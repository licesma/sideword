#!/usr/bin/env python3
"""The sweep: `harness/evaluate.py` over instances × arms × models, resumably.

    uv run --extra eval python -m harness.sweep run --dry-run          # the plan, in order
    uv run --extra eval python -m harness.sweep run --jobs 2           # run it (resumable)
    uv run --extra eval python -m harness.sweep report                 # corpus/eval/report.{json,md}

`evaluate.py` is one (instance, arm, model) and writes
`corpus/eval/<model>/<arm>/<instance_id>.json`. This module is everything above it:
which runs exist, in what order, how many at once, when to stop, and what the records
add up to.

Selection
---------
Instances are `corpus/admission.json`'s `usable_instances` — the ones whose three arms
each score their own gold patch resolved and an empty patch unresolved. The excluded
ones are never run: an arm that cannot discriminate cannot measure, and a record from
it would only have to be filtered out later. `--instances`, `--arms` and `--models`
narrow the product; asking for an excluded instance is an error, not a silent drop.

Resume
------
The unit is the record file. A record that parses, carries a `scoring` block and was
not cut short by the account's allowance is done and is skipped. Anything else —
missing, unparsable, blocked, incomplete — is rerun, and whatever was there is moved
aside as `<instance>.stale-<timestamp>.json` so the evidence survives and the report
never counts it. A crash, a spend-limit block or a laptop that fell asleep therefore
costs exactly the runs that were in flight.

Order
-----
Instances are shuffled with a fixed seed (recorded in the sweep log and manifest),
and within an instance every model and every arm runs back to back. Adjacent arms
are the point: models drift, the account throttles, the machine gets busy, and an
effect that lands on one instance's three arms within the same hour lands on all
three roughly equally, instead of on whichever arm happened to be running that day.
The arm order rotates per instance so that the arm which pays for a cold image is
not always the same one.

Two runs never share an (instance, arm) at the same time, whatever `--jobs` says:
`evaluate.py` names its scoring container `sweval-score-<instance>-<arm>` with no
model in the name, and starting one removes any other by that name.

Stopping
--------
`--max-runs` and `--max-cost` stop launching; work already in flight finishes and is
recorded. A hard block — `evaluate.py` reporting `allowance-exhausted`, or its output
matching the account-blocked patterns — stops launching too, so a sweep never
retries into the wall.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import random
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from harness import evaluate

ADMISSION = ROOT / "corpus" / "admission.json"
EVAL_ROOT = evaluate.EVAL_ROOT
ARMS = list(evaluate.ARMS)
DEFAULT_MODELS = ["claude-opus-4-1", "claude-opus-5"]
DEFAULT_SEED = 2026
CONFIG_DIR_VAR = "SIDEWORD_CLAUDE_CONFIG_DIR"
SPEND_EVERY = 3           # print running spend after this many completions

DONE = "done"
TODO = "todo"

_lock = threading.Lock()


def log(message: str, root: Path | None = None) -> None:
    line = "[%s] %s" % (dt.datetime.now().strftime("%H:%M:%S"), message)
    print(line, file=sys.stderr, flush=True)
    if root is not None:
        with _lock:
            root.mkdir(parents=True, exist_ok=True)
            with (root / "sweep.log").open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")


# ---- selection ---------------------------------------------------------------------------

def load_admission(path: Path = ADMISSION) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def select_instances(admission: dict, only: list[str] | None = None) -> list[str]:
    """The usable instances, or the requested subset of them.

    Requesting something outside `usable_instances` is refused rather than dropped:
    an excluded instance was excluded because an arm of it cannot measure anything,
    and a typo should not silently shrink the sweep.
    """
    usable = list(admission["usable_instances"])
    if not only:
        return usable
    excluded = {e["instance_id"] for e in admission.get("excluded_instances", [])}
    bad = [i for i in only if i not in usable]
    if bad:
        why = ["%s (excluded by admission)" % i if i in excluded else "%s (unknown)" % i
               for i in bad]
        raise SystemExit("not usable: %s" % ", ".join(why))
    keep = set(only)
    return [i for i in usable if i in keep]


def select_arms(only: list[str] | None) -> list[str]:
    if not only:
        return list(ARMS)
    bad = [a for a in only if a not in ARMS]
    if bad:
        raise SystemExit("unknown arm(s) %s; expected %s" % (", ".join(bad), ", ".join(ARMS)))
    return [a for a in ARMS if a in set(only)]


# ---- the plan ----------------------------------------------------------------------------

def order(instances: list[str], arms: list[str], models: list[str],
          seed: int) -> list[dict]:
    """Every run, in the order it should go.

    Instance order is a seeded shuffle. Inside an instance the loop is model, then
    arm, so all of one instance's runs are contiguous and one model's arms are
    contiguous within that. The arm order rotates by one per instance — a fixed
    rotation of the canonical order, not a shuffle, so any two arms stay as often
    before each other as after.
    """
    rng = random.Random(seed)
    shuffled = list(instances)
    rng.shuffle(shuffled)
    plan = []
    for k, instance in enumerate(shuffled):
        shift = k % len(arms) if arms else 0
        rotated = arms[shift:] + arms[:shift]
        for model in models:
            for arm in rotated:
                plan.append({"instance_id": instance, "arm": arm, "model": model})
    return plan


def record_file(root: Path, item: dict) -> Path:
    return evaluate.record_path(root, item["model"], item["arm"], item["instance_id"], "agent")


def record_state(path: Path) -> tuple[str, str]:
    """`(state, why)`: `done` when the record is complete, otherwise `todo` and why."""
    if not path.exists():
        return TODO, "missing"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return TODO, "unparsable"
    return record_state_of(record)


def record_state_of(record: dict) -> tuple[str, str]:
    if not isinstance(record, dict) or record.get("schema") != "sideword-eval-1":
        return TODO, "not an eval record"
    if record.get("source") != "agent":
        return TODO, "not an agent run (%s)" % record.get("source")
    kinds = {e.get("kind") for e in record.get("errors") or []}
    if "allowance-exhausted" in kinds:
        return TODO, "blocked by the account allowance"
    if "scoring" not in record or "resolved" not in (record.get("scoring") or {}):
        return TODO, "never scored"
    if "agent" not in record:
        return TODO, "no agent block"
    return DONE, "recorded"


def plan(instances: list[str], arms: list[str], models: list[str], *, seed: int,
         root: Path = EVAL_ROOT) -> list[dict]:
    """`order()` plus the resume scan: each item carries `state` and `why`."""
    items = order(instances, arms, models, seed)
    for item in items:
        item["state"], item["why"] = record_state(record_file(root, item))
    return items


# ---- one run -----------------------------------------------------------------------------

def set_aside(path: Path) -> Path | None:
    """Move a record that is about to be rerun out of the report's way, keeping it."""
    if not path.exists():
        return None
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    dest = path.with_name("%s.stale-%s.json" % (path.stem, stamp))
    path.rename(dest)
    return dest


def evaluate_command(item: dict, extra: list[str] | None = None) -> list[str]:
    return [sys.executable, "-m", "harness.evaluate",
            "--instance", item["instance_id"], "--arm", item["arm"],
            "--model", item["model"], *(extra or [])]


def config_dir() -> str:
    """The account every run bills. Unset is an error: the CLI's fallback is `~/.claude`,
    which is the wrong account here, and it would spend it silently."""
    value = os.environ.get(CONFIG_DIR_VAR)
    if not value:
        raise SystemExit(
            "%s is not set. It selects the account the runs bill; set it explicitly:\n"
            "    export %s=$HOME/.claude2" % (CONFIG_DIR_VAR, CONFIG_DIR_VAR))
    if not Path(value).is_dir():
        raise SystemExit("%s=%s is not a directory" % (CONFIG_DIR_VAR, value))
    return value


def outcome_of(record_path: Path, output: str, returncode: int) -> str:
    """What one finished `evaluate.py` amounts to: `ok`, `blocked` or `failed`.

    The record wins when there is one: `evaluate.py` exits 0 after an allowance
    block, having written the block into `errors`, so the exit code alone cannot
    tell a blocked run from a finished one. Without a record, the captured output is
    checked against the same patterns `evaluate.py` uses to recognise a block.
    """
    state, why = record_state(record_path)
    if state == DONE:
        return "ok"
    if "blocked" in why:
        return "blocked"
    if evaluate.HARD_BLOCK_RE.search(output) or "rate_limited" in output:
        return "blocked"
    return "failed"


def launch_run(item: dict, *, root: Path, extra: list[str], env: dict,
               logger=log) -> str:
    """Run `evaluate.py` once as a subprocess, its output in `<instance>.run.log`."""
    target = record_file(root, item)
    state, _ = record_state(target)
    if state == DONE:
        return "skip"
    set_aside(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    log_path = target.with_name("%s.run.log" % item["instance_id"])
    cmd = evaluate_command(item, ["--out", str(root), *extra])
    started = time.time()
    with open(log_path, "w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env,
                              stdout=fh, stderr=subprocess.STDOUT, check=False)
    output = log_path.read_text(encoding="utf-8", errors="replace")
    outcome = outcome_of(target, output[-20000:], proc.returncode)
    logger("%-6s %s %s %s  rc=%d  %.0fs" % (outcome, item["instance_id"], item["arm"],
                                            item["model"], proc.returncode, time.time() - started))
    return outcome


# ---- the loop ----------------------------------------------------------------------------

def load_records(root: Path = EVAL_ROOT, *, models: list[str] | None = None,
                 arms: list[str] | None = None) -> list[dict]:
    """Every complete agent record under `root`. Suffixed files — `.gold`, `.empty`,
    `.dryrun`, `.script`, `.traj`, `.stale-*` — have a dot in the stem and are not."""
    out = []
    for model_dir in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        if models and model_dir.name not in models:
            continue
        for arm_dir in sorted(p for p in model_dir.iterdir() if p.is_dir()):
            if arm_dir.name not in ARMS or (arms and arm_dir.name not in arms):
                continue
            for path in sorted(arm_dir.glob("*.json")):
                if "." in path.stem:
                    continue
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if record_state_of(record)[0] == DONE:
                    out.append(record)
    return out


def spend(root: Path) -> float:
    return round(sum((r.get("agent") or {}).get("cost_usd") or 0 for r in load_records(root)), 4)


def run_sweep(items: list[dict], *, jobs: int, root: Path, max_runs: int | None = None,
              max_cost: float | None = None, launch=None, logger=log) -> dict:
    """Drain the plan with `jobs` workers, in order, stopping when told to.

    Returns counts per outcome plus `stopped` — `None`, `max-runs`, `max-cost` or
    `blocked`. Workers take the first queued item whose (instance, arm) is not in
    flight; see the module docstring for why that pair is the exclusion key.
    """
    launch = launch or launch_run
    queue = collections.deque(i for i in items if i.get("state", TODO) != DONE)
    total = len(queue)
    in_flight: set[tuple[str, str]] = set()
    state = {"launched": 0, "completed": 0, "stopped": None}
    counts: collections.Counter = collections.Counter()
    stop = threading.Event()

    def take() -> dict | None:
        while True:
            with _lock:
                if stop.is_set() or not queue:
                    return None
                if max_runs is not None and state["launched"] >= max_runs:
                    state["stopped"] = "max-runs"
                    stop.set()
                    return None
                if max_cost is not None and spend(root) >= max_cost:
                    state["stopped"] = "max-cost"
                    stop.set()
                    return None
                for idx, item in enumerate(queue):
                    key = (item["instance_id"], item["arm"])
                    if key not in in_flight:
                        del queue[idx]
                        in_flight.add(key)
                        state["launched"] += 1
                        return item
            time.sleep(1)      # everything queued collides with a run in flight

    def worker() -> None:
        while True:
            item = take()
            if item is None:
                return
            try:
                outcome = launch(item)
            except Exception as exc:  # noqa: BLE001
                outcome = "exception"
                logger("exception in %s %s %s: %r" % (item["instance_id"], item["arm"],
                                                     item["model"], exc))
            announce = False
            with _lock:                    # `logger` takes `_lock` too: log outside it
                in_flight.discard((item["instance_id"], item["arm"]))
                item["outcome"] = outcome
                counts[outcome] += 1
                state["completed"] += 1
                if outcome == "blocked" and not stop.is_set():
                    state["stopped"] = "blocked"
                    stop.set()
                    announce = True
                due = state["completed"] % SPEND_EVERY == 0
            if announce:
                logger("hard block (account allowance); not launching more")
            if due:
                logger("  %d/%d done  %s  spent $%.2f so far"
                       % (state["completed"], total, dict(counts), spend(root)))

    threads = [threading.Thread(target=worker, name="sweep-%d" % i, daemon=True)
               for i in range(max(1, jobs))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    logger("done: %s  stopped=%s  spent $%.2f" % (dict(counts), state["stopped"], spend(root)))
    return {"counts": dict(counts), "stopped": state["stopped"],
            "launched": state["launched"], "completed": state["completed"]}


def print_plan(items: list[dict], *, seed: int, jobs: int) -> None:
    done = sum(1 for i in items if i["state"] == DONE)
    print("seed %d  jobs %d  %d runs: %d done, %d to run" % (
        seed, jobs, len(items), done, len(items) - done))
    width = max((len(i["instance_id"]) for i in items), default=10)
    for n, item in enumerate(items, 1):
        mark = "skip" if item["state"] == DONE else "run "
        print("%3d  %s  %-*s  %-4s  %-16s  %s" % (
            n, mark, width, item["instance_id"], item["arm"], item["model"], item["why"]))


# ---- report ------------------------------------------------------------------------------

def _tokens(record: dict) -> dict:
    t = (record.get("agent") or {}).get("tokens") or {}
    out = {k: int(t.get(k) or 0) for k in ("input", "output", "cache_read", "cache_creation")}
    out["billed"] = out["input"] + out["cache_creation"] + out["output"]
    return out


def _stat(values: list) -> dict:
    values = [v for v in values if v is not None]
    if not values:
        return {"mean": None, "median": None}
    return {"mean": round(statistics.fmean(values), 1), "median": statistics.median(values)}


def arm_summary(records: list[dict]) -> dict:
    n = len(records)
    resolved = sum(1 for r in records if (r.get("scoring") or {}).get("resolved"))
    toks = [_tokens(r) for r in records]
    agents = [r.get("agent") or {} for r in records]
    out = {
        "n": n,
        "resolved": resolved,
        "resolve_rate": round(resolved / n, 3) if n else None,
        "tokens": {k: _stat([t[k] for t in toks])
                   for k in ("input", "output", "cache_read", "cache_creation", "billed")},
        "wall_s": _stat([r.get("wall_s") for r in records]),
        "turns": _stat([a.get("n_calls") for a in agents]),
        "cost_usd": round(sum(a.get("cost_usd") or 0 for a in agents), 4),
        "files_read": _stat([(r.get("files_read_counts") or {}).get("source",
                                                                   r.get("files_read_count"))
                             for r in records]),
        "errors": sum(1 for r in records if r.get("errors")),
    }
    if records and records[0].get("arm") == "sw":
        out["sideword_files_read"] = _stat(
            [(r.get("files_read_counts") or {}).get("sideword", 0) for r in records])
        out["sideword_calls"] = _stat([r.get("sideword_call_count", 0) for r in records])
    return out


def paired(records: list[dict], arms: list[str]) -> list[dict]:
    """One row per instance that has every arm in `arms`, for one model."""
    by_instance: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    for r in records:
        by_instance[r["instance_id"]][r["arm"]] = r
    rows = []
    for instance in sorted(by_instance):
        have = by_instance[instance]
        if any(a not in have for a in arms):
            continue
        row = {"instance_id": instance, "arms": {}}
        for arm in arms:
            r = have[arm]
            counts = r.get("files_read_counts") or {}
            row["arms"][arm] = {
                "resolved": bool((r.get("scoring") or {}).get("resolved")),
                **_tokens(r),
                "turns": (r.get("agent") or {}).get("n_calls"),
                "wall_s": r.get("wall_s"),
                "files_read": counts.get("source", r.get("files_read_count")),
                "sideword_files_read": counts.get("sideword", 0),
                "sideword_calls": r.get("sideword_call_count", 0),
            }
        rows.append(row)
    return rows


def report(root: Path = EVAL_ROOT, *, admission: dict | None = None,
           models: list[str] | None = None, arms: list[str] | None = None) -> dict:
    admission = admission or load_admission()
    usable = set(admission["usable_instances"])
    arms = arms or list(ARMS)
    every = load_records(root, models=models, arms=arms)
    records = [r for r in every if r["instance_id"] in usable]
    strays = sorted({"%s/%s/%s" % (r["model"], r["arm"], r["instance_id"])
                     for r in every if r["instance_id"] not in usable})
    per_model: dict[str, dict] = {}
    for model in sorted({r["model"] for r in records}):
        mine = [r for r in records if r["model"] == model]
        per_model[model] = {
            "arms": {arm: arm_summary([r for r in mine if r["arm"] == arm]) for arm in arms},
            "paired": paired(mine, arms),
        }
        per_model[model]["paired_n"] = len(per_model[model]["paired"])
    return {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "usable_instances": len(usable),
        "arms": arms,
        "records": len(records),
        "cost_usd": round(sum((r.get("agent") or {}).get("cost_usd") or 0 for r in records), 4),
        "stray_records": strays,
        "per_model": per_model,
    }


def _fmt(value, digits: int = 0) -> str:
    if value is None:
        return "–"
    if isinstance(value, float) and digits:
        return "{:,.{d}f}".format(value, d=digits)
    return "{:,}".format(int(round(value)))


def _mm(stat: dict, digits: int = 0) -> str:
    return "%s / %s" % (_fmt(stat["mean"], digits), _fmt(stat["median"], digits))


def render_markdown(data: dict) -> str:
    arms = data["arms"]
    L = ["# Sideword sweep — results\n",
         "Generated %s. %d complete records over %d admitted instances, $%.2f of model "
         "time. Every table below is sliced by model, then by arm." % (
             data["generated"], data["records"], data["usable_instances"], data["cost_usd"]),
         ""]
    if not data["per_model"]:
        L.append("No records yet.\n")
        return "\n".join(L)
    ns = ["%s: n = %d" % (m, d["paired_n"]) for m, d in data["per_model"].items()]
    L += ["**Paired n (instances with all of %s):** %s." % (", ".join(arms), "; ".join(ns)),
          "",
          "At this n the resolve rate cannot separate a small effect between arms — one "
          "instance flipping moves it by %s — while per-instance token counts are paired "
          "within-instance measurements with far smaller spread, and can." % (
              "/".join("%.0f%%" % (100 / d["paired_n"]) if d["paired_n"] else "∞"
                       for d in data["per_model"].values())),
          ""]
    if data["stray_records"]:
        L += ["Records for instances outside the admitted set, not counted: %s."
              % ", ".join("`%s`" % s for s in data["stray_records"]), ""]

    for model, d in data["per_model"].items():
        L += ["## %s\n" % model,
              "Mean / median unless stated. Billed = input + cache creation + output; "
              "cache read is listed apart. Files read counts source files only.\n",
              "| arm | n | resolved | rate | billed tok | cache-read tok | input tok | "
              "output tok | cache-create tok | wall s | turns | files read | .sideword read | "
              "sideword calls | $ |",
              "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
        for arm in arms:
            s = d["arms"][arm]
            rate = "–" if s["resolve_rate"] is None else "%.0f%%" % (100 * s["resolve_rate"])
            L.append("| %s | %d | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %.2f |" % (
                arm, s["n"], s["resolved"], rate,
                _mm(s["tokens"]["billed"]), _mm(s["tokens"]["cache_read"]),
                _mm(s["tokens"]["input"]), _mm(s["tokens"]["output"]),
                _mm(s["tokens"]["cache_creation"]),
                _mm(s["wall_s"]), _mm(s["turns"], 1), _mm(s["files_read"]),
                _mm(s["sideword_files_read"]) if "sideword_files_read" in s else "–",
                _mm(s["sideword_calls"], 1) if "sideword_calls" in s else "–",
                s["cost_usd"]))
        L.append("")
        rows = d["paired"]
        L += ["### Paired — %s, n = %d\n" % (model, len(rows)),
              "Instances with every arm recorded, so each row compares the arms on the "
              "same task. Resolved is ✓/✗ per arm in the order %s.\n" % " · ".join(arms)]
        if not rows:
            L.append("None yet.\n")
            continue
        head = "| instance | resolved | " + " | ".join("%s billed" % a for a in arms) + \
               " | " + " | ".join("%s cache-read" % a for a in arms) + \
               " | " + " | ".join("%s output" % a for a in arms) + " |"
        L += [head, "|---|:-:|" + "--:|" * (3 * len(arms))]
        for row in rows:
            cells = row["arms"]
            res = " ".join("✓" if cells[a]["resolved"] else "✗" for a in arms)
            L.append("| %s | %s | %s | %s | %s |" % (
                row["instance_id"], res,
                " | ".join(_fmt(cells[a]["billed"]) for a in arms),
                " | ".join(_fmt(cells[a]["cache_read"]) for a in arms),
                " | ".join(_fmt(cells[a]["output"]) for a in arms)))
        L.append("")
        head = "| instance | " + " | ".join("%s turns" % a for a in arms) + \
               " | " + " | ".join("%s files" % a for a in arms) + \
               " | sw .sideword read | sw sideword calls | " + \
               " | ".join("%s wall s" % a for a in arms) + " |"
        L += [head, "|---|" + "--:|" * (3 * len(arms) + 2)]
        for row in rows:
            cells = row["arms"]
            sw = cells.get("sw", {})
            L.append("| %s | %s | %s | %s | %s | %s |" % (
                row["instance_id"],
                " | ".join(_fmt(cells[a]["turns"]) for a in arms),
                " | ".join(_fmt(cells[a]["files_read"]) for a in arms),
                _fmt(sw.get("sideword_files_read")) if sw else "–",
                _fmt(sw.get("sideword_calls")) if sw else "–",
                " | ".join(_fmt(cells[a]["wall_s"]) for a in arms)))
        L.append("")
    return "\n".join(L)


def write_report(data: dict, root: Path = EVAL_ROOT) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    json_path, md_path = root / "report.json", root / "report.md"
    json_path.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(data), encoding="utf-8")
    return json_path, md_path


# ---- CLI ---------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="harness.sweep",
                                 description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--instances", nargs="*", help="instance ids (default: all usable)")
        p.add_argument("--arms", nargs="*", help="arms (default: %s)" % " ".join(ARMS))
        p.add_argument("--models", nargs="*", help="models (default: %s)" % " ".join(DEFAULT_MODELS))
        p.add_argument("--out", default=None, help="record root (default corpus/eval)")
        p.add_argument("--admission", default=None, help="admission file (default corpus/admission.json)")

    r = sub.add_parser("run", help="run the plan, resumably")
    common(r)
    r.add_argument("--jobs", type=int, default=2, help="concurrent runs (default 2)")
    r.add_argument("--seed", type=int, default=DEFAULT_SEED, help="instance order seed")
    r.add_argument("--max-runs", type=int, default=None, help="launch at most this many")
    r.add_argument("--max-cost", type=float, default=None,
                   help="stop launching once summed cost_usd across records reaches this")
    r.add_argument("--dry-run", action="store_true", help="print the plan in order; run nothing")
    r.add_argument("--effort", default=None, choices=["low", "medium", "high", "xhigh", "max"],
                   help="passed through to evaluate.py")
    r.add_argument("--evaluate-arg", action="append", default=[], metavar="ARG",
                   help="extra argument passed through to evaluate.py verbatim (repeatable)")

    p = sub.add_parser("report", help="write corpus/eval/report.{json,md}")
    common(p)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.out) if args.out else EVAL_ROOT
    admission = load_admission(Path(args.admission) if args.admission else ADMISSION)
    instances = select_instances(admission, args.instances)
    arms = select_arms(args.arms)
    models = args.models or list(DEFAULT_MODELS)

    if args.cmd == "report":
        data = report(root, admission=admission, models=args.models, arms=arms)
        json_path, md_path = write_report(data, root)
        print(md_path.read_text(encoding="utf-8"))
        print("wrote %s and %s" % (json_path, md_path), file=sys.stderr)
        return 0

    items = plan(instances, arms, models, seed=args.seed, root=root)
    if args.dry_run:
        print_plan(items, seed=args.seed, jobs=args.jobs)
        return 0

    account = config_dir()
    env = dict(os.environ, **{CONFIG_DIR_VAR: account})
    extra = list(args.evaluate_arg)
    if args.effort:
        extra += ["--effort", args.effort]
    logger = lambda m: log(m, root)  # noqa: E731
    todo = [i for i in items if i["state"] != DONE]
    logger("sweep: seed %d, jobs %d, %d instances x %d arms x %d models = %d runs; "
           "%d done, %d to run; billing %s=%s; spent $%.2f so far" % (
               args.seed, args.jobs, len(instances), len(arms), len(models), len(items),
               len(items) - len(todo), len(todo), CONFIG_DIR_VAR, account, spend(root)))
    for item in todo:
        if item["why"] != "missing":
            logger("rerun %s %s %s: %s" % (item["instance_id"], item["arm"], item["model"],
                                          item["why"]))
    started = dt.datetime.now(dt.timezone.utc)
    result = run_sweep(items, jobs=args.jobs, root=root, max_runs=args.max_runs,
                       max_cost=args.max_cost,
                       launch=lambda item: launch_run(item, root=root, extra=extra, env=env,
                                                      logger=logger),
                       logger=logger)
    manifest = {
        "started": started.isoformat(timespec="seconds"),
        "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "seed": args.seed, "jobs": args.jobs, "max_runs": args.max_runs,
        "max_cost": args.max_cost, "effort": args.effort, "evaluate_args": extra,
        "instances": instances, "arms": arms, "models": models,
        "config_dir": account, "result": result,
        "plan": [{k: i.get(k) for k in ("instance_id", "arm", "model", "state", "why", "outcome")}
                 for i in items],
    }
    sweeps = root / "sweeps"
    sweeps.mkdir(parents=True, exist_ok=True)
    (sweeps / ("%s.json" % started.strftime("%Y%m%dT%H%M%SZ"))).write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    write_report(report(root, admission=admission, arms=arms), root)
    return 2 if result["stopped"] == "blocked" else 0


if __name__ == "__main__":
    sys.exit(main())
