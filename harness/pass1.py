"""Pass 1 (EST-108): fill the content-addressed strip cache for every non-test ``.py`` blob in
every base_commit snapshot of corpus/instances.json.

For each blob (keyed by its git blob sha, which is what ``git ls-tree`` reports):

    cache/<sha>.py       stripped source (byte-identical to the original when nothing changed)
    cache/<sha>.jsonl    sidecar (harness/CONTRACT.md); ``stats`` record last
    cache/<sha>.FAILED   written INSTEAD of the two files above when astcheck.equal fails or the
                         stripper raises; first line = status, rest = detail

Also writes::

    cache/MANIFEST.json                 directives/contract/stripper hashes; refuses to run on a
                                        stale cache unless --reset
    corpus/snapshots/<instance_id>.json every selected (path, blob_sha, cached, astcheck)
    corpus/pass1-report.json / .md      per-instance / per-repo stats and cache hit rates
    corpus/pass1-unresolved.tsv         unresolved comments aggregated by exact text

Blobs are enumerated with ``git ls-tree -r -z`` and read with one long-lived
``git cat-file --batch`` in the parent; nothing is ever checked out.  Stripping runs in a
ProcessPoolExecutor; every output is a pure function of the blob content + directives, so
scheduling never changes what lands on disk.

CLI::

    pass1.py [--instances corpus/instances.json] [--mirror ~/repos/sideword-corpus]
             [--cache cache/] [--jobs N] [--reset] [--only <instance_id>...]
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
    from harness import astcheck, directives as directives_mod, paths as paths_mod, strip as strip_mod
else:
    from . import astcheck, directives as directives_mod, paths as paths_mod, strip as strip_mod

DEFAULT_INSTANCES = ROOT / "corpus" / "instances.json"
DEFAULT_MIRROR = Path.home() / "repos" / "sideword-corpus"
DEFAULT_CACHE = ROOT / "cache"
DEFAULT_DIRECTIVES = ROOT / "corpus" / "directives.toml"
CONTRACT = ROOT / "harness" / "CONTRACT.md"
STRIPPER_FILES = ("strip.py", "directives.py", "astcheck.py")
SNAPSHOT_DIR = ROOT / "corpus" / "snapshots"
REPORT_JSON = ROOT / "corpus" / "pass1-report.json"
REPORT_MD = ROOT / "corpus" / "pass1-report.md"
UNRESOLVED_TSV = ROOT / "corpus" / "pass1-unresolved.tsv"

STAT_KEYS = ("comments_removed", "docstrings_removed", "doctest_docstrings_kept",
             "directives_kept", "stray_strings_kept", "unresolved",
             "lines_before", "lines_after", "bytes_before", "bytes_after")


def log(*a) -> None:
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def stripper_version() -> str:
    h = hashlib.sha256()
    for name in STRIPPER_FILES:
        h.update((ROOT / "harness" / name).read_bytes())
    return h.hexdigest()


def blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


# ---- git plumbing ---------------------------------------------------------------------------
def ls_tree(mirror: Path, commit: str) -> list[tuple[str, str, str, str]]:
    """[(mode, type, sha, path)] for every entry reachable from ``commit``."""
    out = subprocess.run(["git", "-C", str(mirror), "ls-tree", "-r", "-z", commit],
                         check=True, capture_output=True).stdout
    entries = []
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, typ, sha = meta.decode().split(" ")
        entries.append((mode, typ, sha, path.decode("utf-8", errors="surrogateescape")))
    return entries


class CatFile:
    """One long-lived ``git cat-file --batch`` process."""

    def __init__(self, mirror: Path):
        self.proc = subprocess.Popen(["git", "-C", str(mirror), "cat-file", "--batch"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, sha: str) -> bytes:
        self.proc.stdin.write((sha + "\n").encode())
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().decode().split()
        if len(header) != 3 or header[1] != "blob":
            raise RuntimeError(f"cat-file: unexpected header for {sha}: {header}")
        size = int(header[2])
        data = self.proc.stdout.read(size)
        self.proc.stdout.read(1)  # trailing newline
        return data

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.wait()


# ---- worker -----------------------------------------------------------------------------------
_W_DIRECTIVES = None
_W_CACHE = None


def _w_init(directives_path: str, cache_dir: str) -> None:
    global _W_DIRECTIVES, _W_CACHE
    _W_DIRECTIVES = directives_mod.load(directives_path)
    _W_CACHE = Path(cache_dir)


def _summary_from_records(records: list[dict]) -> dict:
    stats = records[-1] if records and records[-1].get("kind") == "stats" else None
    unresolved = [(r["line"], r["text"], r.get("watch")) for r in records
                  if r.get("kind") == "comment" and r.get("unresolved")]
    parse_error = any(r.get("kind") == "parse_error" for r in records)
    return {"stats": stats, "unresolved": unresolved, "parse_error": parse_error}


def process_blob(sha: str, data: bytes) -> dict:
    """Strip one blob (or read it back from the cache).  Pure in (sha, data, directives)."""
    cache = _W_CACHE
    py = cache / f"{sha}.py"
    jsonl = cache / f"{sha}.jsonl"
    failed = cache / f"{sha}.FAILED"
    res = {"sha": sha, "has_doc": b"__doc__" in data, "was_cached": False,
           "status": "ok", "detail": "", "stats": None, "unresolved": [],
           "parse_error": False}
    if failed.exists():
        txt = failed.read_text(encoding="utf-8", errors="replace")
        first, _, rest = txt.partition("\n")
        res.update(was_cached=True, status=first.strip() or "astcheck_fail", detail=rest)
        return res
    if py.exists() and jsonl.exists():
        records = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").split("\n") if l]
        res.update(was_cached=True, **_summary_from_records(records))
        if res["parse_error"]:
            res["status"] = "parse_error"
        return res
    try:
        out, records = strip_mod.strip_source(data, _W_DIRECTIVES)
        ok, detail = astcheck.equal(data, out, _W_DIRECTIVES)
    except Exception:  # never crash the batch
        detail = traceback.format_exc()
        atomic_write(failed, ("error\n" + detail).encode("utf-8"))
        res.update(status="error", detail=detail)
        return res
    if not ok:
        atomic_write(failed, ("astcheck_fail\n" + detail).encode("utf-8"))
        res.update(status="astcheck_fail", detail=detail)
        return res
    side = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode("utf-8")
    atomic_write(jsonl, side)
    atomic_write(py, out)
    res.update(_summary_from_records(records))
    if res["parse_error"]:
        res["status"] = "parse_error"
    return res


# ---- manifest ---------------------------------------------------------------------------------
def check_manifest(cache: Path, directives_path: Path, reset: bool) -> dict:
    cache.mkdir(parents=True, exist_ok=True)
    current = {"directives_sha256": sha256_file(directives_path),
               "contract_sha256": sha256_file(CONTRACT),
               "stripper_version": stripper_version()}
    mpath = cache / "MANIFEST.json"
    old = json.loads(mpath.read_text()) if mpath.exists() else None
    stale = old is not None and (old.get("directives_sha256") != current["directives_sha256"]
                                 or old.get("stripper_version") != current["stripper_version"])
    if reset:
        n = 0
        for p in cache.iterdir():
            if p.suffix in (".py", ".jsonl", ".FAILED") or ".tmp-" in p.name:
                p.unlink()
                n += 1
        log(f"--reset: deleted {n} cache files")
    elif stale:
        sys.exit("cache/MANIFEST.json does not match the current directives.toml / stripper "
                 "(stale cache). Re-run with --reset to wipe cache/*.py, *.jsonl, *.FAILED.\n"
                 f"  manifest: {json.dumps(old, indent=1)}\n  current:  {json.dumps(current, indent=1)}")
    else:
        for p in cache.iterdir():          # leftovers from an interrupted run
            if ".tmp-" in p.name:
                p.unlink()
    manifest = {**current, "created": (old or {}).get("created") if (old and not reset and not stale)
                else None,
                "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "directives_path": str(directives_path), "stripper_files": list(STRIPPER_FILES)}
    if manifest["created"] is None:
        manifest["created"] = manifest["updated"]
    atomic_write(mpath, json.dumps(manifest, indent=1).encode() + b"\n")
    return manifest


# ---- main pass --------------------------------------------------------------------------------
def select_blobs(entries, test_extra: set[str]) -> tuple[list[tuple[str, str, str]], dict]:
    """[(path, sha, mode)] of strippable .py blobs, plus counts of what was skipped and why."""
    picked = []
    skipped = collections.Counter()
    for mode, typ, sha, path in entries:
        if not path.endswith(".py"):
            skipped["not_py"] += 1
            continue
        if typ != "blob" or mode == "160000":
            skipped["submodule"] += 1
            continue
        if mode == "120000":
            skipped["symlink"] += 1
            continue
        if paths_mod.is_test_path(path, extra=test_extra):
            skipped["test_path"] += 1
            continue
        picked.append((path, sha, mode))
    picked.sort()
    return picked, dict(skipped)


def zero_stats() -> dict:
    d = {k: 0 for k in STAT_KEYS}
    d.update(files=0, parse_errors=0, astcheck_failures=0, errors=0, has_doc=0)
    return d


def add_stats(acc: dict, res: dict) -> None:
    acc["files"] += 1
    if res["has_doc"]:
        acc["has_doc"] += 1
    if res["status"] == "astcheck_fail":
        acc["astcheck_failures"] += 1
        return
    if res["status"] == "error":
        acc["errors"] += 1
        return
    if res["parse_error"]:
        acc["parse_errors"] += 1
    st = res["stats"] or {}
    for k in STAT_KEYS:
        acc[k] += st.get(k, 0)


def astcheck_label(res: dict) -> str:
    if res["status"] in ("astcheck_fail", "error"):
        return "fail"
    if res["parse_error"]:
        return "parse_error"
    return "ok"


def run(args) -> int:
    t0 = time.time()
    cache = Path(args.cache).resolve()
    mirror = Path(args.mirror).expanduser().resolve()
    directives_path = Path(args.directives).resolve()
    directives_mod.load(directives_path)  # fail fast on schema problems
    manifest = check_manifest(cache, directives_path, args.reset)
    instances = json.loads(Path(args.instances).read_text())
    if args.only:
        want = set(args.only)
        instances = [i for i in instances if i["instance_id"] in want]
        missing = want - {i["instance_id"] for i in instances}
        if missing:
            sys.exit(f"--only: unknown instance ids {sorted(missing)}")
    if not instances:
        sys.exit("no instances selected")

    # 1. enumerate: per instance, selected blobs; global first-seen path per sha
    per_instance = []
    first_seen: dict[str, tuple[str, str, str]] = {}   # sha -> (repo, instance_id, path)
    unique_order: list[str] = []
    for inst in instances:
        entries = ls_tree(mirror, inst["base_commit"])
        picked, skipped = select_blobs(entries, set(inst.get("test_patch_paths") or []))
        per_instance.append({"inst": inst, "picked": picked, "skipped": skipped})
        for path, sha, _mode in picked:
            if sha not in first_seen:
                first_seen[sha] = (inst["repo"], inst["instance_id"], path)
                unique_order.append(sha)
        log(f"{inst['instance_id']}: {len(picked)} blobs selected, skipped {skipped}")
    log(f"{len(instances)} instances, {sum(len(p['picked']) for p in per_instance)} blob refs, "
        f"{len(unique_order)} unique blobs")

    # cache hit bookkeeping (before this run touches anything)
    def on_disk(sha: str) -> bool:
        return ((cache / f"{sha}.py").exists() and (cache / f"{sha}.jsonl").exists()) \
            or (cache / f"{sha}.FAILED").exists()
    preexisting = {sha for sha in unique_order if on_disk(sha)}
    log(f"{len(preexisting)} unique blobs already on disk")

    # 2. strip every unique blob (bounded in-flight window; parent streams cat-file)
    results: dict[str, dict] = {}
    reader = CatFile(mirror)
    sha_checked = 0
    jobs = max(1, args.jobs)
    window = jobs * 8
    with cf.ProcessPoolExecutor(max_workers=jobs, initializer=_w_init,
                                initargs=(str(directives_path), str(cache))) as pool:
        pending: dict = {}
        it = iter(unique_order)
        done_n = 0
        exhausted = False
        while True:
            while not exhausted and len(pending) < window:
                sha = next(it, None)
                if sha is None:
                    exhausted = True
                    break
                data = reader.read(sha)
                if blob_sha1(data) != sha:   # ls-tree sha must be the content-address we key on
                    raise SystemExit(f"blob sha mismatch for {sha} ({first_seen[sha]})")
                sha_checked += 1
                fut = pool.submit(process_blob, sha, data)
                pending[fut] = sha
            if not pending:
                break
            done, _ = cf.wait(list(pending), return_when=cf.FIRST_COMPLETED)
            for fut in done:
                sha = pending.pop(fut)
                results[sha] = fut.result()
                done_n += 1
                if done_n % 2000 == 0:
                    log(f"  {done_n}/{len(unique_order)} blobs done")
    reader.close()
    log(f"strip phase done in {time.time() - t0:.1f}s ({sha_checked} blobs read)")

    # 3. aggregate
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    seen_this_run: set[str] = set()
    inst_rows = []
    repo_rows: dict[str, dict] = {}
    repo_unique: dict[str, set] = collections.defaultdict(set)
    repo_refs: dict[str, int] = collections.Counter()
    for entry in per_instance:
        inst = entry["inst"]
        repo = inst["repo"]
        st = zero_stats()
        hit_disk = hit_run = 0
        files = []
        for path, sha, mode in entry["picked"]:
            res = results[sha]
            add_stats(st, res)
            if sha in preexisting:
                hit_disk += 1
            if sha in seen_this_run:
                hit_run += 1
            files.append({"path": path, "blob_sha": sha, "mode": mode,
                          "cached": res["status"] not in ("astcheck_fail", "error"),
                          "astcheck": astcheck_label(res)})
            repo_unique[repo].add(sha)
            repo_refs[repo] += 1
        seen_this_run.update(sha for _, sha, _ in entry["picked"])
        n = len(entry["picked"])
        row = {"instance_id": inst["instance_id"], "repo": repo, "base_commit": inst["base_commit"],
               "created_at": inst.get("created_at"), "blobs": n,
               "hits_on_disk_before_run": hit_disk, "hits_from_earlier_instance": hit_run,
               "skipped": entry["skipped"], **st}
        inst_rows.append(row)
        snap = {"instance_id": inst["instance_id"], "repo": inst["repo"],
                "base_commit": inst["base_commit"], "directives_sha256": manifest["directives_sha256"],
                "stripper_version": manifest["stripper_version"], "cache_dir": str(cache),
                "selected": n, "skipped": entry["skipped"],
                "test_patch_paths": inst.get("test_patch_paths") or [], "files": files}
        atomic_write(SNAPSHOT_DIR / f"{inst['instance_id']}.json",
                     json.dumps(snap, indent=1, ensure_ascii=False).encode("utf-8") + b"\n")
    # hit = on disk before the run OR produced by an earlier instance of this run
    seen: set[str] = set()
    seen_repo: dict[str, set] = collections.defaultdict(set)
    for entry, row in zip(per_instance, inst_rows):
        picked = entry["picked"]
        hits = sum(1 for _, sha, _ in picked if sha in preexisting or sha in seen)
        row["hits"] = hits
        row["hit_rate"] = round(hits / row["blobs"], 4) if row["blobs"] else None
        # same-repo reuse only (ignores e.g. empty __init__.py shared across repos)
        same = sum(1 for _, sha, _ in picked if sha in seen_repo[row["repo"]])
        row["hits_same_repo_earlier_instance"] = same
        row["hit_rate_same_repo"] = round(same / row["blobs"], 4) if row["blobs"] else None
        seen.update(sha for _, sha, _ in picked)
        seen_repo[row["repo"]].update(sha for _, sha, _ in picked)

    for repo in sorted(repo_unique):
        st = zero_stats()
        for sha in repo_unique[repo]:
            add_stats(st, results[sha])
        rows = [r for r in inst_rows if r["repo"] == repo]
        repo_rows[repo] = {"repo": repo, "instances": len(rows), "unique_blobs": len(repo_unique[repo]),
                           "blob_refs": repo_refs[repo],
                           "reuse_rate": round(1 - len(repo_unique[repo]) / repo_refs[repo], 4),
                           **st}

    # unresolved aggregation (by exact text, over unique blobs; refs weighted separately)
    unres: dict[str, dict] = {}
    ref_count = collections.Counter(sha for e in per_instance for _, sha, _ in e["picked"])
    for sha in unique_order:
        res = results[sha]
        repo, _iid, path = first_seen[sha]
        for line, text, watch in res["unresolved"]:
            u = unres.setdefault(text, {"count": 0, "refs": 0, "watch": watch, "examples": [], "repos": set()})
            u["count"] += 1
            u["refs"] += ref_count[sha]
            u["repos"].add(repo)
            if len(u["examples"]) < 3:
                u["examples"].append((repo, path, line))
    unres_rows = sorted(unres.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
    with open(UNRESOLVED_TSV, "w", encoding="utf-8") as fh:
        fh.write("count\trefs\twatch\trepos\ttext\texamples\n")
        for text, u in unres_rows:
            ex = "; ".join(f"{r}:{p}:{l}" for r, p, l in u["examples"])
            fh.write(f"{u['count']}\t{u['refs']}\t{u['watch']}\t{','.join(sorted(u['repos']))}\t"
                     f"{text.replace(chr(9), ' ')}\t{ex}\n")

    failures = [{"sha": sha, "status": results[sha]["status"], "first_path": first_seen[sha],
                 "detail": results[sha]["detail"][:2000]}
                for sha in unique_order if results[sha]["status"] in ("astcheck_fail", "error")]
    parse_errors = [{"sha": sha, "first_path": first_seen[sha],
                     "refs": ref_count[sha]}
                    for sha in unique_order if results[sha]["parse_error"]]

    total = zero_stats()
    for sha in unique_order:
        add_stats(total, results[sha])
    wall = time.time() - t0
    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "wall_seconds": round(wall, 1), "jobs": jobs, "manifest": manifest,
        "instances": len(instances), "blob_refs": sum(r["blobs"] for r in inst_rows),
        "unique_blobs": len(unique_order), "preexisting_on_disk": len(preexisting),
        "totals_unique": total,
        "per_repo": [repo_rows[r] for r in sorted(repo_rows)],
        "per_instance": inst_rows,
        "unresolved_distinct_texts": len(unres_rows),
        "unresolved_top": [{"text": t, **{k: v for k, v in u.items() if k != "repos"},
                            "repos": sorted(u["repos"])} for t, u in unres_rows[:50]],
        "astcheck_failures": failures, "parse_errors": parse_errors,
    }
    REPORT_JSON.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_MD.write_text(render_md(report), encoding="utf-8")
    log(f"done in {wall:.1f}s; unique={len(unique_order)} refs={report['blob_refs']} "
        f"failures={len(failures)} parse_errors={len(parse_errors)} "
        f"unresolved={total['unresolved']} ({len(unres_rows)} distinct)")
    return 1 if failures else 0


def _fmt(n) -> str:
    if isinstance(n, float):
        return f"{n:.1%}" if n <= 1 else f"{n:,.1f}"
    if isinstance(n, int):
        return f"{n:,}"
    return str(n)


def render_md(rep: dict) -> str:
    L = []
    t = rep["totals_unique"]
    L.append("# Pass 1 report (strip cache)\n")
    L.append(f"Generated {rep['generated_at']} · wall {rep['wall_seconds']} s · jobs {rep['jobs']} · "
             f"directives sha256 `{rep['manifest']['directives_sha256'][:12]}` · "
             f"stripper `{rep['manifest']['stripper_version'][:12]}`\n")
    L.append(f"Instances {rep['instances']} · blob refs {_fmt(rep['blob_refs'])} · unique blobs "
             f"{_fmt(rep['unique_blobs'])} · on disk before run {_fmt(rep['preexisting_on_disk'])}\n")
    L.append("## Totals over unique blobs\n")
    L.append("| files | comments removed | docstrings removed | doctest kept | directives kept | stray kept | "
             "unresolved | parse errors | AST failures | errors | `__doc__` files | bytes before | bytes after | "
             "lines before | lines after |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    L.append("| " + " | ".join(_fmt(t[k]) for k in ("files", "comments_removed", "docstrings_removed",
             "doctest_docstrings_kept", "directives_kept", "stray_strings_kept", "unresolved",
             "parse_errors", "astcheck_failures", "errors", "has_doc", "bytes_before", "bytes_after",
             "lines_before", "lines_after")) + " |\n")
    L.append("## Per repo (unique blobs)\n")
    L.append("| repo | inst | unique blobs | blob refs | reuse | comments removed | docstrings removed | "
             "doctest kept | directives kept | stray kept | unresolved | parse errors | AST failures | "
             "`__doc__` files | bytes before | bytes after |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rep["per_repo"]:
        L.append(f"| {r['repo']} | {r['instances']} | {_fmt(r['unique_blobs'])} | {_fmt(r['blob_refs'])} | "
                 f"{_fmt(r['reuse_rate'])} | {_fmt(r['comments_removed'])} | {_fmt(r['docstrings_removed'])} | "
                 f"{_fmt(r['doctest_docstrings_kept'])} | {_fmt(r['directives_kept'])} | "
                 f"{_fmt(r['stray_strings_kept'])} | {_fmt(r['unresolved'])} | {_fmt(r['parse_errors'])} | "
                 f"{_fmt(r['astcheck_failures'] + r['errors'])} | {_fmt(r['has_doc'])} | "
                 f"{_fmt(r['bytes_before'])} | {_fmt(r['bytes_after'])} |")
    L.append("\n## Per instance (blob references; hit = cached before this instance was processed)\n")
    L.append("| instance | blobs | hits | hit rate | on-disk hits | earlier-instance hits | same-repo hit rate | "
             "comments removed | "
             "docstrings removed | doctest kept | directives kept | stray kept | unresolved | parse errors | "
             "AST failures | `__doc__` files | bytes before | bytes after |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rep["per_instance"]:
        L.append(f"| {r['instance_id']} | {_fmt(r['blobs'])} | {_fmt(r['hits'])} | "
                 f"{_fmt(r['hit_rate']) if r['hit_rate'] is not None else '-'} | "
                 f"{_fmt(r['hits_on_disk_before_run'])} | {_fmt(r['hits_from_earlier_instance'])} | "
                 f"{_fmt(r['hit_rate_same_repo']) if r['hit_rate_same_repo'] is not None else '-'} | "
                 f"{_fmt(r['comments_removed'])} | {_fmt(r['docstrings_removed'])} | "
                 f"{_fmt(r['doctest_docstrings_kept'])} | {_fmt(r['directives_kept'])} | "
                 f"{_fmt(r['stray_strings_kept'])} | {_fmt(r['unresolved'])} | {_fmt(r['parse_errors'])} | "
                 f"{_fmt(r['astcheck_failures'] + r['errors'])} | {_fmt(r['has_doc'])} | "
                 f"{_fmt(r['bytes_before'])} | {_fmt(r['bytes_after'])} |")
    L.append(f"\n## Unresolved comments ({rep['unresolved_distinct_texts']} distinct texts; top 20; "
             f"full list in corpus/pass1-unresolved.tsv)\n")
    L.append("| count | refs | watch | repos | text | example |")
    L.append("|---:|---:|---|---|---|---|")
    for u in rep["unresolved_top"][:20]:
        ex = u["examples"][0] if u["examples"] else ("", "", "")
        txt = u["text"].replace("|", "\\|")
        L.append(f"| {u['count']} | {u['refs']} | {u['watch']} | {','.join(u['repos'])} | `{txt}` | "
                 f"{ex[0]}:{ex[1]}:{ex[2]} |")
    L.append(f"\n## AST-check failures / stripper errors ({len(rep['astcheck_failures'])})\n")
    for f in rep["astcheck_failures"]:
        r, i, p = f["first_path"]
        L.append(f"- `{f['sha']}` {f['status']} — {r} `{p}` (first seen in {i})\n\n```\n{f['detail']}\n```\n")
    if not rep["astcheck_failures"]:
        L.append("none\n")
    L.append(f"\n## Parse errors ({len(rep['parse_errors'])}; left byte-identical, cached as identity)\n")
    for f in rep["parse_errors"]:
        r, i, p = f["first_path"]
        L.append(f"- `{f['sha']}` {r} `{p}` (first seen in {i}, {f['refs']} refs)")
    if not rep["parse_errors"]:
        L.append("none")
    L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--instances", default=str(DEFAULT_INSTANCES))
    ap.add_argument("--mirror", default=str(DEFAULT_MIRROR))
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--directives", default=str(DEFAULT_DIRECTIVES))
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--reset", action="store_true",
                    help="wipe cache/*.py, *.jsonl, *.FAILED and rewrite MANIFEST.json")
    ap.add_argument("--only", nargs="*", metavar="INSTANCE_ID")
    args = ap.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
