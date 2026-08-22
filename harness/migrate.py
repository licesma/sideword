"""Convert an existing repository to Sideword.

    .venv/bin/python -m harness.migrate <repo>                 # in place
    .venv/bin/python -m harness.migrate <repo> --out <dir>     # to a copy
    .venv/bin/python -m harness.migrate <repo> --check         # verify only, write nothing
    .venv/bin/python -m harness.migrate <repo> --report out.json

Every `.py` becomes the three artifacts of `FORMAT.md`: clean source in place of
the original, plus `.sideword/<relpath>.idx` and `.sideword/<relpath>.md` in a
mirror tree. Everything else in the repo is left exactly as it is.

This is the *mechanical* migration — no model. Comments already sit next to the
code they describe, so their anchor is a question about position, which
`harness/anchoring.py` answers deterministically. The model is needed only where
that position is ambiguous, which is the converter arm's problem, not this one.

Two invariants are checked per file, and a file that fails either is left
untouched:

* **the code is unchanged** — the clean source is AST-equal to the original,
  with the `# noqa` / `# type: ignore` family still in place (`FORMAT.md` §2);
* **no prose is lost** — every documentation block is either in the sidedoc or
  reported unanchorable. `FORMAT.md` §6 is explicit that nothing is dropped
  silently, and a migration is exactly where that would happen unnoticed.

Byte-exact reconstruction is *not* required, and mostly will not hold: §3 is
normative about how a record renders, so a comment written `#no space` comes
back as `# no space`. That is a rendering convention, not a loss.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import os
import sys
import traceback
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import anchoring, astcheck, inline, paths, roundtrip, sidedoc, strip
from harness import directives as directives_mod

SIDEWORD_DIR = ".sideword"
SKIP_DIRS = {".git", ".hg", ".svn", ".tox", ".venv", "venv", "node_modules",
             "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
             "build", "dist", SIDEWORD_DIR}


def log(*a: object) -> None:
    print(*a, file=sys.stderr, flush=True)


def python_files(root: Path, include_tests: bool) -> list[Path]:
    """Every `.py` under `root`, minus the directories nobody means to convert.

    Test files are skipped by default: they are the experiment's control surface
    and `harness/paths.py` already owns that rule."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if not include_tests and paths.is_test_path(rel):
                continue
            out.append(path)
    return out


def prose(sidecar, source: bytes) -> list[str]:
    lines = strip.split_lines(anchoring._decode(source))
    return [t for t in roundtrip.documentation(sidecar, lines) if t]


def convert_one(original: bytes, rel: str, directives) -> dict:
    """The three artifacts for one file, plus the two verdicts that gate writing."""
    art = anchoring.convert(original, directives)
    clean, anchored = art["source"], art["anchored"]
    index_text = sidedoc.write_index(rel, art["records"], art["sidedoc"])

    code_ok, code_detail = astcheck.equal(original, clean, directives)

    # Reconstruct and re-strip: the prose has to be findable in the inline view,
    # not merely present in the sidedoc.
    entries = anchoring.resolver.index_text(anchoring._decode(clean))
    rebuilt, _ = inline.reconstruct(clean, art["sidedoc"], entries=entries)
    _, resid = strip.strip_source(rebuilt, directives)

    declared = {roundtrip.doc_text(u["kind"], u.get("text", "")) for u in anchored.unanchorable}
    haystack = roundtrip._squash(" \0 ".join(prose(resid, rebuilt)))
    dropped = [t for t in prose(art["sidecar"], original)
               if t not in declared and roundtrip._squash(t) not in haystack]

    return {
        "rel": rel,
        "bytes": len(original),
        "records": len(art["records"]),
        "unanchorable": len(anchored.unanchorable),
        "unanchorable_reasons": collections.Counter(u["reason"] for u in anchored.unanchorable),
        "code_ok": code_ok,
        "code_detail": "" if code_ok else code_detail,
        "dropped": dropped,
        "exact": rebuilt == original,
        "clean": clean,
        "index": index_text,
        "sidedoc": art["sidedoc"],
    }


def _worker(args) -> dict:
    root, rel, out_root, check, directives_path = args
    directives = (directives_mod.load(directives_path) if directives_path
                  else directives_mod.load())
    source = (Path(root) / rel)
    try:
        result = convert_one(source.read_bytes(), rel, directives)
    except Exception as exc:  # noqa: BLE001 — one bad file must not stop a repo
        return {"rel": rel, "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc(limit=3)}

    result["written"] = False
    if not check and result["code_ok"] and not result["dropped"]:
        write(Path(out_root), rel, result)
        result["written"] = True
    for key in ("clean", "index", "sidedoc"):
        result.pop(key)
    return result


def write(out_root: Path, rel: str, result: dict) -> None:
    target = out_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(result["clean"])
    mirror = out_root / SIDEWORD_DIR / rel
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.with_suffix(mirror.suffix + ".idx").write_text(result["index"], encoding="utf-8")
    mirror.with_suffix(mirror.suffix + ".md").write_text(result["sidedoc"], encoding="utf-8")


def copy_tree(root: Path, out: Path) -> None:
    """Everything that is not a `.py` we convert: data files, configs, licences."""
    import shutil
    if out.exists():
        raise SystemExit(f"--out {out} already exists; refusing to overwrite")
    shutil.copytree(root, out, ignore=shutil.ignore_patterns(*SKIP_DIRS))


def summarise(results: list[dict]) -> dict:
    ok = [r for r in results if "error" not in r]
    failed_code = [r for r in ok if not r["code_ok"]]
    lost = [r for r in ok if r["dropped"]]
    reasons: collections.Counter = collections.Counter()
    for r in ok:
        reasons.update(r["unanchorable_reasons"])
    return {
        "files": len(results),
        "converted": sum(1 for r in ok if r.get("written")),
        "errors": len(results) - len(ok),
        "code_changed": len(failed_code),
        "files_losing_prose": len(lost),
        "records": sum(r["records"] for r in ok),
        "unanchorable": sum(r["unanchorable"] for r in ok),
        "byte_exact": sum(1 for r in ok if r["exact"]),
        "unanchorable_reasons": dict(reasons.most_common()),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("repo", help="repository root")
    ap.add_argument("--out", default=None,
                    help="write a converted copy here instead of converting in place")
    ap.add_argument("--check", action="store_true",
                    help="verify only; write nothing")
    ap.add_argument("--include-tests", action="store_true",
                    help="convert test files too (skipped by default)")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 1))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--directives", default=None)
    ap.add_argument("--report", default=None, help="write the per-file JSON report here")
    args = ap.parse_args(argv)

    root = Path(args.repo).resolve()
    if not root.is_dir():
        raise SystemExit(f"{root} is not a directory")

    files = python_files(root, args.include_tests)
    if args.limit:
        files = files[:args.limit]
    if not files:
        raise SystemExit("no .py files to convert")

    out_root = root
    if args.out and not args.check:
        out_root = Path(args.out).resolve()
        copy_tree(root, out_root)
    log(f"{len(files)} files{' (check only)' if args.check else ''} -> {out_root}")

    rels = [f.relative_to(root).as_posix() for f in files]
    work = [(str(root), rel, str(out_root), args.check, args.directives) for rel in rels]
    results: list[dict] = []
    with cf.ProcessPoolExecutor(max_workers=args.jobs) as ex:
        for i, result in enumerate(ex.map(_worker, work, chunksize=8), 1):
            results.append(result)
            if i % 200 == 0:
                log(f"  {i}/{len(files)}")

    summary = summarise(results)
    if args.report:
        Path(args.report).write_text(json.dumps({"summary": summary, "results": results}, indent=1,
                                                default=str))
    print(json.dumps(summary, indent=1))

    for result in results:
        if "error" in result:
            log(f"ERROR {result['rel']}: {result['error']}")
        elif not result["code_ok"]:
            log(f"CODE CHANGED {result['rel']}: {result['code_detail'][:200]}")
        elif result["dropped"]:
            log(f"PROSE LOST {result['rel']}: {result['dropped'][:2]}")

    bad = summary["errors"] + summary["code_changed"] + summary["files_losing_prose"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
