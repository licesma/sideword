#!/usr/bin/env python
"""Build / refresh the Sideword mirror repo (EST-105).

    ~/repos/sideword-corpus        one git repo, sibling of ~/repos/sideword
      remotes  <name>  -> the 12 SWE-bench Verified upstreams (no tags fetched)
      branches <name>  -> that upstream's default-branch head at fetch time
      (pass 2 later adds `<instance_id>-nc` commits/tags on top of base_commits)

Idempotent: every step is a no-op if already done, fetches are incremental.
Stdlib only.  Usage:

    .venv/bin/python harness/mirror.py                 # full run
    .venv/bin/python harness/mirror.py --skip-fetch    # only verify/branches/manifest
    .venv/bin/python harness/mirror.py --jobs 6 --wait-instances 0

Steps: init -> remotes -> fetch (parallel, retried) -> wait for
corpus/instances.json -> verify every base_commit (fetch by sha if missing)
-> branch per remote -> write corpus/mirror-manifest.json.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIDEWORD = HERE.parent
MIRROR = Path(os.environ.get("SIDEWORD_MIRROR", SIDEWORD.parent / "sideword-corpus"))
INSTANCES = SIDEWORD / "corpus" / "instances.json"
MANIFEST = SIDEWORD / "corpus" / "mirror-manifest.json"

# remote name = second path segment of the GitHub repo
REMOTES: dict[str, str] = {
    "astropy": "https://github.com/astropy/astropy",
    "django": "https://github.com/django/django",
    "matplotlib": "https://github.com/matplotlib/matplotlib",
    "seaborn": "https://github.com/mwaskom/seaborn",
    "flask": "https://github.com/pallets/flask",
    "requests": "https://github.com/psf/requests",
    "xarray": "https://github.com/pydata/xarray",
    "pylint": "https://github.com/pylint-dev/pylint",
    "pytest": "https://github.com/pytest-dev/pytest",
    "scikit-learn": "https://github.com/scikit-learn/scikit-learn",
    "sphinx": "https://github.com/sphinx-doc/sphinx",
    "sympy": "https://github.com/sympy/sympy",
}

# local config that makes later commits deterministic and keeps the mirror quiet
CONFIG = {
    "user.name": "sideword",
    "user.email": "sideword@localhost",
    "core.autocrlf": "false",
    "gc.auto": "0",
    "fetch.prune": "true",
    "advice.detachedHead": "false",
}

GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}


def log(*a: object) -> None:
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def git(*args: str, check: bool = True, capture: bool = True, cwd: Path = MIRROR) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=GIT_ENV, check=check,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None, text=True,
    )


def out(*args: str, **kw) -> str:
    return git(*args, **kw).stdout.strip()


def repo_name(repo: str) -> str:
    """'mwaskom/seaborn' -> 'seaborn'"""
    return repo.split("/")[1]


# --------------------------------------------------------------------------- steps

def step_init() -> None:
    if not (MIRROR / ".git").is_dir():
        MIRROR.mkdir(parents=True, exist_ok=True)
        git("init", "-q", cwd=MIRROR)
        log("initialised", MIRROR)
    for k, v in CONFIG.items():
        if out("config", "--local", "--get", k, check=False) != v:
            git("config", "--local", k, v)


def step_remotes() -> None:
    existing = set(out("remote").split())
    for name, url in REMOTES.items():
        if name not in existing:
            git("remote", "add", name, url)
            log("added remote", name)
        elif out("remote", "get-url", name) != url:
            git("remote", "set-url", name, url)
        want = {
            f"remote.{name}.tagopt": "--no-tags",
            f"remote.{name}.fetch": f"+refs/heads/*:refs/remotes/{name}/*",
        }
        for k, v in want.items():
            if out("config", "--local", "--get-all", k, check=False) != v:
                git("config", "--local", "--replace-all", k, v)
    extra = existing - set(REMOTES)
    if extra:
        log("WARNING: unexpected remotes present, leaving them alone:", sorted(extra))


def fetch_one(name: str, retries: int = 4) -> dict:
    t0 = time.time()
    last_err = ""
    for attempt in range(1, retries + 1):
        p = git("fetch", "--no-tags", "--prune", "--no-recurse-submodules", name, check=False)
        if p.returncode == 0:
            git("remote", "set-head", name, "--auto", check=False)
            dur = round(time.time() - t0, 1)
            log(f"fetched {name} in {dur}s (attempt {attempt})")
            return {"ok": True, "seconds": dur, "attempts": attempt}
        last_err = (p.stderr or "").strip().splitlines()[-1:] or ["?"]
        log(f"fetch {name} failed (attempt {attempt}): {last_err[0]}")
        time.sleep(min(60, 10 * attempt))
    return {"ok": False, "seconds": round(time.time() - t0, 1), "attempts": retries, "error": last_err[0]}


def step_fetch(jobs: int) -> dict[str, dict]:
    log(f"fetching {len(REMOTES)} remotes, {jobs} in parallel")
    # biggest first so the long poles start early
    order = ["django", "sympy", "scikit-learn", "astropy", "matplotlib", "sphinx",
             "xarray", "pylint", "pytest", "requests", "seaborn", "flask"]
    results: dict[str, dict] = {}
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(fetch_one, n): n for n in order}
        for f in cf.as_completed(futs):
            results[futs[f]] = f.result()
    return results


def load_instances(wait_seconds: int) -> list[dict] | None:
    deadline = time.time() + wait_seconds
    while True:
        if INSTANCES.exists():
            try:
                data = json.loads(INSTANCES.read_text())
                if isinstance(data, list) and data:
                    return data
            except json.JSONDecodeError:
                pass  # being written; try again
        if time.time() >= deadline:
            return None
        log(f"waiting for {INSTANCES} ...")
        time.sleep(30)


def has_commit(sha: str) -> bool:
    return git("cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode == 0


def step_verify(instances: list[dict]) -> list[dict]:
    """Ensure every base_commit is present; fetch by sha from the right remote if not."""
    rows = []
    missing_by_remote: dict[str, set[str]] = {}
    for inst in instances:
        remote = repo_name(inst["repo"])
        if remote not in REMOTES:
            log(f"WARNING: {inst['instance_id']} repo {inst['repo']} has no remote")
        sha = inst["base_commit"]
        if not has_commit(sha):
            missing_by_remote.setdefault(remote, set()).add(sha)
    for remote, shas in missing_by_remote.items():
        log(f"{remote}: {len(shas)} base_commit(s) not reachable from branches, fetching by sha")
        for sha in sorted(shas):
            for attempt in range(3):
                p = git("fetch", "--no-tags", remote, sha, check=False)
                if p.returncode == 0:
                    break
                log(f"  fetch {remote} {sha[:12]} failed: {(p.stderr or '').strip().splitlines()[-1:]}")
                time.sleep(5)
    for inst in instances:
        remote = repo_name(inst["repo"])
        sha = inst["base_commit"]
        found = has_commit(sha)
        rows.append({
            "instance_id": inst["instance_id"],
            "repo": inst["repo"],
            "remote": remote,
            "base_commit": sha,
            "base_commit_short": sha[:12],
            "found": found,
            "commit_date": out("show", "-s", "--format=%cI", sha) if found else None,
        })
    n_missing = sum(not r["found"] for r in rows)
    log(f"verified {len(rows)} base_commits, {n_missing} missing")
    return rows


def default_head(name: str) -> str | None:
    for ref in (f"refs/remotes/{name}/HEAD", f"refs/remotes/{name}/main", f"refs/remotes/{name}/master"):
        sha = out("rev-parse", "--verify", "-q", ref, check=False)
        if sha:
            return sha
    return None


def step_branches() -> dict[str, str | None]:
    heads: dict[str, str | None] = {}
    current = out("symbolic-ref", "-q", "HEAD", check=False)  # '' when detached
    for name in REMOTES:
        sha = default_head(name)
        heads[name] = sha
        if sha is None:
            log(f"WARNING: no default head for {name}; branch not created")
            continue
        if current == f"refs/heads/{name}":
            git("update-ref", f"refs/heads/{name}", sha)  # never checked out in practice
        else:
            git("branch", "-f", name, sha)
    return heads


def object_count(name: str) -> int:
    p = subprocess.run(
        ["git", "rev-list", "--objects", f"--glob=refs/remotes/{name}/*"],
        cwd=MIRROR, env=GIT_ENV, stdout=subprocess.PIPE, text=True, check=True,
    )
    return p.stdout.count("\n")


def step_manifest(fetch_results: dict[str, dict], heads: dict[str, str | None],
                  rows: list[dict] | None, jobs: int) -> None:
    prev: dict = {}
    if MANIFEST.exists():
        try:
            prev = json.loads(MANIFEST.read_text())
        except json.JSONDecodeError:
            prev = {}
    prev_remotes = prev.get("remotes", {})
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    log("counting objects per remote")
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        counts = dict(zip(REMOTES, ex.map(object_count, REMOTES)))
    remotes = {}
    for name, url in REMOTES.items():
        fr = fetch_results.get(name)
        old = prev_remotes.get(name, {})
        remotes[name] = {
            "url": url,
            "head_sha": heads.get(name),
            "branch": name,
            "fetched_at": now if fr and fr.get("ok") else old.get("fetched_at"),
            "fetch_seconds": fr.get("seconds") if fr else old.get("fetch_seconds"),
            # duration of the very first (full) fetch, preserved across incremental reruns
            "initial_fetch_seconds": old.get("initial_fetch_seconds")
                or old.get("fetch_seconds") or (fr.get("seconds") if fr else None),
            "fetch_ok": fr.get("ok") if fr else old.get("fetch_ok"),
            "object_count": counts[name],
            "commit_count": int(out("rev-list", "--count", f"--glob=refs/remotes/{name}/*") or 0),
        }
    if rows is None:
        rows = prev.get("instances", [])
        note = "instances.json not available at run time; instance rows carried over from previous manifest"
    else:
        note = None
    manifest = {
        "mirror": str(MIRROR),
        "generated_at": now,
        "git_dir_bytes": du_bytes(MIRROR / ".git"),
        "instances_total": len(rows),
        "instances_found": sum(1 for r in rows if r.get("found")),
        "instances_missing": [r["instance_id"] for r in rows if not r.get("found")],
        "note": note,
        "remotes": remotes,
        "instances": rows,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n")
    log("wrote", MANIFEST)


def du_bytes(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", type=int, default=4, help="parallel fetches (default 4)")
    ap.add_argument("--skip-fetch", action="store_true", help="do not fetch the remotes")
    ap.add_argument("--wait-instances", type=int, default=40 * 60,
                    help="seconds to wait for corpus/instances.json (default 2400; 0 = don't wait)")
    a = ap.parse_args(argv)

    step_init()
    step_remotes()
    fetch_results = {} if a.skip_fetch else step_fetch(a.jobs)
    failed = [n for n, r in fetch_results.items() if not r["ok"]]
    if failed:
        log("FETCH FAILED for:", failed)
    instances = load_instances(a.wait_instances)
    rows = step_verify(instances) if instances is not None else None
    if rows is None:
        log("no instances.json; skipping base_commit verification")
    heads = step_branches()
    step_manifest(fetch_results, heads, rows, a.jobs)
    for name, r in sorted(fetch_results.items()):
        log(f"  {name:13s} ok={r['ok']} {r['seconds']}s attempts={r['attempts']}")
    if rows is not None:
        missing = [r["instance_id"] for r in rows if not r["found"]]
        log(f"base_commits: {len(rows) - len(missing)}/{len(rows)} found; missing: {missing or 'none'}")
        return 1 if missing or failed else 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
