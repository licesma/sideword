"""EST-104: select ~30 SWE-bench Verified instances and write corpus/instances.json.

Usage:
    .venv/bin/python harness/instances.py            # writes corpus/instances.json + instances-summary.md
    .venv/bin/python harness/instances.py --dry-run  # print selection only

Selection rule (deterministic, no randomness):
  1. Load princeton-nlp/SWE-bench_Verified (500 rows, 12 repos) from Hugging Face.
  2. Per repo, candidates = instances whose `patch` touches >=1 non-test .py file (test-path
     rule from harness/CONTRACT.md) AND whose hunks in those files contain >=1 comment or
     docstring line (`#` or triple quotes in a context/+/- line). If a repo has fewer such
     candidates than its quota, fall back to "touches >=1 non-test .py file", then to all.
  3. Fill the repo's quota greedily, one slot at a time. Rank remaining candidates by
       (a) fewest picks so far for the candidate's `version`  -> spreads snapshot age,
       (b) difficulty == preferred difficulty for this slot     -> mixes difficulty,
           preferred cycles through DIFFICULTY_CYCLE by slot index,
       (c) sha1(instance_id) hex                                 -> stable tie-break.
     Candidates sharing a base_commit with an already-picked instance are skipped.
  4. Output sorted by (repo, created_at, instance_id).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_JSON = os.path.join(ROOT, "corpus", "instances.json")
OUT_MD = os.path.join(ROOT, "corpus", "instances-summary.md")

DATASET = "princeton-nlp/SWE-bench_Verified"

# repo -> quota. Sums to 30. Weighted toward comment-dense repos.
QUOTA = {
    "sympy/sympy": 5,
    "astropy/astropy": 4,
    "scikit-learn/scikit-learn": 4,
    "matplotlib/matplotlib": 4,
    "django/django": 3,
    "sphinx-doc/sphinx": 2,
    "pydata/xarray": 2,
    "pytest-dev/pytest": 2,
    "pylint-dev/pylint": 1,
    "mwaskom/seaborn": 1,
    "pallets/flask": 1,
    "psf/requests": 1,
}

# Preferred difficulty for the k-th pick within a repo (k % len). Roughly mirrors the
# dataset mix (52% "15 min - 1 hour", 39% "<15 min fix", 8% "1-4 hours").
DIFFICULTY_CYCLE = ["15 min - 1 hour", "<15 min fix", "1-4 hours", "15 min - 1 hour", "<15 min fix"]

_DIFF_HDR = re.compile(r"^diff --git a/(.*?) b/(.*)$", re.M)
_TEST_SEGMENTS = {"tests", "test", "testing"}


def is_test_path(path: str) -> bool:
    """CONTRACT.md test-path rule (without the per-instance test_patch_paths clause)."""
    parts = path.split("/")
    if any(p in _TEST_SEGMENTS for p in parts[:-1]):
        return True
    base = parts[-1]
    if base in ("conftest.py", "tests.py"):
        return True
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith("_test.py"):
        return True
    return False


def diff_paths(diff: str) -> list[str]:
    """Paths from `diff --git a/X b/X` headers, in order, de-duplicated (b-side)."""
    out: list[str] = []
    for m in _DIFF_HDR.finditer(diff):
        p = m.group(2)
        if p not in out:
            out.append(p)
    return out


def split_by_file(diff: str) -> dict[str, str]:
    """Map path -> that file's chunk of the unified diff."""
    chunks: dict[str, str] = {}
    positions = [(m.start(), m.group(2)) for m in _DIFF_HDR.finditer(diff)]
    for i, (start, path) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(diff)
        chunks[path] = diff[start:end]
    return chunks


def docs_signal(file_diff: str) -> int:
    """Number of hunk body lines (context/+/-) that look like a comment or docstring line."""
    n = 0
    for line in file_diff.splitlines():
        if not line or line[0] not in " +-":
            continue
        if line.startswith(("+++", "---")):
            continue
        body = line[1:].strip()
        if body.startswith("#") or '"""' in body or "'''" in body or " # " in line:
            n += 1
    return n


def load_rows() -> list[dict]:
    from huggingface_hub import hf_hub_download, list_repo_files
    import pyarrow.parquet as pq

    files = [f for f in list_repo_files(DATASET, repo_type="dataset") if f.endswith(".parquet")]
    if len(files) != 1:
        raise SystemExit(f"expected exactly one parquet in {DATASET}, got {files}")
    path = hf_hub_download(repo_id=DATASET, repo_type="dataset", filename=files[0])
    table = pq.read_table(path)
    return table.to_pylist()


def annotate(row: dict) -> dict:
    patch_paths = diff_paths(row["patch"])
    test_patch_paths = diff_paths(row["test_patch"])
    chunks = split_by_file(row["patch"])
    src_py = [p for p in patch_paths if p.endswith(".py") and not is_test_path(p) and p not in test_patch_paths]
    signal = sum(docs_signal(chunks[p]) for p in src_py)
    return {
        "instance_id": row["instance_id"],
        "repo": row["repo"],
        "base_commit": row["base_commit"],
        "version": row["version"],
        "created_at": row["created_at"],
        "FAIL_TO_PASS": json.loads(row["FAIL_TO_PASS"]),
        "PASS_TO_PASS": json.loads(row["PASS_TO_PASS"]),
        "test_patch_paths": test_patch_paths,
        "patch_paths": patch_paths,
        "problem_statement_len": len(row["problem_statement"]),
        "difficulty": row.get("difficulty"),
        # selection-only fields (dropped before writing)
        "_src_py": src_py,
        "_signal": signal,
    }


def _tiebreak(instance_id: str) -> str:
    return hashlib.sha1(instance_id.encode()).hexdigest()


def select_for_repo(cands: list[dict], quota: int, log) -> list[dict]:
    tiers = [
        [c for c in cands if c["_src_py"] and c["_signal"] > 0],
        [c for c in cands if c["_src_py"]],
        list(cands),
    ]
    pool = next((t for t in tiers if len(t) >= quota), tiers[-1])
    tier_idx = tiers.index(pool)
    log(f"  tiers: docs={len(tiers[0])} src_py={len(tiers[1])} all={len(tiers[2])} -> using tier {tier_idx}")

    picked: list[dict] = []
    picked_ids: set[str] = set()
    picked_shas: set[str] = set()
    version_count: collections.Counter = collections.Counter()
    while len(picked) < quota:
        k = len(picked)
        want = DIFFICULTY_CYCLE[k % len(DIFFICULTY_CYCLE)]
        remaining = [c for c in pool if c["instance_id"] not in picked_ids and c["base_commit"] not in picked_shas]
        if not remaining:
            break
        remaining.sort(
            key=lambda c: (
                version_count[c["version"]],
                0 if c["difficulty"] == want else 1,
                _tiebreak(c["instance_id"]),
            )
        )
        c = remaining[0]
        picked.append(c)
        picked_ids.add(c["instance_id"])
        picked_shas.add(c["base_commit"])
        version_count[c["version"]] += 1
    return picked


def select(rows: list[dict], log=lambda s: None) -> list[dict]:
    ann = [annotate(r) for r in rows]
    by_repo: dict[str, list[dict]] = collections.defaultdict(list)
    for a in ann:
        by_repo[a["repo"]].append(a)
    repos = sorted(by_repo)
    if set(repos) != set(QUOTA):
        raise SystemExit(f"repo set mismatch: dataset={repos} quota={sorted(QUOTA)}")
    chosen: list[dict] = []
    for repo in repos:
        log(f"{repo}: {len(by_repo[repo])} instances, quota {QUOTA[repo]}")
        cands = sorted(by_repo[repo], key=lambda c: c["instance_id"])
        chosen.extend(select_for_repo(cands, QUOTA[repo], log))
    chosen.sort(key=lambda c: (c["repo"], c["created_at"], c["instance_id"]))
    return chosen


def sanity(chosen: list[dict]) -> None:
    sha_re = re.compile(r"^[0-9a-f]{40}$")
    for c in chosen:
        assert sha_re.match(c["base_commit"]), c["instance_id"]
        assert c["test_patch_paths"], f"{c['instance_id']} has no test_patch_paths"
        assert c["patch_paths"], f"{c['instance_id']} has no patch_paths"
        assert c["FAIL_TO_PASS"], f"{c['instance_id']} has empty FAIL_TO_PASS"
    ids = [c["instance_id"] for c in chosen]
    assert len(ids) == len(set(ids))
    shas = [c["base_commit"] for c in chosen]
    assert len(shas) == len(set(shas)), "duplicate base_commit"
    assert set(c["repo"] for c in chosen) == set(QUOTA), "not all repos covered"


def summary_md(chosen: list[dict]) -> str:
    by_repo: dict[str, list[dict]] = collections.defaultdict(list)
    for c in chosen:
        by_repo[c["repo"]].append(c)
    lines = [
        "# Selected SWE-bench Verified instances",
        "",
        f"Generated by `harness/instances.py` from `{DATASET}`. Total: **{len(chosen)}** instances, "
        f"{len(by_repo)} repos.",
        "",
        "| repo | n | instance_id | version | base_commit | created_at | difficulty | #F2P | #P2P | src .py touched |",
        "|---|---:|---|---|---|---|---|---:|---:|---:|",
    ]
    for repo in sorted(by_repo):
        rows = by_repo[repo]
        for i, c in enumerate(rows):
            lines.append(
                f"| {repo if i == 0 else ''} | {len(rows) if i == 0 else ''} | `{c['instance_id']}` | {c['version']} | "
                f"`{c['base_commit'][:10]}` | {c['created_at'][:10]} | {c['difficulty']} | "
                f"{len(c['FAIL_TO_PASS'])} | {len(c['PASS_TO_PASS'])} | {len(c['_src_py'])} |"
            )
    lines += ["", "## Per-repo totals", "", "| repo | count | versions | #F2P | #P2P |", "|---|---:|---|---:|---:|"]
    tf = tp = 0
    for repo in sorted(by_repo):
        rows = by_repo[repo]
        f2p = sum(len(c["FAIL_TO_PASS"]) for c in rows)
        p2p = sum(len(c["PASS_TO_PASS"]) for c in rows)
        tf += f2p
        tp += p2p
        versions = ", ".join(sorted({c["version"] for c in rows}, key=lambda v: [int(x) if x.isdigit() else x for x in v.split(".")]))
        lines.append(f"| {repo} | {len(rows)} | {versions} | {f2p} | {p2p} |")
    lines.append(f"| **total** | **{len(chosen)}** | | **{tf}** | **{tp}** |")
    diff = collections.Counter(c["difficulty"] for c in chosen)
    lines += ["", "## Difficulty mix", ""] + [f"- {k}: {v}" for k, v in sorted(diff.items(), key=lambda kv: -kv[1])]
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    log = lambda s: print(s, file=sys.stderr)

    rows = load_rows()
    log(f"loaded {len(rows)} rows, repos={sorted(collections.Counter(r['repo'] for r in rows).items())}")
    chosen = select(rows, log)
    sanity(chosen)

    counts = collections.Counter(c["repo"] for c in chosen)
    for repo, n in sorted(counts.items()):
        print(f"{repo:28s} {n}")
    print(f"{'total':28s} {len(chosen)}")

    if args.dry_run:
        for c in chosen:
            print(c["instance_id"], c["version"], c["difficulty"], c["_signal"], c["_src_py"])
        return

    out = [{k: v for k, v in c.items() if not k.startswith("_")} for c in chosen]
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    with open(OUT_MD, "w") as f:
        f.write(summary_md(chosen))
    print(f"wrote {OUT_JSON} and {OUT_MD}")


if __name__ == "__main__":
    main()
