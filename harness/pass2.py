"""Pass 2 (EST-109): materialize one ``-nc`` commit per instance in the mirror and tag it, gated.

For every instance in corpus/instances.json (order preserved) the tree is built with git
plumbing only -- the mirror's (empty) working tree and its real index are never touched:

    GIT_INDEX_FILE=<tmp> git read-tree <base_commit>
    git hash-object -w --no-filters --stdin-paths     (cache/<blob_sha>.py -> new blob sha)
    GIT_INDEX_FILE=<tmp> git update-index -z --index-info   (mode SP sha TAB path)
    GIT_INDEX_FILE=<tmp> git write-tree
    git commit-tree <tree> -p <base_commit>           (fixed author/committer/date)
    git tag <instance_id>-nc <commit>                 (lightweight; never overwritten
                                                       without --force)

The commit is only created after the tree passes every gate (harness/CONTRACT.md):

    1. astcheck.equal(orig, stripped) for every selected path (re-checked here; the pass-1
       flag in the snapshot is not trusted).  orig = ``git cat-file`` of the snapshot's
       blob_sha, stripped = cache/<blob_sha>.py.
    2. sum(unresolved) over the snapshot's sidecars == 0 (parse_error records are counted
       and reported but do not block).
    3. Test paths untouched: every entry of ``git diff-tree -r <base> <tree>`` is a
       modification (no add/delete/rename/mode change) of a selected, non-test path; every
       test_patch_path resolves to the same blob in both trees.
    4. The new tree lists exactly the paths of base_commit (ls-tree counts and path sets
       equal; every non-selected entry byte-identical incl. mode).
    Additionally the tree's blob for every selected path must equal the cache file's
    content address (sha1("blob <len>\\0" + bytes)).

Author/committer are ``sideword <sideword@localhost>`` at a fixed date so a rerun produces
byte-identical commit shas; the second run then finds every tag already pointing at the
same sha and creates nothing (``tag_action == "unchanged"``).

Writes corpus/pass2-report.json and corpus/pass2-report.md.

CLI::

    pass2.py [--instances corpus/instances.json] [--mirror ~/repos/sideword-corpus]
             [--cache cache/] [--directives corpus/directives.toml] [--only <id>...]
             [--force] [--jobs N] [--worktree-check <id>...] [--no-tag]
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures as cf
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
    from harness import astcheck, directives as directives_mod, paths as paths_mod, strip as strip_mod
    from harness.pass1 import (CatFile, blob_sha1, log, ls_tree, sha256_file, stripper_version,
                               STAT_KEYS)
else:
    from . import astcheck, directives as directives_mod, paths as paths_mod, strip as strip_mod
    from .pass1 import CatFile, blob_sha1, log, ls_tree, sha256_file, stripper_version, STAT_KEYS

DEFAULT_INSTANCES = ROOT / "corpus" / "instances.json"
DEFAULT_MIRROR = Path.home() / "repos" / "sideword-corpus"
DEFAULT_CACHE = ROOT / "cache"
DEFAULT_DIRECTIVES = ROOT / "corpus" / "directives.toml"
SNAPSHOT_DIR = ROOT / "corpus" / "snapshots"
PASS1_REPORT = ROOT / "corpus" / "pass1-report.json"
REPORT_JSON = ROOT / "corpus" / "pass2-report.json"
REPORT_MD = ROOT / "corpus" / "pass2-report.md"

# Deterministic identity for every -nc commit (byte-identical shas across reruns).
COMMIT_ENV = {
    "GIT_AUTHOR_NAME": "sideword", "GIT_AUTHOR_EMAIL": "sideword@localhost",
    "GIT_AUTHOR_DATE": "2026-08-17T00:00:00Z",
    "GIT_COMMITTER_NAME": "sideword", "GIT_COMMITTER_EMAIL": "sideword@localhost",
    "GIT_COMMITTER_DATE": "2026-08-17T00:00:00Z",
}
TAG_SUFFIX = "-nc"


# ---- git helpers -------------------------------------------------------------------------------
def git(mirror: Path, *args, input: bytes | None = None, env: dict | None = None,
        check: bool = True) -> subprocess.CompletedProcess:
    full_env = None
    if env:
        full_env = {**os.environ, **env}
    return subprocess.run(["git", "-C", str(mirror), *args], input=input, env=full_env,
                          check=check, capture_output=True)


def git_out(mirror: Path, *args, **kw) -> str:
    return git(mirror, *args, **kw).stdout.decode().strip()


def tree_entries(mirror: Path, treeish: str) -> dict[str, tuple[str, str, str]]:
    """path -> (mode, type, sha) for every entry reachable from ``treeish``."""
    return {path: (mode, typ, sha) for mode, typ, sha, path in ls_tree(mirror, treeish)}


def diff_tree(mirror: Path, a: str, b: str) -> list[dict]:
    """``git diff-tree -r -z --raw`` between two tree-ish, no rename detection."""
    out = git(mirror, "diff-tree", "-r", "-z", "--no-renames", a, b).stdout
    fields = out.split(b"\0")
    rows = []
    i = 0
    while i < len(fields) and fields[i]:
        meta = fields[i].decode()
        # ":<old_mode> <new_mode> <old_sha> <new_sha> <status>"
        old_mode, new_mode, old_sha, new_sha, status = meta[1:].split(" ")
        path = fields[i + 1].decode("utf-8", errors="surrogateescape")
        rows.append({"path": path, "old_mode": old_mode, "new_mode": new_mode,
                     "old_sha": old_sha, "new_sha": new_sha, "status": status})
        i += 2
    return rows


# ---- astcheck worker ---------------------------------------------------------------------------
_W_DIRECTIVES = None


def _w_init(directives_path: str) -> None:
    global _W_DIRECTIVES
    _W_DIRECTIVES = directives_mod.load(directives_path)


def sidecar_keep_owners(cache_py: str) -> list[tuple[str, str]]:
    """The ``keep_owners`` context cache/<sha>.jsonl was written under (usually none)."""
    jsonl = Path(cache_py).with_suffix(".jsonl")
    try:
        lines = [l for l in jsonl.read_text(encoding="utf-8").split("\n") if l]
    except OSError:
        return []
    return strip_mod.keep_owners_from_sidecar(json.loads(l) for l in lines[-1:])


def check_blob(sha: str, orig: bytes, cache_py: str) -> dict:
    """Re-verify one cache entry against its original blob.  Pure in (orig, cache bytes,
    the sidecar's recorded ``keep_owners``)."""
    try:
        stripped = Path(cache_py).read_bytes()
    except OSError as e:
        return {"sha": sha, "ok": False, "detail": f"cache file unreadable: {e}",
                "stripped_sha": None, "identity": False}
    try:
        ok, detail = astcheck.equal(orig, stripped, _W_DIRECTIVES, sidecar_keep_owners(cache_py))
    except Exception as e:  # never crash the batch
        ok, detail = False, f"astcheck raised {type(e).__name__}: {e}"
    return {"sha": sha, "ok": ok, "detail": detail if not ok else "",
            "stripped_sha": blob_sha1(stripped), "identity": stripped == orig}


def _parse_ok(path: str) -> tuple[str, str | None]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ast.parse(Path(path).read_bytes())
        return path, None
    except (SyntaxError, ValueError) as e:
        return path, f"{type(e).__name__}: {e}"
    except Exception as e:  # pragma: no cover
        return path, f"{type(e).__name__}: {e}"


# ---- sidecars ----------------------------------------------------------------------------------
def read_sidecar_stats(cache: Path, sha: str) -> tuple[dict | None, bool, str | None]:
    """(stats record, parse_error?, error) for cache/<sha>.jsonl."""
    p = cache / f"{sha}.jsonl"
    if (cache / f"{sha}.FAILED").exists():
        return None, False, "cache/<sha>.FAILED present"
    if not p.exists():
        return None, False, "sidecar missing"
    lines = [l for l in p.read_text(encoding="utf-8").split("\n") if l]
    if not lines:
        return None, False, "sidecar empty"
    stats = json.loads(lines[-1])
    if stats.get("kind") != "stats":
        return None, False, "sidecar has no trailing stats record"
    parse_error = any('"parse_error"' in l and json.loads(l).get("kind") == "parse_error"
                      for l in lines[:-1])
    return stats, parse_error, None


# ---- per instance ------------------------------------------------------------------------------
def commit_message(inst: dict, snap: dict, agg: dict, files_changed: int, files_identity: int,
                   directives_sha: str, stripper_ver: str) -> str:
    return "\n".join([
        f"sideword -nc: {inst['instance_id']}",
        "",
        "Comments and docstrings stripped from every non-test .py file (harness/CONTRACT.md).",
        "",
        f"repo: {inst['repo']}",
        f"base_commit: {inst['base_commit']}",
        f"directives_sha256: {directives_sha}",
        f"stripper_version: {stripper_ver}",
        f"files_stripped: {snap['selected']}",
        f"files_changed: {files_changed}",
        f"files_identity: {files_identity}",
        f"comments_removed: {agg['comments_removed']}",
        f"docstrings_removed: {agg['docstrings_removed']}",
        f"doctest_docstrings_kept: {agg['doctest_docstrings_kept']}",
        f"docstrings_kept: {agg.get('docstrings_kept', 0)}",
        f"directives_kept: {agg['directives_kept']}",
        f"stray_strings_kept: {agg['stray_strings_kept']}",
        f"unresolved: {agg['unresolved']}",
        f"parse_errors: {agg['parse_errors']}",
        "",
    ])


def process_instance(inst: dict, snap: dict, mirror: Path, cache: Path, ast_results: dict,
                     directives_sha: str, stripper_ver: str, force: bool, do_tag: bool) -> dict:
    iid = inst["instance_id"]
    base = inst["base_commit"]
    tag = f"{iid}{TAG_SUFFIX}"
    t0 = time.time()
    row = {"instance_id": iid, "repo": inst["repo"], "base_commit": base, "tag": tag,
           "nc_tree": None, "nc_commit": None, "files_selected": snap["selected"],
           "files_changed": None, "files_identity": None,
           "gate": {"ast_ok": None, "unresolved": None, "parse_errors": None,
                    "tests_untouched": None, "tree_complete": None, "cache_complete": None},
           "gate_passed": False, "tagged": False, "tag_action": None, "failure_detail": [],
           "stats": None, "seconds": None}
    fail = row["failure_detail"]
    files = snap["files"]
    test_extra = set(snap.get("test_patch_paths") or inst.get("test_patch_paths") or [])
    selected_paths = {f["path"] for f in files}

    # -- gate 1 + cache completeness ---------------------------------------------------------
    ast_bad = []
    cache_missing = []
    identity = 0
    for f in files:
        r = ast_results.get(f["blob_sha"])
        if r is None or r["stripped_sha"] is None:
            cache_missing.append(f["path"])
            continue
        if not r["ok"]:
            ast_bad.append((f["path"], f["blob_sha"], r["detail"][:500]))
        if r["identity"]:
            identity += 1
    row["gate"]["cache_complete"] = not cache_missing
    row["gate"]["ast_ok"] = not ast_bad and not cache_missing
    row["files_identity"] = identity
    if cache_missing:
        fail.append(f"cache incomplete: {len(cache_missing)} selected blobs without a readable "
                    f"cache/<sha>.py (e.g. {cache_missing[:3]})")
    if ast_bad:
        fail.append(f"astcheck failed for {len(ast_bad)} files: "
                    + "; ".join(f"{p} ({s[:10]}): {d.splitlines()[0] if d else ''}"
                                for p, s, d in ast_bad[:5]))

    # -- gate 2: sidecars ---------------------------------------------------------------------
    agg = {k: 0 for k in STAT_KEYS}
    agg["parse_errors"] = 0
    agg["files"] = len(files)
    parse_error_paths = []
    sidecar_errors = []
    for f in files:
        stats, perr, err = read_sidecar_stats(cache, f["blob_sha"])
        if err:
            sidecar_errors.append((f["path"], err))
            continue
        for k in STAT_KEYS:
            agg[k] += stats.get(k, 0)
        if perr:
            agg["parse_errors"] += 1
            parse_error_paths.append(f["path"])
    row["stats"] = agg
    row["gate"]["unresolved"] = agg["unresolved"] if not sidecar_errors else None
    row["gate"]["parse_errors"] = agg["parse_errors"]
    row["parse_error_paths"] = parse_error_paths
    if sidecar_errors:
        fail.append(f"{len(sidecar_errors)} sidecars unreadable: {sidecar_errors[:3]}")
    if agg["unresolved"]:
        fail.append(f"unresolved comments in snapshot: {agg['unresolved']}")

    if fail:
        row["seconds"] = round(time.time() - t0, 2)
        return row

    # -- build the tree in a temporary index -----------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="sideword-pass2-") as td:
        index = os.path.join(td, "index")
        env = {"GIT_INDEX_FILE": index}
        git(mirror, "read-tree", base, env=env)
        # hash every cache file into the mirror's object db, in snapshot order
        stdin_paths = "".join(str(cache / f"{f['blob_sha']}.py") + "\n" for f in files).encode()
        out = git(mirror, "hash-object", "-w", "--no-filters", "--stdin-paths",
                  input=stdin_paths).stdout.decode().split()
        if len(out) != len(files):
            fail.append(f"hash-object returned {len(out)} shas for {len(files)} paths")
            row["seconds"] = round(time.time() - t0, 2)
            return row
        mismatch = [(f["path"], got, ast_results[f["blob_sha"]]["stripped_sha"])
                    for f, got in zip(files, out)
                    if got != ast_results[f["blob_sha"]]["stripped_sha"]]
        if mismatch:
            fail.append(f"hash-object sha != content address of cache file for {len(mismatch)} "
                        f"paths (cache changed under us?): {mismatch[:3]}")
            row["seconds"] = round(time.time() - t0, 2)
            return row
        info = b"".join(f"{f['mode']} {sha}\t".encode() + f["path"].encode("utf-8", "surrogateescape")
                        + b"\0" for f, sha in zip(files, out))
        git(mirror, "update-index", "-z", "--index-info", input=info, env=env)
        tree = git_out(mirror, "write-tree", env=env)
    row["nc_tree"] = tree

    # -- gate 3 + 4: compare trees ------------------------------------------------------------------
    base_entries = tree_entries(mirror, base)
    new_entries = tree_entries(mirror, tree)
    changed = diff_tree(mirror, base, tree)
    row["files_changed"] = len(changed)
    tests_ok = True
    problems = []
    for c in changed:
        if c["status"] != "M":
            problems.append(f"{c['status']} {c['path']}")
        elif c["path"] not in selected_paths:
            problems.append(f"changed but not selected: {c['path']}")
        elif paths_mod.is_test_path(c["path"], extra=test_extra):
            problems.append(f"test path changed: {c['path']}")
        elif c["old_mode"] != c["new_mode"]:
            problems.append(f"mode changed {c['old_mode']}->{c['new_mode']}: {c['path']}")
    for tp in sorted(test_extra):
        if base_entries.get(tp) != new_entries.get(tp):
            problems.append(f"test_patch_path differs: {tp}")
    # every test path in the base tree must be identical (belt and braces over diff-tree)
    for path, ent in base_entries.items():
        if paths_mod.is_test_path(path, extra=test_extra) and new_entries.get(path) != ent:
            problems.append(f"test path differs: {path}")
            if len(problems) > 20:
                break
    if problems:
        tests_ok = False
        fail.append(f"tests_untouched failed ({len(problems)}): " + "; ".join(problems[:10]))
    row["gate"]["tests_untouched"] = tests_ok

    complete = (len(base_entries) == len(new_entries)
                and set(base_entries) == set(new_entries))
    if complete:
        # non-selected entries: byte-identical incl. mode
        for path, ent in base_entries.items():
            if path not in selected_paths and new_entries[path] != ent:
                complete = False
                fail.append(f"tree_complete failed: non-selected entry differs: {path}")
                break
        # selected paths: mode/type preserved, blob == cache content address
        for f in files:
            path = f["path"]
            nm, nt, ns = new_entries[path]
            if nm != f["mode"] or nt != "blob" or ns != ast_results[f["blob_sha"]]["stripped_sha"]:
                complete = False
                fail.append(f"tree_complete failed: selected entry wrong: {path} "
                            f"({nm} {nt} {ns[:10]})")
                break
    else:
        fail.append(f"tree_complete failed: base has {len(base_entries)} entries, new tree "
                    f"{len(new_entries)}; missing={sorted(set(base_entries) - set(new_entries))[:5]} "
                    f"extra={sorted(set(new_entries) - set(base_entries))[:5]}")
    row["gate"]["tree_complete"] = complete

    if fail:
        row["seconds"] = round(time.time() - t0, 2)
        return row
    row["gate_passed"] = True

    # -- commit + tag -------------------------------------------------------------------------------
    msg = commit_message(inst, snap, agg, len(changed), identity, directives_sha, stripper_ver)
    commit = git_out(mirror, "commit-tree", tree, "-p", base, "-m", msg, env=COMMIT_ENV)
    row["nc_commit"] = commit
    if not do_tag:
        row["tag_action"] = "skipped(--no-tag)"
        row["seconds"] = round(time.time() - t0, 2)
        return row
    existing = git(mirror, "rev-parse", "--verify", "-q", f"refs/tags/{tag}", check=False)
    if existing.returncode == 0:
        old = existing.stdout.decode().strip()
        if old == commit:
            row["tag_action"] = "unchanged"
            row["tagged"] = True
        elif force:
            git(mirror, "tag", "-f", tag, commit)
            row["tag_action"] = f"forced(was {old[:12]})"
            row["tagged"] = True
        else:
            row["tag_action"] = f"refused(exists at {old[:12]})"
            fail.append(f"tag {tag} already exists at {old} != {commit}; rerun with --force to move it")
    else:
        git(mirror, "tag", tag, commit)
        row["tag_action"] = "created"
        row["tagged"] = True
    row["seconds"] = round(time.time() - t0, 2)
    return row


# ---- worktree sanity check ---------------------------------------------------------------------
def worktree_check(mirror: Path, inst: dict, row: dict, jobs: int) -> dict:
    tag = row["tag"]
    res = {"instance_id": inst["instance_id"], "tag": tag, "ok": False, "py_files": 0,
           "parse_failures": [], "preexisting_parse_errors": [], "diff_stat_tail": None,
           "seconds": None, "error": None}
    if not row.get("nc_commit"):
        res["error"] = "no -nc commit"
        return res
    t0 = time.time()
    wt = Path(tempfile.mkdtemp(prefix=f"nc-check-{inst['instance_id']}-", dir="/tmp"))
    wt.rmdir()  # git wants to create it
    try:
        git(mirror, "worktree", "add", "--detach", str(wt), row["nc_commit"])
        head = git_out(wt, "rev-parse", "HEAD")
        if head != row["nc_commit"]:
            res["error"] = f"worktree HEAD {head} != {row['nc_commit']}"
        py = [str(p) for p in wt.rglob("*.py") if ".git" not in p.parts]
        res["py_files"] = len(py)
        changed = {c["path"] for c in diff_tree(mirror, inst["base_commit"], row["nc_commit"])}
        with cf.ProcessPoolExecutor(max_workers=jobs) as pool:
            for path, err in pool.map(_parse_ok, py, chunksize=32):
                if err:
                    rel = os.path.relpath(path, wt)
                    # a file that -nc did not touch is byte-identical to base_commit; a parse
                    # error there is upstream's (e.g. django's tests_syntax_error.py fixture)
                    if rel in changed:
                        res["parse_failures"].append((rel, err))
                    else:
                        res["preexisting_parse_errors"].append((rel, err))
        stat = git_out(wt, "diff", "--stat", f"{inst['base_commit']}..{row['nc_commit']}")
        res["diff_stat_tail"] = stat.splitlines()[-1] if stat else ""
        # sanity: the working tree is clean w.r.t. the -nc commit
        status = git_out(wt, "status", "--porcelain")
        if status:
            res["error"] = (res["error"] or "") + f" worktree not clean: {status[:200]}"
        res["ok"] = res["error"] is None and not res["parse_failures"]
    except subprocess.CalledProcessError as e:
        res["error"] = f"{e.cmd[3:]} failed: {e.stderr.decode(errors='replace')[:500]}"
    finally:
        git(mirror, "worktree", "remove", "--force", str(wt), check=False)
        if wt.exists():
            shutil.rmtree(wt, ignore_errors=True)
        git(mirror, "worktree", "prune", check=False)
    res["seconds"] = round(time.time() - t0, 1)
    return res


# ---- main ----------------------------------------------------------------------------------------
def run(args) -> int:
    t0 = time.time()
    cache = Path(args.cache).resolve()
    mirror = Path(args.mirror).expanduser().resolve()
    directives_path = Path(args.directives).resolve()
    directives_mod.load(directives_path)  # fail fast
    directives_sha = sha256_file(directives_path)
    stripper_ver = stripper_version()
    manifest_path = cache / "MANIFEST.json"
    if not manifest_path.exists():
        sys.exit(f"{manifest_path} missing: run pass1.py first")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("directives_sha256") != directives_sha:
        sys.exit(f"cache/MANIFEST.json directives_sha256 {manifest.get('directives_sha256')} != "
                 f"sha256({directives_path}) {directives_sha}: pass 1 is stale, rerun it")
    if manifest.get("stripper_version") != stripper_ver:
        sys.exit(f"cache/MANIFEST.json stripper_version != current harness (strip/directives/"
                 f"astcheck.py changed): rerun pass 1 (--reset)")
    if not git(mirror, "rev-parse", "--git-dir", check=False).returncode == 0:
        sys.exit(f"{mirror} is not a git repo")

    instances = json.loads(Path(args.instances).read_text())
    if args.only:
        want = set(args.only)
        instances = [i for i in instances if i["instance_id"] in want]
        missing = want - {i["instance_id"] for i in instances}
        if missing:
            sys.exit(f"--only: unknown instance ids {sorted(missing)}")
    if not instances:
        sys.exit("no instances selected")

    # snapshots
    snaps = {}
    for inst in instances:
        p = SNAPSHOT_DIR / f"{inst['instance_id']}.json"
        if not p.exists():
            sys.exit(f"snapshot missing: {p} (run pass1.py)")
        snap = json.loads(p.read_text(encoding="utf-8"))
        if snap["base_commit"] != inst["base_commit"]:
            sys.exit(f"{p}: base_commit {snap['base_commit']} != instances.json {inst['base_commit']}")
        if snap.get("directives_sha256") != directives_sha or snap.get("stripper_version") != stripper_ver:
            sys.exit(f"{p}: written for a different directives/stripper version; rerun pass 1")
        snaps[inst["instance_id"]] = snap
    unique: dict[str, str] = {}   # sha -> first path (for messages)
    for inst in instances:
        for f in snaps[inst["instance_id"]]["files"]:
            unique.setdefault(f["blob_sha"], f["path"])
    log(f"{len(instances)} instances, {sum(len(snaps[i['instance_id']]['files']) for i in instances)} "
        f"blob refs, {len(unique)} unique blobs to re-verify")

    # gate 1 over unique blobs (parent streams cat-file, pool runs astcheck)
    ast_results: dict[str, dict] = {}
    reader = CatFile(mirror)
    jobs = max(1, args.jobs)
    window = jobs * 8
    n_bad = 0
    with cf.ProcessPoolExecutor(max_workers=jobs, initializer=_w_init,
                                initargs=(str(directives_path),)) as pool:
        pending: dict = {}
        it = iter(unique)
        exhausted = False
        done_n = 0
        while True:
            while not exhausted and len(pending) < window:
                sha = next(it, None)
                if sha is None:
                    exhausted = True
                    break
                data = reader.read(sha)
                if blob_sha1(data) != sha:
                    raise SystemExit(f"blob sha mismatch for {sha} ({unique[sha]})")
                pending[pool.submit(check_blob, sha, data, str(cache / f"{sha}.py"))] = sha
            if not pending:
                break
            done, _ = cf.wait(list(pending), return_when=cf.FIRST_COMPLETED)
            for fut in done:
                sha = pending.pop(fut)
                r = fut.result()
                ast_results[sha] = r
                if not r["ok"]:
                    n_bad += 1
                done_n += 1
                if done_n % 2000 == 0:
                    log(f"  {done_n}/{len(unique)} blobs re-verified")
    reader.close()
    t_ast = time.time() - t0
    log(f"astcheck phase done in {t_ast:.1f}s: {len(unique)} unique blobs, {n_bad} failures, "
        f"{sum(1 for r in ast_results.values() if r['identity'])} identity")

    # per instance
    rows = []
    for inst in instances:
        row = process_instance(inst, snaps[inst["instance_id"]], mirror, cache, ast_results,
                               directives_sha, stripper_ver, args.force, not args.no_tag)
        rows.append(row)
        log(f"{inst['instance_id']}: gate={'PASS' if row['gate_passed'] else 'FAIL'} "
            f"changed={row['files_changed']} identity={row['files_identity']} "
            f"commit={(row['nc_commit'] or '-')[:12]} tag={row['tag_action']} "
            f"({row['seconds']}s)" + (f" :: {row['failure_detail'][0][:160]}" if row["failure_detail"] else ""))

    # worktree sanity checks
    wt_results = []
    if args.worktree_check:
        by_id = {r["instance_id"]: r for r in rows}
        inst_by_id = {i["instance_id"]: i for i in instances}
        for iid in args.worktree_check:
            if iid not in by_id:
                sys.exit(f"--worktree-check: {iid} not among processed instances")
            res = worktree_check(mirror, inst_by_id[iid], by_id[iid], jobs)
            wt_results.append(res)
            log(f"worktree check {iid}: ok={res['ok']} py_files={res['py_files']} "
                f"parse_failures={len(res['parse_failures'])} "
                f"preexisting={len(res['preexisting_parse_errors'])} diff='{res['diff_stat_tail']}' "
                f"({res['seconds']}s) {res['error'] or ''}")

    # per repo + report
    per_repo = []
    for repo in sorted({r["repo"] for r in rows}):
        rr = [r for r in rows if r["repo"] == repo]
        agg = {k: sum((r["stats"] or {}).get(k, 0) for r in rr) for k in STAT_KEYS + ("parse_errors",)}
        per_repo.append({"repo": repo, "instances": len(rr),
                         "gate_passed": sum(r["gate_passed"] for r in rr),
                         "tags_created": sum(r["tag_action"] == "created" for r in rr),
                         "tags_unchanged": sum(r["tag_action"] == "unchanged" for r in rr),
                         "tags_forced": sum((r["tag_action"] or "").startswith("forced") for r in rr),
                         "gate_failures": sum(not r["gate_passed"] for r in rr),
                         "files_selected": sum(r["files_selected"] for r in rr),
                         "files_changed": sum(r["files_changed"] or 0 for r in rr),
                         "files_identity": sum(r["files_identity"] or 0 for r in rr),
                         "blob_refs_stats": agg})
    pass1 = json.loads(PASS1_REPORT.read_text()) if PASS1_REPORT.exists() else None
    pass1_summary = None
    if pass1:
        t = pass1["totals_unique"]
        refs = pass1["blob_refs"]
        hits = sum(r["hits"] for r in pass1["per_instance"])
        pass1_summary = {
            "generated_at": pass1["generated_at"], "instances": pass1["instances"],
            "blob_refs": refs, "unique_blobs": pass1["unique_blobs"],
            "cache_hit_rate_over_refs": round(hits / refs, 4) if refs else None,
            "reuse_rate_unique_over_refs": round(1 - pass1["unique_blobs"] / refs, 4) if refs else None,
            "totals_unique": {k: t[k] for k in ("files", "comments_removed", "docstrings_removed",
                                                "doctest_docstrings_kept", "directives_kept",
                                                "stray_strings_kept", "unresolved", "parse_errors",
                                                "astcheck_failures", "errors", "has_doc",
                                                "bytes_before", "bytes_after", "lines_before",
                                                "lines_after")},
            "per_repo": [{k: r[k] for k in ("repo", "instances", "unique_blobs", "blob_refs",
                                            "reuse_rate", "comments_removed", "docstrings_removed",
                                            "doctest_docstrings_kept", "directives_kept",
                                            "stray_strings_kept", "unresolved", "parse_errors",
                                            "astcheck_failures", "errors", "bytes_before",
                                            "bytes_after")} for r in pass1["per_repo"]],
            "manifest": pass1["manifest"],
        }
    tags = git_out(mirror, "for-each-ref", "--format=%(refname:short) %(objectname) %(objecttype)",
                   "refs/tags").splitlines()
    tag_list = git_out(mirror, "tag", "-l", f"*{TAG_SUFFIX}").splitlines()
    wall = time.time() - t0
    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "wall_seconds": round(wall, 1), "astcheck_seconds": round(t_ast, 1), "jobs": jobs,
        "mirror": str(mirror), "cache": str(cache),
        "directives_sha256": directives_sha, "stripper_version": stripper_ver,
        "commit_identity": COMMIT_ENV, "force": bool(args.force), "only": args.only or None,
        "instances": len(rows),
        "gate_passed": sum(r["gate_passed"] for r in rows),
        "gate_failed": sum(not r["gate_passed"] for r in rows),
        "tags_created": sum(r["tag_action"] == "created" for r in rows),
        "tags_unchanged": sum(r["tag_action"] == "unchanged" for r in rows),
        "tags_forced": sum((r["tag_action"] or "").startswith("forced") for r in rows),
        "tags_refused": sum((r["tag_action"] or "").startswith("refused") for r in rows),
        "unique_blobs_verified": len(unique),
        "unique_blobs_astcheck_failures": n_bad,
        "unique_blobs_identity": sum(1 for r in ast_results.values() if r["identity"]),
        "per_repo": per_repo,
        "per_instance": rows,
        "worktree_checks": wt_results,
        "pass1": pass1_summary,
        "refs_tags": tags,
        "nc_tags": tag_list,
    }
    REPORT_JSON.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_MD.write_text(render_md(report), encoding="utf-8")
    log(f"done in {wall:.1f}s: {report['gate_passed']}/{len(rows)} passed, tags created "
        f"{report['tags_created']}, unchanged {report['tags_unchanged']}, forced {report['tags_forced']}, "
        f"refused {report['tags_refused']}; {len(tag_list)} *{TAG_SUFFIX} tags in mirror")
    bad_wt = [w for w in wt_results if not w["ok"]]
    return 1 if report["gate_failed"] or report["tags_refused"] or bad_wt else 0


def _fmt(n) -> str:
    if isinstance(n, bool) or n is None:
        return {True: "yes", False: "NO", None: "-"}[n]
    if isinstance(n, float):
        return f"{n:.1%}" if n <= 1 else f"{n:,.1f}"
    if isinstance(n, int):
        return f"{n:,}"
    return str(n)


def render_md(rep: dict) -> str:
    L = []
    L.append("# Pass 2 report (-nc commits and tags)\n")
    L.append(f"Generated {rep['generated_at']} · wall {rep['wall_seconds']} s (astcheck {rep['astcheck_seconds']} s) · "
             f"jobs {rep['jobs']} · directives sha256 `{rep['directives_sha256'][:12]}` · "
             f"stripper `{rep['stripper_version'][:12]}` · mirror `{rep['mirror']}`\n")
    L.append(f"Instances {rep['instances']} · gate passed {rep['gate_passed']} · gate failed {rep['gate_failed']} · "
             f"tags created {rep['tags_created']} · unchanged {rep['tags_unchanged']} · forced {rep['tags_forced']} · "
             f"refused {rep['tags_refused']} · unique blobs re-verified {_fmt(rep['unique_blobs_verified'])} "
             f"(astcheck failures {rep['unique_blobs_astcheck_failures']}, identity {_fmt(rep['unique_blobs_identity'])})\n")
    ce = rep["commit_identity"]
    L.append(f"Commit identity: `{ce['GIT_AUTHOR_NAME']} <{ce['GIT_AUTHOR_EMAIL']}>` at `{ce['GIT_AUTHOR_DATE']}` "
             f"(author = committer; deterministic shas).\n")
    L.append("## Per instance\n")
    L.append("| instance | base | -nc commit | tag | action | selected | changed | identity | comments removed | "
             "docstrings removed | doctest kept | directives kept | AST ok | unresolved | parse errors | "
             "tests untouched | tree complete | failure |")
    L.append("|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|---|---|")
    for r in rep["per_instance"]:
        g = r["gate"]
        st = r["stats"] or {}
        L.append(f"| {r['instance_id']} | `{r['base_commit'][:12]}` | "
                 f"`{(r['nc_commit'] or '-')[:12]}` | `{r['tag']}` | {r['tag_action'] or 'none'} | "
                 f"{_fmt(r['files_selected'])} | {_fmt(r['files_changed'])} | {_fmt(r['files_identity'])} | "
                 f"{_fmt(st.get('comments_removed'))} | {_fmt(st.get('docstrings_removed'))} | "
                 f"{_fmt(st.get('doctest_docstrings_kept'))} | {_fmt(st.get('directives_kept'))} | "
                 f"{_fmt(g['ast_ok'])} | {_fmt(g['unresolved'])} | {_fmt(g['parse_errors'])} | "
                 f"{_fmt(g['tests_untouched'])} | {_fmt(g['tree_complete'])} | "
                 f"{'; '.join(r['failure_detail'])[:200] if r['failure_detail'] else ''} |")
    L.append("\n## Per repo\n")
    L.append("| repo | instances | gate passed | tags created | unchanged | forced | gate failures | selected | "
             "changed | identity | comments removed | docstrings removed | doctest kept | directives kept | "
             "stray kept | unresolved | parse errors |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rep["per_repo"]:
        s = r["blob_refs_stats"]
        L.append(f"| {r['repo']} | {r['instances']} | {r['gate_passed']} | {r['tags_created']} | "
                 f"{r['tags_unchanged']} | {r['tags_forced']} | {r['gate_failures']} | "
                 f"{_fmt(r['files_selected'])} | {_fmt(r['files_changed'])} | {_fmt(r['files_identity'])} | "
                 f"{_fmt(s['comments_removed'])} | {_fmt(s['docstrings_removed'])} | "
                 f"{_fmt(s['doctest_docstrings_kept'])} | {_fmt(s['directives_kept'])} | "
                 f"{_fmt(s['stray_strings_kept'])} | {_fmt(s['unresolved'])} | {_fmt(s['parse_errors'])} |")
    fails = [r for r in rep["per_instance"] if r["failure_detail"]]
    L.append("\n## Gate failures\n")
    if not fails:
        L.append("None.\n")
    for r in fails:
        L.append(f"- **{r['instance_id']}**: " + " / ".join(r["failure_detail"]))
    if rep["worktree_checks"]:
        L.append("\n## Worktree sanity checks\n")
        L.append("| instance | tag | ok | .py files parsed | parse failures (changed files) | "
                 "pre-existing parse errors (unchanged files) | diff --stat tail | seconds | error |")
        L.append("|---|---|---|---:|---:|---|---|---:|---|")
        for w in rep["worktree_checks"]:
            pre = "; ".join(f"{p} ({e[:40]})" for p, e in w["preexisting_parse_errors"][:5]) or "-"
            L.append(f"| {w['instance_id']} | `{w['tag']}` | {_fmt(w['ok'])} | {_fmt(w['py_files'])} | "
                     f"{len(w['parse_failures'])} | {pre} | {w['diff_stat_tail'] or ''} | {w['seconds']} | "
                     f"{w['error'] or ''} |")
    p1 = rep.get("pass1")
    if p1:
        t = p1["totals_unique"]
        L.append("\n## Stripping numbers carried over from pass 1 (unique blobs)\n")
        L.append(f"Pass 1 generated {p1['generated_at']} · instances {p1['instances']} · blob refs {_fmt(p1['blob_refs'])} · "
                 f"unique blobs {_fmt(p1['unique_blobs'])} · cache hit rate over refs {_fmt(p1['cache_hit_rate_over_refs'])} · "
                 f"reuse (1 - unique/refs) {_fmt(p1['reuse_rate_unique_over_refs'])}\n")
        L.append("| files | comments removed | docstrings removed | doctest kept | directives kept | stray kept | "
                 "unresolved | parse errors | AST failures | errors | bytes before | bytes after | lines before | lines after |")
        L.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        L.append("| " + " | ".join(_fmt(t[k]) for k in ("files", "comments_removed", "docstrings_removed",
                 "doctest_docstrings_kept", "directives_kept", "stray_strings_kept", "unresolved", "parse_errors",
                 "astcheck_failures", "errors", "bytes_before", "bytes_after", "lines_before", "lines_after")) + " |\n")
        L.append("| repo | inst | unique blobs | blob refs | reuse | comments removed | docstrings removed | doctest kept | "
                 "directives kept | stray kept | unresolved | parse errors | AST failures | bytes before | bytes after |")
        L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for r in p1["per_repo"]:
            L.append(f"| {r['repo']} | {r['instances']} | {_fmt(r['unique_blobs'])} | {_fmt(r['blob_refs'])} | "
                     f"{_fmt(r['reuse_rate'])} | {_fmt(r['comments_removed'])} | {_fmt(r['docstrings_removed'])} | "
                     f"{_fmt(r['doctest_docstrings_kept'])} | {_fmt(r['directives_kept'])} | {_fmt(r['stray_strings_kept'])} | "
                     f"{_fmt(r['unresolved'])} | {_fmt(r['parse_errors'])} | {_fmt(r['astcheck_failures'] + r['errors'])} | "
                     f"{_fmt(r['bytes_before'])} | {_fmt(r['bytes_after'])} |")
    L.append("\n## refs/tags in the mirror\n")
    L.append("```")
    L.extend(rep["refs_tags"] or ["(none)"])
    L.append("```")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instances", default=str(DEFAULT_INSTANCES))
    ap.add_argument("--mirror", default=str(DEFAULT_MIRROR))
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--directives", default=str(DEFAULT_DIRECTIVES))
    ap.add_argument("--only", nargs="*", default=None, help="instance ids to process")
    ap.add_argument("--force", action="store_true", help="move an existing -nc tag that points elsewhere")
    ap.add_argument("--no-tag", action="store_true", help="build, gate and commit but do not tag")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--worktree-check", nargs="*", default=None,
                    help="after tagging, check these instances out into a temp worktree, "
                         "ast.parse every .py, then remove the worktree")
    args = ap.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
