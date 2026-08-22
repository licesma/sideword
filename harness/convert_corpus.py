"""EST-119 — run the converter over every cached blob of the 30 instances.

    .venv/bin/python -m harness.convert_corpus plan             # what it would cost
    .venv/bin/python -m harness.convert_corpus run --jobs 4     # convert (resumable)
    .venv/bin/python -m harness.convert_corpus report           # tokens and time, per instance

The recipe is EST-111's, settled by EST-120: `claude-opus-5` at effort medium,
headless `claude -p`, the model names anchors only and never touches the text.
The system prompt is `FORMAT.md` plus the contract, byte-identical on every
call so it stays cached.

Work is content-addressed by blob sha, exactly as the strip cache is. The 30
instances share far more source than they don't — 11,609 unique blobs across
~15,000 instance-file pairs — so a blob converted for one instance is never
converted again for another. `cache/<sha>.anchors.json` is the unit of resume:
if it exists, that blob is done.

Every call's tokens, wall time and nominal cost are recorded per blob, which is
what makes the per-instance and whole-corpus totals in `report` real
measurements rather than estimates.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import json
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from harness import convert_pilot as pilot
from harness import paths as pathrules

CACHE = ROOT / "cache"
SNAPSHOTS = ROOT / "corpus" / "snapshots"
INSTANCES = ROOT / "corpus" / "instances.json"
OUT = ROOT / "corpus" / "convert-corpus"
REPORT_JSON = OUT / "report.json"
REPORT_MD = OUT / "report.md"
RUN_LOG = OUT / "run.log"

EFFORT = "medium"
_lock = threading.Lock()


def log(*a: object) -> None:
    line = f"[{dt.datetime.now():%H:%M:%S}] " + " ".join(str(x) for x in a)
    print(line, file=sys.stderr, flush=True)
    with _lock:
        OUT.mkdir(parents=True, exist_ok=True)
        with RUN_LOG.open("a") as fh:
            fh.write(line + "\n")


def anchors_path(sha: str) -> Path:
    return CACHE / f"{sha}.anchors.json"


def snapshots() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(SNAPSHOTS.glob("*.json"))]


def work_items() -> tuple[list[dict], dict[str, list[str]]]:
    """Every blob to convert, and which instances each one belongs to.

    A blob qualifies when pass 1 cached it and it is not a test path — the same set `-nc` was built from, so `-sw` differs from
    `-nc` only in documentation."""
    blobs: dict[str, dict] = {}
    by_instance: dict[str, list[str]] = {}
    for snap in snapshots():
        instance = snap["instance_id"]
        shas: list[str] = []
        for entry in snap.get("files", []):
            if not entry.get("cached"):
                continue
            if pathrules.is_test_path(entry["path"]):
                continue
            sha = entry["blob_sha"]
            shas.append(sha)
            blobs.setdefault(sha, {"blob_sha": sha, "path": entry["path"],
                                   "repo": snap["repo"], "instances": []})
            blobs[sha]["instances"].append(instance)
        by_instance[instance] = shas
    return list(blobs.values()), by_instance


def needs_run(sha: str) -> bool:
    return not anchors_path(sha).exists()


def convert_blob(item: dict) -> str:
    """One blob: build the prompt, call the model, record the answer and the bill."""
    sha = item["blob_sha"]
    out = anchors_path(sha)
    if out.exists():
        return "skip"
    if pilot._stop.is_set():
        return "stopped"

    try:
        text, lines, records = pilot.blob_context(item)
    except Exception as exc:  # noqa: BLE001
        out.with_suffix(".failed.json").write_text(json.dumps({"error": f"prompt: {exc}"}))
        return "failed"

    if not records:
        # Nothing to document. Recorded, not skipped, so resume sees it as done.
        out.write_text(json.dumps({"blob_sha": sha, "path": item["path"], "records": 0,
                                   "anchors": [], "unanchorable": [], "usage": None}, indent=1))
        return "empty"

    prompt = pilot.build_user_prompt(item, text, lines, records)
    started = time.time()
    result = None
    attempts = []
    delay = 30
    for attempt in range(1, pilot.MAX_RETRIES + 1):
        if pilot._stop.is_set():
            return "stopped"
        r = pilot.call_model(prompt, EFFORT)
        attempts.append({"attempt": attempt, "ok": r["ok"], "error": r.get("error"),
                         "wall_ms": r["wall_ms"]})
        if r["ok"]:
            result = r["result"]
            break
        blob = json.dumps(r.get("result", ""))
        if "rate_limited" in blob or "spend limit" in blob:
            pilot._stop.set()
            log("hard block (usage/spend limit); stopping new work")
            return "blocked"
        time.sleep(delay)
        delay *= 2

    if result is None:
        out.with_suffix(".failed.json").write_text(json.dumps({"attempts": attempts}, indent=1))
        return "failed"

    so = result["structured_output"]
    payload = {
        "blob_sha": sha,
        "path": item["path"],
        "repo": item["repo"],
        "records": len(records),
        "anchors": so.get("anchors", []),
        "unanchorable": so.get("unanchorable", []),
        "usage": pilot.usage_of(result),
        "wall_ms": int(1000 * (time.time() - started)),
        "attempts": len(attempts),
        "model": pilot.MODEL,
        "effort": EFFORT,
    }
    out.write_text(json.dumps(payload, indent=1))
    return "ok"


def run(items: list[dict], jobs: int) -> dict:
    counts: collections.Counter = collections.Counter()
    todo = [i for i in items if needs_run(i["blob_sha"])]
    log(f"{len(items)} blobs, {len(todo)} to convert, {len(items) - len(todo)} already done")
    done = 0
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        futures = {ex.submit(convert_blob, i): i for i in todo}
        for fut in cf.as_completed(futures):
            try:
                counts[fut.result()] += 1
            except Exception as exc:  # noqa: BLE001
                counts["exception"] += 1
                log(f"exception: {exc!r}")
            done += 1
            if done % 50 == 0:
                spent = totals(load_results())
                log(f"  {done}/{len(todo)}  {dict(counts)}  "
                    f"${spent['cost_usd']:.2f}  {spent['wall_hours']:.1f}h of model time")
    log(f"done: {dict(counts)}")
    return dict(counts)


# ---------------------------------------------------------------------------------------------
# tokens and time
# ---------------------------------------------------------------------------------------------

def load_results() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in CACHE.glob("*.anchors.json"):
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        out[payload["blob_sha"]] = payload
    return out


def totals(results: dict[str, dict]) -> dict:
    """The bill. `wall` is model time — the sum of per-call durations, which at
    N-concurrent is N times the clock time the batch actually took."""
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
            "output_tokens", "thinking_tokens")
    # Seeded, so an instance with nothing converted yet still reports zeros
    # rather than missing keys.
    agg: collections.Counter = collections.Counter({k: 0 for k in keys})
    cost = wall_ms = calls = 0.0
    for payload in results.values():
        usage = payload.get("usage")
        if not usage:
            continue
        calls += 1
        for key in keys:
            agg[key] += usage.get(key) or 0
        cost += usage.get("opus_cost_usd") or 0
        wall_ms += payload.get("wall_ms") or 0
    return {
        "calls": int(calls),
        **{k: int(v) for k, v in agg.items()},
        "input_total": int(agg["input_tokens"] + agg["cache_creation_input_tokens"]),
        "cost_usd": round(cost, 2),
        "wall_hours": round(wall_ms / 3_600_000, 2),
    }


def per_instance(results: dict[str, dict], by_instance: dict[str, list[str]]) -> list[dict]:
    rows = []
    for instance, shas in sorted(by_instance.items()):
        subset = {s: results[s] for s in shas if s in results}
        row = {"instance_id": instance, "blobs": len(shas), "converted": len(subset)}
        row.update(totals(subset))
        row["records"] = sum(r.get("records", 0) for r in subset.values())
        row["anchored"] = sum(len(r.get("anchors") or []) for r in subset.values())
        row["unanchorable"] = sum(len(r.get("unanchorable") or []) for r in subset.values())
        rows.append(row)
    return rows


def report(items: list[dict], by_instance: dict[str, list[str]]) -> dict:
    results = load_results()
    overall = totals(results)
    rows = per_instance(results, by_instance)
    shared = len(items)
    naive = sum(len(shas) for shas in by_instance.values())
    calls = [r for r in results.values() if r.get("usage")]
    walls = sorted((r.get("wall_ms") or 0) / 1000 for r in calls)
    outs = sorted((r["usage"].get("output_tokens") or 0) for r in calls)

    summary = {
        "blobs_total": shared,
        "blobs_converted": len(results),
        "instance_file_pairs": naive,
        "dedup_saving": round(1 - shared / naive, 3) if naive else 0,
        "records": sum(r.get("records", 0) for r in results.values()),
        "anchored": sum(len(r.get("anchors") or []) for r in results.values()),
        "unanchorable": sum(len(r.get("unanchorable") or []) for r in results.values()),
        **overall,
        "wall_s_median": round(statistics.median(walls), 1) if walls else 0,
        "wall_s_p90": round(walls[int(0.9 * (len(walls) - 1))], 1) if walls else 0,
        "output_tokens_median": int(statistics.median(outs)) if outs else 0,
    }
    return {"summary": summary, "per_instance": rows,
            "generated": dt.datetime.now().isoformat(timespec="seconds")}


def write_report(data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(data, indent=1))
    s = data["summary"]
    L = ["# EST-119 — corpus conversion (-sw arm)\n",
         f"`{pilot.MODEL}` at effort **{EFFORT}**, headless `claude -p`. "
         f"Generated {data['generated']}.\n",
         "## Whole corpus\n",
         "| | |", "|---|---|",
         f"| blobs converted | {s['blobs_converted']:,} of {s['blobs_total']:,} |",
         f"| instance-file pairs | {s['instance_file_pairs']:,} |",
         f"| saved by content addressing | {s['dedup_saving']:.1%} |",
         f"| documentation records | {s['records']:,} |",
         f"| anchored / unanchorable | {s['anchored']:,} / {s['unanchorable']:,} |",
         f"| model calls | {s['calls']:,} |",
         f"| input tokens (uncached) | {s['input_total']:,} |",
         f"| cache-read tokens | {s['cache_read_input_tokens']:,} |",
         f"| output tokens | {s['output_tokens']:,} |",
         f"| thinking tokens | {s['thinking_tokens']:,} |",
         f"| model time | {s['wall_hours']:,} h |",
         f"| nominal cost | ${s['cost_usd']:,.2f} |",
         f"| median / p90 call | {s['wall_s_median']} s / {s['wall_s_p90']} s |",
         "",
         "Model time is the sum of per-call durations; at N-concurrent the clock time is "
         "roughly that divided by N.\n",
         "## Per instance\n",
         "| instance | blobs | done | records | anchored | unanch | output tok | model time h | $ |",
         "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for r in data["per_instance"]:
        L.append(f"| {r['instance_id']} | {r['blobs']:,} | {r['converted']:,} | {r['records']:,} | "
                 f"{r['anchored']:,} | {r['unanchorable']:,} | {r['output_tokens']:,} | "
                 f"{r['wall_hours']} | {r['cost_usd']:.2f} |")
    REPORT_MD.write_text("\n".join(L) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    r = sub.add_parser("run")
    r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--limit", type=int)
    r.add_argument("--only", nargs="*", help="instance ids")
    sub.add_parser("report")
    args = ap.parse_args(argv)

    items, by_instance = work_items()
    if args.cmd == "plan":
        todo = [i for i in items if needs_run(i["blob_sha"])]
        naive = sum(len(s) for s in by_instance.values())
        done = len(items) - len(todo)
        # EST-120 measured medium at ~4,082 output tokens, ~40 s, ~$0.27 per blob.
        log(f"instances {len(by_instance)}  instance-file pairs {naive:,}  "
            f"unique blobs {len(items):,}  already converted {done:,}  to run {len(todo):,}")
        log(f"projection at EST-120 v1 rates: ~${0.27 * len(todo):,.0f} nominal, "
            f"~{40 * len(todo) / 3600:,.0f} h model time (~{40 * len(todo) / 3600 / 4:,.0f} h at 4-concurrent)")
        return 0

    if args.cmd == "run":
        selected = items
        if args.only:
            keep = {s for i in args.only for s in by_instance.get(i, [])}
            selected = [i for i in items if i["blob_sha"] in keep]
        if args.limit:
            selected = [i for i in selected if needs_run(i["blob_sha"])][:args.limit]
        run(selected, args.jobs)
        write_report(report(items, by_instance))
        return 2 if pilot._stop.is_set() else 0

    data = report(items, by_instance)
    write_report(data)
    print(json.dumps(data["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
