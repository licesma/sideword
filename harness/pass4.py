"""Pass 4: materialize one ``-sw`` commit per instance in the mirror and tag it, gated.

Arm 2 of the experiment.  The tree is ``-nc``'s tree plus a parallel documentation
tree: every selected non-test ``.py`` path carries the *same stripped blob* the
``-nc`` tag carries, and gains two siblings under ``.sideword/``::

    src/cart.py     ->  .sideword/src/cart.py.md    the sidedoc (FORMAT.md §5)
                        .sideword/src/cart.py.idx   the index   (FORMAT.md §4)

Both come straight from pass 3's content-addressed cache (``cache/<sha>.sw.md`` and
``cache/<sha>.sw.idx``).  The only edit pass 4 makes is to the index header: pass 3
converts a blob once, under whichever path it was first seen at, so a blob shared by
several paths carries the wrong path in its header.  The header's path field is
rewritten to the path the file actually sits at; nothing else in either artifact is
touched.

Git plumbing only -- the mirror's working tree and its real index are never touched::

    GIT_INDEX_FILE=<tmp> git read-tree <base_commit>
    git hash-object -w --no-filters --stdin-paths      (cache files -> blob shas)
    GIT_INDEX_FILE=<tmp> git update-index -z --index-info    (mode SP sha TAB path)
    GIT_INDEX_FILE=<tmp> git write-tree
    git commit-tree <tree> -p <base_commit>            (pass 2's fixed identity)
    git tag <instance_id>-sw <commit>                  (lightweight, never overwritten
                                                        without --force)

A tree that fails any gate is never committed and the failure is reported:

    0. cache complete: cache/<sha>.py, cache/<sha>.sw.md and cache/<sha>.sw.idx all
       readable for every selected blob, and every index header parses.
    1. astcheck.equal(orig, stripped) for every selected path -- pass 2's check,
       re-run here over the same unique blobs, and the sidecars' unresolved == 0.
    2. Test paths untouched: every diff entry is either a modification of a selected
       non-test path or an addition of one of the .sideword/ files we meant to add;
       every test_patch_path (and every test path in the base tree) resolves to the
       same blob in both trees.
    3. The tree's path set == base_commit's path set + exactly the .sideword/ files
       added -- nothing else added, removed or renamed, and non-selected entries are
       byte-identical including mode.
    4. Every .sideword/*.md and .sideword/*.idx corresponds to a selected path that is
       present in the tree, and every selected path has both.
    5. -sw and -nc agree on the code: outside .sideword/, the two trees are entry-for-
       entry identical.  A differing .py blob means the arms are not comparable, which
       is a hard failure.

Author/committer are pass 2's ``sideword <sideword@localhost>`` at a fixed date, so a
rerun produces byte-identical commit shas and finds every tag already correct
(``tag_action == "unchanged"``).

Writes corpus/pass4-report.json and corpus/pass4-report.md.

CLI::

    uv run python -m harness.pass4 [--instances corpus/instances.json]
        [--mirror ~/repos/sideword-corpus] [--cache cache/]
        [--directives corpus/directives.toml] [--only <id>...] [--force]
        [--jobs N] [--worktree-check <id>...] [--no-tag]
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures as cf
import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tokenize
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
    from harness import directives as directives_mod, paths as paths_mod
    from harness.pass1 import (CatFile, blob_sha1, log, sha256_file, stripper_version, STAT_KEYS)
    from harness.pass2 import (COMMIT_ENV, check_blob, diff_tree, git, git_out, read_sidecar_stats,
                               tree_entries, _w_init)
else:
    from . import directives as directives_mod, paths as paths_mod
    from .pass1 import CatFile, blob_sha1, log, sha256_file, stripper_version, STAT_KEYS
    from .pass2 import (COMMIT_ENV, check_blob, diff_tree, git, git_out, read_sidecar_stats,
                        tree_entries, _w_init)

DEFAULT_INSTANCES = ROOT / "corpus" / "instances.json"
DEFAULT_MIRROR = Path.home() / "repos" / "sideword-corpus"
DEFAULT_CACHE = ROOT / "cache"
DEFAULT_DIRECTIVES = ROOT / "corpus" / "directives.toml"
SNAPSHOT_DIR = ROOT / "corpus" / "snapshots"
PASS3_REPORT = ROOT / "corpus" / "pass3-report.json"
REPORT_JSON = ROOT / "corpus" / "pass4-report.json"
REPORT_MD = ROOT / "corpus" / "pass4-report.md"

TAG_SUFFIX = "-sw"
NC_SUFFIX = "-nc"
SIDEWORD_DIR = ".sideword"
SIDEWORD_MODE = "100644"
FORMAT_VERSION = "sideword/1"

#: ``sideword/1  <path>  <n> records  ~<t> tok`` -- the index header (FORMAT.md §4).
_IDX_HEADER = re.compile(
    rb"^" + re.escape(FORMAT_VERSION.encode()) + rb"  (?P<path>.+)  "
    rb"(?P<records>\d+) records?  ~(?P<tokens>\d+) tok$")


def md_path(path: str) -> str:
    return f"{SIDEWORD_DIR}/{path}.md"


def idx_path(path: str) -> str:
    return f"{SIDEWORD_DIR}/{path}.idx"


def source_of(sideword_path: str) -> str | None:
    """``.sideword/src/cart.py.md`` -> ``src/cart.py``; None if it is not one of ours."""
    if not sideword_path.startswith(SIDEWORD_DIR + "/"):
        return None
    rest = sideword_path[len(SIDEWORD_DIR) + 1:]
    for suffix in (".md", ".idx"):
        if rest.endswith(suffix):
            return rest[: -len(suffix)]
    return None


def retarget_index(data: bytes, path: str) -> tuple[bytes, int, int]:
    """Rewrite the index header's path field.  Raises ValueError on an unparsable header.

    Returns (bytes, records, token estimate).  Byte-identical output when the header
    already names ``path``, which is the common case -- pass 3 converts a blob under the
    first path it was seen at, and only 105 of 11,609 blobs live at more than one.
    """
    head, sep, tail = data.partition(b"\n")
    m = _IDX_HEADER.match(head)
    if not m:
        raise ValueError(f"index header does not parse: {head[:120]!r}")
    records, tokens = int(m["records"]), int(m["tokens"])
    if m["path"] == path.encode():
        return data, records, tokens
    word = "record" if records == 1 else "records"
    new = (f"{FORMAT_VERSION}  {path}  {records} {word}  ~{tokens} tok").encode()
    return new + sep + tail, records, tokens


# ---- artifact preparation ------------------------------------------------------------------
def hash_objects(mirror: Path, files: list[Path]) -> list[str]:
    """``git hash-object -w`` a batch of files, in order."""
    if not files:
        return []
    stdin = "".join(str(p) + "\n" for p in files).encode()
    out = git(mirror, "hash-object", "-w", "--no-filters", "--stdin-paths",
              input=stdin).stdout.decode().split()
    if len(out) != len(files):
        raise SystemExit(f"hash-object returned {len(out)} shas for {len(files)} paths")
    return out


def prepare_artifacts(mirror: Path, cache: Path, unique_shas: list[str],
                      pairs: list[tuple[str, str]], tmpdir: Path) -> dict:
    """Write every sidedoc and index into the mirror's object db.

    ``pairs`` is every distinct (blob sha, path) the corpus references; the sidedoc is
    content-addressed by sha alone, the index by (sha, path) because of the header.
    """
    res = {"md_sha": {}, "idx_sha": {}, "idx_meta": {}, "md_bytes": {}, "idx_bytes": {},
           "missing_md": [], "missing_idx": [], "bad_header": [], "mismatch": []}

    # -- sidedocs: one blob per cached sha, hashed straight out of the cache -------------
    md_files, md_shas, want = [], [], {}
    for sha in unique_shas:
        p = cache / f"{sha}.sw.md"
        try:
            data = p.read_bytes()
        except OSError as e:
            res["missing_md"].append((sha, str(e)))
            continue
        md_files.append(p)
        md_shas.append(sha)
        want[sha] = blob_sha1(data)
        res["md_bytes"][sha] = len(data)
    got = hash_objects(mirror, md_files)
    for sha, g in zip(md_shas, got):
        if g != want[sha]:
            res["mismatch"].append(("md", sha, g, want[sha]))
        else:
            res["md_sha"][sha] = g

    # -- indexes: retargeted per path, deduplicated by content ---------------------------
    raw: dict[str, bytes] = {}
    by_content: dict[str, Path] = {}          # content sha -> a file holding those bytes
    pending: list[tuple[tuple[str, str], str]] = []
    for sha, path in pairs:
        if sha not in raw:
            try:
                raw[sha] = (cache / f"{sha}.sw.idx").read_bytes()
            except OSError as e:
                res["missing_idx"].append((sha, str(e)))
                raw[sha] = b""
        data = raw[sha]
        if not data:
            continue
        try:
            out, records, tokens = retarget_index(data, path)
        except ValueError as e:
            res["bad_header"].append((sha, path, str(e)))
            continue
        content = blob_sha1(out)
        res["idx_meta"][(sha, path)] = {"records": records, "tokens": tokens}
        res["idx_bytes"][(sha, path)] = len(out)
        pending.append(((sha, path), content))
        if content not in by_content:
            if out is data:
                by_content[content] = cache / f"{sha}.sw.idx"      # unchanged: hash in place
            else:
                f = tmpdir / f"{content}.idx"
                f.write_bytes(out)
                by_content[content] = f
    raw.clear()
    contents = list(by_content)
    got = hash_objects(mirror, [by_content[c] for c in contents])
    ok = set()
    for c, g in zip(contents, got):
        if g != c:
            res["mismatch"].append(("idx", c, g, c))
        else:
            ok.add(c)
    for key, content in pending:
        if content in ok:
            res["idx_sha"][key] = content
    return res


# ---- per instance --------------------------------------------------------------------------
def commit_message(inst: dict, snap: dict, agg: dict, counts: dict, nc_commit: str,
                   directives_sha: str, stripper_ver: str) -> str:
    return "\n".join([
        f"sideword -sw: {inst['instance_id']}",
        "",
        "Comments and docstrings moved out of every non-test .py file into .sideword/",
        "(FORMAT.md §4-§5).  The .py sources are byte-identical to the -nc tag's.",
        "",
        f"repo: {inst['repo']}",
        f"base_commit: {inst['base_commit']}",
        f"nc_commit: {nc_commit}",
        f"sidedoc_format: {FORMAT_VERSION}",
        f"directives_sha256: {directives_sha}",
        f"stripper_version: {stripper_ver}",
        f"files_stripped: {snap['selected']}",
        f"files_changed: {counts['files_changed']}",
        f"files_identity: {counts['files_identity']}",
        f"sidedocs_added: {counts['sidedocs_added']}",
        f"indexes_added: {counts['indexes_added']}",
        f"records: {counts['records']}",
        f"sidedoc_bytes: {counts['sidedoc_bytes']}",
        f"index_bytes: {counts['index_bytes']}",
        f"comments_removed: {agg['comments_removed']}",
        f"docstrings_removed: {agg['docstrings_removed']}",
        f"doctest_docstrings_kept: {agg['doctest_docstrings_kept']}",
        f"directives_kept: {agg['directives_kept']}",
        f"stray_strings_kept: {agg['stray_strings_kept']}",
        f"unresolved: {agg['unresolved']}",
        f"parse_errors: {agg['parse_errors']}",
        "",
    ])


def process_instance(inst: dict, snap: dict, mirror: Path, cache: Path, ast_results: dict,
                     art: dict, directives_sha: str, stripper_ver: str, force: bool,
                     do_tag: bool) -> dict:
    iid = inst["instance_id"]
    base = inst["base_commit"]
    tag = f"{iid}{TAG_SUFFIX}"
    nc_tag = f"{iid}{NC_SUFFIX}"
    t0 = time.time()
    row = {"instance_id": iid, "repo": inst["repo"], "base_commit": base, "tag": tag,
           "nc_tag": nc_tag, "nc_commit": None, "sw_tree": None, "sw_commit": None,
           "files_selected": snap["selected"], "files_changed": None, "files_identity": None,
           "sidedocs_added": 0, "indexes_added": 0, "records": 0, "empty_sidedocs": 0,
           "index_headers_retargeted": 0, "sidedoc_bytes": 0, "index_bytes": 0,
           "sidedoc_tokens": 0,
           "gate": {"cache_complete": None, "ast_ok": None, "unresolved": None,
                    "parse_errors": None, "tests_untouched": None, "tree_complete": None,
                    "sideword_pairs": None, "nc_agrees": None},
           "gate_passed": False, "tagged": False, "tag_action": None, "failure_detail": [],
           "stats": None, "seconds": None}
    fail = row["failure_detail"]
    files = snap["files"]
    test_extra = set(snap.get("test_patch_paths") or inst.get("test_patch_paths") or [])
    selected_paths = {f["path"] for f in files}

    # -- gate 0: the cache has all three artifacts for every selected blob ---------------
    cache_missing, md_missing, idx_missing = [], [], []
    ast_bad = []
    identity = 0
    for f in files:
        sha, path = f["blob_sha"], f["path"]
        r = ast_results.get(sha)
        if r is None or r["stripped_sha"] is None:
            cache_missing.append(path)
        else:
            if not r["ok"]:
                ast_bad.append((path, sha, r["detail"][:500]))
            if r["identity"]:
                identity += 1
        if sha not in art["md_sha"]:
            md_missing.append(path)
        if (sha, path) not in art["idx_sha"]:
            idx_missing.append(path)
    row["files_identity"] = identity
    row["gate"]["cache_complete"] = not (cache_missing or md_missing or idx_missing)
    row["gate"]["ast_ok"] = not ast_bad and not cache_missing
    if cache_missing:
        fail.append(f"cache incomplete: {len(cache_missing)} selected blobs without a readable "
                    f"cache/<sha>.py (e.g. {cache_missing[:3]})")
    if md_missing:
        fail.append(f"{len(md_missing)} selected paths without a usable cache/<sha>.sw.md "
                    f"(e.g. {md_missing[:3]}): run pass 3")
    if idx_missing:
        fail.append(f"{len(idx_missing)} selected paths without a usable cache/<sha>.sw.idx "
                    f"(e.g. {idx_missing[:3]}): run pass 3")
    if ast_bad:
        fail.append(f"astcheck failed for {len(ast_bad)} files: "
                    + "; ".join(f"{p} ({s[:10]}): {d.splitlines()[0] if d else ''}"
                                for p, s, d in ast_bad[:5]))

    # -- gate 1b: sidecar stats (pass 2's contract, carried into the commit message) ------
    agg = {k: 0 for k in STAT_KEYS}
    agg["parse_errors"] = 0
    agg["files"] = len(files)
    parse_error_paths, sidecar_errors = [], []
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

    # -- documentation totals -------------------------------------------------------------
    for f in files:
        key = (f["blob_sha"], f["path"])
        meta = art["idx_meta"].get(key)
        if meta:
            row["records"] += meta["records"]
            # the header's ~N tok is an estimate of the *sidedoc*, so a retrieval can be
            # budgeted before it is made (FORMAT.md §4) -- not of the index itself.
            row["sidedoc_tokens"] += meta["tokens"]
            if meta["records"] == 0:
                row["empty_sidedocs"] += 1
        row["sidedoc_bytes"] += art["md_bytes"].get(f["blob_sha"], 0)
        row["index_bytes"] += art["idx_bytes"].get(key, 0)

    if fail:
        row["seconds"] = round(time.time() - t0, 2)
        return row

    # -- build the tree in a temporary index -----------------------------------------------
    entries = []
    for f in files:
        sha, path = f["blob_sha"], f["path"]
        entries.append((f["mode"], ast_results[sha]["stripped_sha"], path))
        entries.append((SIDEWORD_MODE, art["md_sha"][sha], md_path(path)))
        entries.append((SIDEWORD_MODE, art["idx_sha"][(sha, path)], idx_path(path)))
    row["sidedocs_added"] = len(files)
    row["indexes_added"] = len(files)
    expected_sideword = {md_path(p) for p in selected_paths} | {idx_path(p) for p in selected_paths}

    with tempfile.TemporaryDirectory(prefix="sideword-pass4-") as td:
        index = os.path.join(td, "index")
        env = {"GIT_INDEX_FILE": index}
        git(mirror, "read-tree", base, env=env)
        info = b"".join(f"{mode} {sha}\t".encode() + path.encode("utf-8", "surrogateescape") + b"\0"
                        for mode, sha, path in entries)
        git(mirror, "update-index", "-z", "--index-info", input=info, env=env)
        tree = git_out(mirror, "write-tree", env=env)
    row["sw_tree"] = tree

    base_entries = tree_entries(mirror, base)
    new_entries = tree_entries(mirror, tree)

    # -- gate 2: test paths untouched --------------------------------------------------------
    changed = diff_tree(mirror, base, tree)
    row["files_changed"] = sum(1 for c in changed if c["status"] == "M")
    problems = []
    for c in changed:
        if c["status"] == "A":
            if c["path"] not in expected_sideword:
                problems.append(f"unexpected addition: {c['path']}")
            continue
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
    for path, ent in base_entries.items():
        if paths_mod.is_test_path(path, extra=test_extra) and new_entries.get(path) != ent:
            problems.append(f"test path differs: {path}")
            if len(problems) > 20:
                break
    row["gate"]["tests_untouched"] = not problems
    if problems:
        fail.append(f"tests_untouched failed ({len(problems)}): " + "; ".join(problems[:10]))

    # -- gate 3: path set is base + exactly the .sideword/ files we added ----------------------
    collision = sorted(expected_sideword & set(base_entries))
    want_paths = set(base_entries) | expected_sideword
    complete = set(new_entries) == want_paths and len(new_entries) == len(want_paths)
    if collision:
        complete = False
        fail.append(f"tree_complete failed: base_commit already carries {len(collision)} of the "
                    f".sideword/ paths ({collision[:3]})")
    if not complete:
        missing = sorted(want_paths - set(new_entries))[:5]
        extra = sorted(set(new_entries) - want_paths)[:5]
        fail.append(f"tree_complete failed: expected {len(want_paths)} entries, got "
                    f"{len(new_entries)}; missing={missing} extra={extra}")
    else:
        for path, ent in base_entries.items():
            if path not in selected_paths and new_entries[path] != ent:
                complete = False
                fail.append(f"tree_complete failed: non-selected entry differs: {path}")
                break
        for f in files:
            path = f["path"]
            nm, nt, ns = new_entries[path]
            if nm != f["mode"] or nt != "blob" or ns != ast_results[f["blob_sha"]]["stripped_sha"]:
                complete = False
                fail.append(f"tree_complete failed: selected entry wrong: {path} "
                            f"({nm} {nt} {ns[:10]})")
                break
    row["gate"]["tree_complete"] = complete

    # -- gate 4: every .sideword/ file names a selected path that is in the tree ---------------
    pair_problems = []
    seen = {"md": set(), "idx": set()}
    for path, (mode, typ, sha) in new_entries.items():
        if not path.startswith(SIDEWORD_DIR + "/"):
            continue
        src = source_of(path)
        if src is None:
            pair_problems.append(f"not a sidedoc or index: {path}")
            continue
        if src not in selected_paths:
            pair_problems.append(f"names a path that is not selected: {path}")
            continue
        if src not in new_entries:
            pair_problems.append(f"names a path absent from the tree: {path}")
            continue
        if typ != "blob" or mode != SIDEWORD_MODE:
            pair_problems.append(f"wrong mode/type {mode} {typ}: {path}")
            continue
        seen["md" if path.endswith(".md") else "idx"].add(src)
    for kind in ("md", "idx"):
        gap = selected_paths - seen[kind]
        if gap:
            pair_problems.append(f"{len(gap)} selected paths without a .{kind} "
                                 f"({sorted(gap)[:3]})")
    row["gate"]["sideword_pairs"] = not pair_problems
    if pair_problems:
        fail.append(f"sideword_pairs failed ({len(pair_problems)}): " + "; ".join(pair_problems[:10]))

    # -- gate 5: -sw and -nc agree on the code -------------------------------------------------
    nc_ref = git(mirror, "rev-parse", "--verify", "-q", f"refs/tags/{nc_tag}", check=False)
    if nc_ref.returncode != 0:
        row["gate"]["nc_agrees"] = False
        fail.append(f"gate 5: tag {nc_tag} does not exist; run pass 2 first")
    else:
        row["nc_commit"] = nc_ref.stdout.decode().strip()
        nc_entries = tree_entries(mirror, f"{row['nc_commit']}^{{tree}}")
        code_only = {p: e for p, e in new_entries.items() if not p.startswith(SIDEWORD_DIR + "/")}
        diffs = []
        for path in sorted(set(code_only) | set(nc_entries)):
            if code_only.get(path) != nc_entries.get(path):
                diffs.append(path)
                if len(diffs) > 20:
                    break
        py_diffs = [p for p in diffs if p in selected_paths]
        row["gate"]["nc_agrees"] = not diffs
        row["nc_code_diffs"] = len(diffs)
        if diffs:
            fail.append(f"gate 5: -sw and -nc disagree outside .sideword/ on {len(diffs)} paths "
                        f"({len(py_diffs)} of them selected .py): {diffs[:5]}")

    if fail:
        row["seconds"] = round(time.time() - t0, 2)
        return row
    row["gate_passed"] = True

    # -- commit + tag ---------------------------------------------------------------------------
    counts = {"files_changed": row["files_changed"], "files_identity": identity,
              "sidedocs_added": row["sidedocs_added"], "indexes_added": row["indexes_added"],
              "records": row["records"], "sidedoc_bytes": row["sidedoc_bytes"],
              "index_bytes": row["index_bytes"]}
    msg = commit_message(inst, snap, agg, counts, row["nc_commit"], directives_sha, stripper_ver)
    commit = git_out(mirror, "commit-tree", tree, "-p", base, "-m", msg, env=COMMIT_ENV)
    row["sw_commit"] = commit
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
            fail.append(f"tag {tag} already exists at {old} != {commit}; rerun with --force")
    else:
        git(mirror, "tag", tag, commit)
        row["tag_action"] = "created"
        row["tagged"] = True
    row["seconds"] = round(time.time() - t0, 2)
    return row


# ---- worktree sanity check ---------------------------------------------------------------------
def _inspect_py(path: str) -> dict:
    """Parse one file and count what documentation is left in the source."""
    out = {"path": path, "parse_error": None, "comments": [], "docstrings": 0, "doctests": 0}
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        out["parse_error"] = str(e)
        return out
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(data)
    except (SyntaxError, ValueError) as e:
        out["parse_error"] = f"{type(e).__name__}: {e}"
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                out["docstrings"] += 1
                if ">>>" in doc:
                    out["doctests"] += 1
    try:
        for tok in tokenize.tokenize(io.BytesIO(data).readline):
            if tok.type == tokenize.COMMENT:
                out["comments"].append((tok.start[0], tok.string))
    except (tokenize.TokenError, SyntaxError, UnicodeDecodeError) as e:
        out["parse_error"] = out["parse_error"] or f"tokenize: {type(e).__name__}: {e}"
    return out


def worktree_check(mirror: Path, inst: dict, row: dict, jobs: int, directives_path: Path) -> dict:
    """Check a -sw commit out for real: clean .py, documentation living in .sideword/."""
    res = {"instance_id": inst["instance_id"], "tag": row["tag"], "ok": False,
           "py_files": 0, "sidedoc_files": 0, "index_files": 0, "changed_py": 0,
           "parse_failures": [], "preexisting_parse_errors": [],
           "comments_left": 0, "comments_not_directives": [], "docstrings_left": 0,
           "doctests_left": 0, "sample": None, "seconds": None, "error": None}
    if not row.get("sw_commit"):
        res["error"] = "no -sw commit"
        return res
    t0 = time.time()
    D = directives_mod.load(directives_path)
    wt = Path(tempfile.mkdtemp(prefix=f"sw-check-{inst['instance_id']}-", dir="/tmp"))
    wt.rmdir()
    try:
        git(mirror, "worktree", "add", "--detach", str(wt), row["sw_commit"])
        head = git_out(wt, "rev-parse", "HEAD")
        if head != row["sw_commit"]:
            res["error"] = f"worktree HEAD {head} != {row['sw_commit']}"
        sideword = wt / SIDEWORD_DIR
        res["sidedoc_files"] = sum(1 for _ in sideword.rglob("*.md")) if sideword.exists() else 0
        res["index_files"] = sum(1 for _ in sideword.rglob("*.idx")) if sideword.exists() else 0
        py = [p for p in wt.rglob("*.py")
              if ".git" not in p.parts and SIDEWORD_DIR not in p.parts]
        res["py_files"] = len(py)
        changed = {c["path"] for c in diff_tree(mirror, inst["base_commit"], row["sw_commit"])
                   if c["status"] == "M"}
        res["changed_py"] = len(changed)
        with cf.ProcessPoolExecutor(max_workers=jobs) as pool:
            for r in pool.map(_inspect_py, [str(p) for p in py], chunksize=32):
                rel = os.path.relpath(r["path"], wt)
                touched = rel in changed
                if r["parse_error"]:
                    (res["parse_failures"] if touched
                     else res["preexisting_parse_errors"]).append((rel, r["parse_error"]))
                if not touched:
                    continue
                res["docstrings_left"] += r["docstrings"]
                res["doctests_left"] += r["doctests"]
                for lineno, text in r["comments"]:
                    res["comments_left"] += 1
                    action, _ = D.classify(text, lineno)
                    if action != directives_mod.KEEP:
                        res["comments_not_directives"].append((rel, lineno, text[:80]))
        # one real file: source clean, documentation present next door
        for rel in sorted(changed):
            md = sideword / (rel + ".md")
            idx = sideword / (rel + ".idx")
            if md.exists() and md.stat().st_size > 400 and idx.exists():
                src = (wt / rel).read_text(encoding="utf-8", errors="replace")
                res["sample"] = {
                    "path": rel, "source_bytes": len(src.encode()),
                    "source_has_hash_comment": "#" in src,
                    "sidedoc_bytes": md.stat().st_size,
                    "index_head": idx.read_text(encoding="utf-8").splitlines()[:3],
                    "sidedoc_head": md.read_text(encoding="utf-8").splitlines()[:8],
                }
                break
        status = git_out(wt, "status", "--porcelain")
        if status:
            res["error"] = (res["error"] or "") + f" worktree not clean: {status[:200]}"
        res["ok"] = (res["error"] is None and not res["parse_failures"]
                     and not res["comments_not_directives"]
                     and res["sidedoc_files"] == row["sidedocs_added"]
                     and res["index_files"] == row["indexes_added"]
                     and res["docstrings_left"] == res["doctests_left"])
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
    directives_mod.load(directives_path)
    directives_sha = sha256_file(directives_path)
    harness_ver = stripper_version()
    manifest_path = cache / "MANIFEST.json"
    if not manifest_path.exists():
        sys.exit(f"{manifest_path} missing: run pass1.py first")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("directives_sha256") != directives_sha:
        sys.exit(f"cache/MANIFEST.json directives_sha256 != sha256({directives_path}): "
                 f"pass 1 is stale, rerun it")
    # The cache's own stripper version, not the running harness's: pass 4 never strips
    # anything, it copies pass 1's bytes, so this is what the -sw commits must record and
    # it is what the -nc commits already record.
    stripper_ver = manifest.get("stripper_version")
    stale_stripper = stripper_ver != harness_ver
    if stale_stripper and not args.allow_stale_stripper:
        sys.exit(f"cache/MANIFEST.json stripper_version {stripper_ver} != current harness "
                 f"{harness_ver}: rerun pass 1 (--reset), or pass --allow-stale-stripper if the "
                 f"edit to strip/directives/astcheck.py was cosmetic.  Pass 4 re-strips nothing, "
                 f"and gate 5 proves the code side byte-for-byte against the -nc tags.")
    if stale_stripper:
        log(f"WARNING: cache stripper_version {stripper_ver[:12]} != running harness "
            f"{harness_ver[:12]}; --allow-stale-stripper given, using the cache's version")
    if git(mirror, "rev-parse", "--git-dir", check=False).returncode != 0:
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

    snaps = {}
    for inst in instances:
        p = SNAPSHOT_DIR / f"{inst['instance_id']}.json"
        if not p.exists():
            sys.exit(f"snapshot missing: {p} (run pass1.py)")
        snap = json.loads(p.read_text(encoding="utf-8"))
        if snap["base_commit"] != inst["base_commit"]:
            sys.exit(f"{p}: base_commit != instances.json")
        if snap.get("directives_sha256") != directives_sha or snap.get("stripper_version") != stripper_ver:
            sys.exit(f"{p}: written for a different directives/stripper version than the cache "
                     f"({snap.get('stripper_version')} vs {stripper_ver}); rerun pass 1")
        snaps[inst["instance_id"]] = snap

    unique: dict[str, str] = {}
    pairs: dict[tuple[str, str], None] = {}
    for inst in instances:
        for f in snaps[inst["instance_id"]]["files"]:
            unique.setdefault(f["blob_sha"], f["path"])
            pairs.setdefault((f["blob_sha"], f["path"]), None)
    log(f"{len(instances)} instances, "
        f"{sum(len(snaps[i['instance_id']]['files']) for i in instances)} blob refs, "
        f"{len(unique)} unique blobs, {len(pairs)} unique (blob, path) pairs")

    # -- gate 1 over unique blobs (pass 2's astcheck phase, verbatim) ------------------------
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
    log(f"astcheck phase done in {t_ast:.1f}s: {len(unique)} unique blobs, {n_bad} failures")

    # -- the stripped sources must be in the object db (pass 2 put them there; be sure) -------
    t1 = time.time()
    have_py = [s for s in unique if ast_results.get(s, {}).get("stripped_sha")]
    got = hash_objects(mirror, [cache / f"{s}.py" for s in have_py])
    py_mismatch = [(s, g) for s, g in zip(have_py, got) if g != ast_results[s]["stripped_sha"]]
    if py_mismatch:
        sys.exit(f"hash-object sha != content address of cache/<sha>.py for "
                 f"{len(py_mismatch)} blobs (cache changed under us?): {py_mismatch[:3]}")

    # -- sidedocs and indexes into the object db ----------------------------------------------
    with tempfile.TemporaryDirectory(prefix="sideword-pass4-idx-") as td:
        art = prepare_artifacts(mirror, cache, list(unique), list(pairs), Path(td))
    retargeted = sum(1 for (sha, path) in pairs
                     if (sha, path) in art["idx_sha"] and unique.get(sha) != path)
    t_art = time.time() - t1
    log(f"artifacts hashed in {t_art:.1f}s: {len(art['md_sha'])} sidedocs, "
        f"{len(art['idx_sha'])} indexes ({retargeted} headers retargeted), "
        f"missing md {len(art['missing_md'])}, missing idx {len(art['missing_idx'])}, "
        f"bad headers {len(art['bad_header'])}, sha mismatches {len(art['mismatch'])}")
    if art["mismatch"]:
        sys.exit(f"hash-object sha != content address for {len(art['mismatch'])} artifacts: "
                 f"{art['mismatch'][:3]}")

    rows = []
    for inst in instances:
        row = process_instance(inst, snaps[inst["instance_id"]], mirror, cache, ast_results, art,
                               directives_sha, stripper_ver, args.force, not args.no_tag)
        row["index_headers_retargeted"] = sum(
            1 for f in snaps[inst["instance_id"]]["files"]
            if unique.get(f["blob_sha"]) != f["path"])
        rows.append(row)
        log(f"{inst['instance_id']}: gate={'PASS' if row['gate_passed'] else 'FAIL'} "
            f"changed={row['files_changed']} +docs={row['sidedocs_added']}/{row['indexes_added']} "
            f"records={row['records']} commit={(row['sw_commit'] or '-')[:12]} "
            f"tag={row['tag_action']} ({row['seconds']}s)"
            + (f" :: {row['failure_detail'][0][:200]}" if row["failure_detail"] else ""))

    wt_results = []
    if args.worktree_check:
        by_id = {r["instance_id"]: r for r in rows}
        inst_by_id = {i["instance_id"]: i for i in instances}
        for iid in args.worktree_check:
            if iid not in by_id:
                sys.exit(f"--worktree-check: {iid} not among processed instances")
            res = worktree_check(mirror, inst_by_id[iid], by_id[iid], jobs, directives_path)
            wt_results.append(res)
            log(f"worktree check {iid}: ok={res['ok']} py={res['py_files']} "
                f"changed={res['changed_py']} sidedocs={res['sidedoc_files']} "
                f"indexes={res['index_files']} comments_left={res['comments_left']} "
                f"(non-directive {len(res['comments_not_directives'])}) "
                f"docstrings_left={res['docstrings_left']} (doctests {res['doctests_left']}) "
                f"({res['seconds']}s) {res['error'] or ''}")

    per_repo = []
    for repo in sorted({r["repo"] for r in rows}):
        rr = [r for r in rows if r["repo"] == repo]
        per_repo.append({
            "repo": repo, "instances": len(rr),
            "gate_passed": sum(r["gate_passed"] for r in rr),
            "gate_failures": sum(not r["gate_passed"] for r in rr),
            "tags_created": sum(r["tag_action"] == "created" for r in rr),
            "tags_unchanged": sum(r["tag_action"] == "unchanged" for r in rr),
            "tags_forced": sum((r["tag_action"] or "").startswith("forced") for r in rr),
            "files_selected": sum(r["files_selected"] for r in rr),
            "files_changed": sum(r["files_changed"] or 0 for r in rr),
            "sidedocs_added": sum(r["sidedocs_added"] for r in rr),
            "indexes_added": sum(r["indexes_added"] for r in rr),
            "records": sum(r["records"] for r in rr),
            "empty_sidedocs": sum(r["empty_sidedocs"] for r in rr),
            "sidedoc_bytes": sum(r["sidedoc_bytes"] for r in rr),
            "index_bytes": sum(r["index_bytes"] for r in rr),
            "sidedoc_tokens": sum(r["sidedoc_tokens"] for r in rr),
        })
    pass3 = json.loads(PASS3_REPORT.read_text()) if PASS3_REPORT.exists() else None
    pass3_summary = {k: v for k, v in (pass3 or {}).items() if k != "per_instance"} or None
    tags = git_out(mirror, "for-each-ref", "--format=%(refname:short) %(objectname) %(objecttype)",
                   "refs/tags").splitlines()
    sw_tags = git_out(mirror, "tag", "-l", f"*{TAG_SUFFIX}").splitlines()
    nc_tags = git_out(mirror, "tag", "-l", f"*{NC_SUFFIX}").splitlines()
    wall = time.time() - t0
    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "wall_seconds": round(wall, 1), "astcheck_seconds": round(t_ast, 1),
        "artifact_seconds": round(t_art, 1), "jobs": jobs,
        "mirror": str(mirror), "cache": str(cache),
        "directives_sha256": directives_sha, "stripper_version": stripper_ver,
        "harness_stripper_version": harness_ver, "stale_stripper": stale_stripper,
        "sidedoc_format": FORMAT_VERSION, "commit_identity": COMMIT_ENV,
        "force": bool(args.force), "only": args.only or None,
        "instances": len(rows),
        "gate_passed": sum(r["gate_passed"] for r in rows),
        "gate_failed": sum(not r["gate_passed"] for r in rows),
        "tags_created": sum(r["tag_action"] == "created" for r in rows),
        "tags_unchanged": sum(r["tag_action"] == "unchanged" for r in rows),
        "tags_forced": sum((r["tag_action"] or "").startswith("forced") for r in rows),
        "tags_refused": sum((r["tag_action"] or "").startswith("refused") for r in rows),
        "unique_blobs_verified": len(unique),
        "unique_blobs_astcheck_failures": n_bad,
        "unique_pairs": len(pairs),
        "sidedoc_blobs": len(art["md_sha"]),
        "index_blobs": len(set(art["idx_sha"].values())),
        "index_headers_retargeted": retargeted,
        "artifact_problems": {"missing_md": art["missing_md"][:20],
                              "missing_idx": art["missing_idx"][:20],
                              "bad_header": art["bad_header"][:20],
                              "mismatch": art["mismatch"][:20]},
        "per_repo": per_repo, "per_instance": rows, "worktree_checks": wt_results,
        "pass3": pass3_summary, "refs_tags": tags, "sw_tags": sw_tags, "nc_tags": nc_tags,
    }
    REPORT_JSON.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_MD.write_text(render_md(report), encoding="utf-8")
    log(f"done in {wall:.1f}s: {report['gate_passed']}/{len(rows)} passed, tags created "
        f"{report['tags_created']}, unchanged {report['tags_unchanged']}, "
        f"forced {report['tags_forced']}, refused {report['tags_refused']}; "
        f"{len(sw_tags)} *{TAG_SUFFIX} tags in the mirror")
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
    L.append("# Pass 4 report (-sw commits and tags)\n")
    L.append(f"Generated {rep['generated_at']} · wall {rep['wall_seconds']} s "
             f"(astcheck {rep['astcheck_seconds']} s, artifacts {rep['artifact_seconds']} s) · "
             f"jobs {rep['jobs']} · directives sha256 `{rep['directives_sha256'][:12]}` · "
             f"stripper `{rep['stripper_version'][:12]}` · format `{rep['sidedoc_format']}` · "
             f"mirror `{rep['mirror']}`\n")
    if rep.get("stale_stripper"):
        L.append(f"> Run with `--allow-stale-stripper`: the cache was written by stripper "
                 f"`{rep['stripper_version'][:12]}`, the running harness is "
                 f"`{rep['harness_stripper_version'][:12]}`.  Pass 4 re-strips nothing; the `.py` "
                 f"blobs are pass 1's bytes and gate `-nc` proves them equal to the `-nc` tags'.\n")
    L.append(f"Instances {rep['instances']} · gate passed {rep['gate_passed']} · "
             f"gate failed {rep['gate_failed']} · tags created {rep['tags_created']} · "
             f"unchanged {rep['tags_unchanged']} · forced {rep['tags_forced']} · "
             f"refused {rep['tags_refused']}\n")
    L.append(f"Unique blobs re-verified {_fmt(rep['unique_blobs_verified'])} "
             f"(astcheck failures {rep['unique_blobs_astcheck_failures']}) · "
             f"unique (blob, path) pairs {_fmt(rep['unique_pairs'])} · "
             f"sidedoc blobs {_fmt(rep['sidedoc_blobs'])} · index blobs {_fmt(rep['index_blobs'])} · "
             f"index headers retargeted {_fmt(rep['index_headers_retargeted'])}\n")
    ce = rep["commit_identity"]
    L.append(f"Commit identity: `{ce['GIT_AUTHOR_NAME']} <{ce['GIT_AUTHOR_EMAIL']}>` at "
             f"`{ce['GIT_AUTHOR_DATE']}` (author = committer; deterministic shas).\n")
    L.append("Gates: **cache** all three cache artifacts present · **AST** stripped == original · "
             "**tests** test paths untouched · **tree** base paths + exactly the added "
             "`.sideword/` files · **pairs** every `.sideword/` file names a selected path in the "
             "tree · **-nc** the two trees are identical outside `.sideword/`.\n")
    L.append("## Per instance\n")
    L.append("| instance | base | -sw commit | tag | action | selected | changed | sidedocs | "
             "indexes | records | empty docs | sidedoc KiB | index KiB | ~doc tok | cache | AST | "
             "unresolved | tests | tree | pairs | -nc | failure |")
    L.append("|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---|---|---|---|---|")
    for r in rep["per_instance"]:
        g = r["gate"]
        L.append(f"| {r['instance_id']} | `{r['base_commit'][:12]}` | "
                 f"`{(r['sw_commit'] or '-')[:12]}` | `{r['tag']}` | {r['tag_action'] or 'none'} | "
                 f"{_fmt(r['files_selected'])} | {_fmt(r['files_changed'])} | "
                 f"{_fmt(r['sidedocs_added'])} | {_fmt(r['indexes_added'])} | "
                 f"{_fmt(r['records'])} | {_fmt(r['empty_sidedocs'])} | "
                 f"{_fmt(r['sidedoc_bytes'] // 1024)} | "
                 f"{_fmt(r['index_bytes'] // 1024)} | {_fmt(r['sidedoc_tokens'])} | "
                 f"{_fmt(g['cache_complete'])} | {_fmt(g['ast_ok'])} | {_fmt(g['unresolved'])} | "
                 f"{_fmt(g['tests_untouched'])} | {_fmt(g['tree_complete'])} | "
                 f"{_fmt(g['sideword_pairs'])} | {_fmt(g['nc_agrees'])} | "
                 f"{'; '.join(r['failure_detail'])[:200] if r['failure_detail'] else ''} |")
    L.append("\n## Per repo\n")
    L.append("| repo | instances | gate passed | failures | created | unchanged | forced | "
             "selected | changed | sidedocs | indexes | records | empty docs | sidedoc KiB | "
             "index KiB | ~doc tok |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rep["per_repo"]:
        L.append(f"| {r['repo']} | {r['instances']} | {r['gate_passed']} | {r['gate_failures']} | "
                 f"{r['tags_created']} | {r['tags_unchanged']} | {r['tags_forced']} | "
                 f"{_fmt(r['files_selected'])} | {_fmt(r['files_changed'])} | "
                 f"{_fmt(r['sidedocs_added'])} | {_fmt(r['indexes_added'])} | "
                 f"{_fmt(r['records'])} | {_fmt(r['empty_sidedocs'])} | "
                 f"{_fmt(r['sidedoc_bytes'] // 1024)} | "
                 f"{_fmt(r['index_bytes'] // 1024)} | {_fmt(r['sidedoc_tokens'])} |")
    fails = [r for r in rep["per_instance"] if r["failure_detail"]]
    L.append("\n## Gate failures\n")
    if not fails:
        L.append("None.\n")
    for r in fails:
        L.append(f"- **{r['instance_id']}**: " + " / ".join(r["failure_detail"]))
    probs = rep["artifact_problems"]
    if any(probs.values()):
        L.append("\n## Artifact problems\n")
        for k, v in probs.items():
            if v:
                L.append(f"- **{k}** ({len(v)} shown): {v[:5]}")
    if rep["worktree_checks"]:
        L.append("\n## Worktree sanity checks\n")
        L.append("| instance | tag | ok | .py | changed .py | .sideword .md | .sideword .idx | "
                 "comments left | non-directive comments | docstrings left | of which doctests | "
                 "parse failures | seconds | error |")
        L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for w in rep["worktree_checks"]:
            L.append(f"| {w['instance_id']} | `{w['tag']}` | {_fmt(w['ok'])} | {_fmt(w['py_files'])} | "
                     f"{_fmt(w['changed_py'])} | {_fmt(w['sidedoc_files'])} | {_fmt(w['index_files'])} | "
                     f"{_fmt(w['comments_left'])} | {len(w['comments_not_directives'])} | "
                     f"{_fmt(w['docstrings_left'])} | {_fmt(w['doctests_left'])} | "
                     f"{len(w['parse_failures'])} | {w['seconds']} | {w['error'] or ''} |")
        for w in rep["worktree_checks"]:
            s = w.get("sample")
            if not s:
                continue
            L.append(f"\n### Sample from `{w['instance_id']}`: `{s['path']}`\n")
            L.append(f"Source {s['source_bytes']:,} B, contains `#`: {s['source_has_hash_comment']} · "
                     f"sidedoc {s['sidedoc_bytes']:,} B\n")
            L.append("```")
            L.extend(s["index_head"])
            L.append("```")
            L.append("```markdown")
            L.extend(s["sidedoc_head"])
            L.append("```")
    p3 = rep.get("pass3")
    if p3:
        L.append("\n## Pass 3 (the artifacts these trees carry)\n")
        L.append("| | |")
        L.append("|---|---|")
        for k, v in p3.items():
            L.append(f"| {k} | {_fmt(v) if isinstance(v, (int, float)) else v} |")
    L.append("\n## refs/tags in the mirror\n")
    L.append("```")
    L.extend(rep["refs_tags"] or ["(none)"])
    L.append("```")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instances", default=str(DEFAULT_INSTANCES))
    ap.add_argument("--mirror", default=str(DEFAULT_MIRROR))
    ap.add_argument("--cache", default=str(DEFAULT_CACHE))
    ap.add_argument("--directives", default=str(DEFAULT_DIRECTIVES))
    ap.add_argument("--only", nargs="*", default=None, help="instance ids to process")
    ap.add_argument("--force", action="store_true", help="move an existing -sw tag")
    ap.add_argument("--allow-stale-stripper", action="store_true",
                    help="proceed when strip/directives/astcheck.py have changed since pass 1 "
                         "wrote the cache; the cache's own stripper_version is used")
    ap.add_argument("--no-tag", action="store_true", help="build, gate and commit but do not tag")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--worktree-check", nargs="*", default=None,
                    help="check these instances out into a temp worktree and confirm the .py "
                         "files are clean while .sideword/ holds the documentation")
    args = ap.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
