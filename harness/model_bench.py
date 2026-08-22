"""Compare a candidate model against Opus on blobs Opus has already converted.

    .venv/bin/python -m harness.model_bench --model claude-haiku-4-5 -n 20

The 5,448 blobs converted for EST-119 are an eval set with *known answers*: the
original line of every comment is on record, so placement is scored
mechanically and no model's output is treated as truth. Opus 5 medium is the
high-water mark to beat, not the reference.

Reports the two numbers that decide whether a cheaper model can do this job:
placement accuracy, and cost per blob — which on a subscription is also the
allowance meter, since the limit that blocks a batch is denominated in dollars.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import random
import statistics
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from harness import convert_pilot as pilot

CACHE = ROOT / "cache"
OUT = ROOT / "corpus" / "model-bench"
ENV_FILE = Path.home() / ".config" / "sideword" / "env"

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def secret(name: str) -> str:
    """Keys live in ~/.config/sideword/env (mode 600), never in the repo."""
    if os.environ.get(name):
        return os.environ[name]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip().removeprefix("export ").strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit(f"{name} not set; put it in {ENV_FILE}")


def gemini_schema(schema: dict) -> dict:
    """Gemini rejects `additionalProperties`; the rest of our schema is already
    the OpenAPI subset it accepts."""
    if isinstance(schema, dict):
        return {k: gemini_schema(v) for k, v in schema.items() if k != "additionalProperties"}
    if isinstance(schema, list):
        return [gemini_schema(v) for v in schema]
    return schema


def call_gemini(prompt: str, model: str, thinking: int | None) -> dict:
    """One Gemini call. Same system prompt, same schema, same scoring as Claude —
    only the transport differs."""
    config: dict = {
        "responseMimeType": "application/json",
        "responseJsonSchema": gemini_schema(pilot.JSON_SCHEMA),
    }
    if thinking is not None:
        config["thinkingConfig"] = {"thinkingBudget": thinking}
    body = {
        "systemInstruction": {"parts": [{"text": pilot.SYSTEM_PROMPT_FILE.read_text()}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": config,
    }
    url = GEMINI_URL.format(model=model) + "?key=" + secret("GEMINI_API_KEY")
    t0 = time.time()
    payload = None
    # The free tier throttles hard (a few requests per minute), and a 429 here
    # says nothing about the model — retry it rather than record it as a miss.
    for attempt in range(6):
        request = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=pilot.CALL_TIMEOUT_S) as response:
                payload = json.loads(response.read())
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:400].decode("utf-8", "replace")
            if exc.code == 429 and attempt < 5:
                time.sleep(8 * (attempt + 1))
                continue
            return {"ok": False, "error": f"http {exc.code}", "raw": detail,
                    "wall_ms": int(1000 * (time.time() - t0))}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": type(exc).__name__, "raw": str(exc)[:300],
                    "wall_ms": int(1000 * (time.time() - t0))}
    if payload is None:
        return {"ok": False, "error": "429 after retries",
                "wall_ms": int(1000 * (time.time() - t0))}
    wall = int(1000 * (time.time() - t0))

    candidates = payload.get("candidates") or []
    if not candidates:
        return {"ok": False, "error": "no-candidates", "raw": json.dumps(payload)[:400],
                "wall_ms": wall}
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    try:
        structured = json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "error": "bad-json", "raw": text[:400], "wall_ms": wall}

    usage = payload.get("usageMetadata", {})
    return {"ok": True, "wall_ms": wall, "structured": structured, "usage": {
        "input_tokens": usage.get("promptTokenCount", 0),
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": usage.get("cachedContentTokenCount", 0),
        "output_tokens": usage.get("candidatesTokenCount", 0),
        "thinking_tokens": usage.get("thoughtsTokenCount", 0),
        # Gemini does not price the call for us; tokens are the honest unit here.
        "total_cost_usd": None,
    }}

def supports_effort(model: str) -> bool:
    """The CLI accepts `--effort` on Haiku 4.5 too, despite the API-level rule
    that effort is an Opus-family control — and it matters more there than
    anywhere: without it Haiku spends 91% of its output on thinking."""
    return model.startswith("claude-")


def cmd(model: str, effort: str) -> list[str]:
    argv = ["claude", "-p", "--model", model]
    if supports_effort(model):
        argv += ["--effort", effort]
    return argv + [
        "--system-prompt-file", str(pilot.SYSTEM_PROMPT_FILE),
        "--no-session-persistence", "--output-format", "json", "--tools", "",
        "--json-schema", json.dumps(pilot.JSON_SCHEMA, separators=(",", ":")),
    ]


def call(prompt: str, model: str, effort: str) -> dict:
    t0 = time.time()
    try:
        proc = subprocess.run(cmd(model, effort), input=prompt, capture_output=True, text=True,
                              env=pilot.clean_env(), timeout=pilot.CALL_TIMEOUT_S,
                              cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "wall_ms": int(1000 * (time.time() - t0))}
    wall = int(1000 * (time.time() - t0))
    out = proc.stdout.strip()
    result = None
    for candidate in (out, out.splitlines()[-1] if out else ""):
        try:
            result = json.loads(candidate)
            break
        except Exception:
            continue
    if result is None:
        return {"ok": False, "error": f"no-json rc={proc.returncode}",
                "stderr": proc.stderr[-400:], "wall_ms": wall}
    if result.get("is_error") or result.get("structured_output") is None:
        return {"ok": False, "error": result.get("is_error") and "is_error" or "no-structured-output",
                "raw": json.dumps(result)[:400], "wall_ms": wall}
    return {"ok": True, "result": result, "wall_ms": wall}


def score(entry: dict, anchors: list[dict]) -> dict:
    """Placement against the record's real line — mechanical, no model involved."""
    facts = pilot.FileFacts(entry)
    by_id = {a["id"]: a for a in anchors}
    texts = [a["anchor"] for a in anchors]
    hints = [a.get("line") for a in anchors]
    outcomes = pilot.resolve_anchors(facts.utf8, texts, hints)
    outcome_by_id = {a["id"]: o for a, o in zip(anchors, outcomes)}

    status: collections.Counter = collections.Counter()
    correct = considered = 0
    for rec in facts.records:
        got = by_id.get(rec["id"])
        if got is None:
            status["unanchorable_or_dropped"] += 1
            continue
        outcome = outcome_by_id[rec["id"]]
        status[outcome["status"]] += 1
        considered += 1
        line = outcome.get("line")
        if outcome["status"] == "found" and line is not None:
            expected, _ = facts.expected_lines(rec)
            if any(abs(line - e) <= 1 for e in expected):
                correct += 1
    return {"records": len(facts.records), "considered": considered,
            "correct": correct, "status": dict(status)}


def one(entry: dict, model: str, effort: str, thinking: int | None = None) -> dict:
    sha = entry["blob_sha"]
    text, lines, records = pilot.blob_context(entry)
    if not records:
        return {"blob_sha": sha, "skipped": "no records"}
    prompt = pilot.build_user_prompt(entry, text, lines, records)

    if model.startswith("gemini"):
        r = call_gemini(prompt, model, thinking)
        so, usage = (r.get("structured"), r.get("usage")) if r["ok"] else (None, None)
    else:
        r = call(prompt, model, effort)
        so = r["result"]["structured_output"] if r["ok"] else None
        usage = pilot.usage_of(r["result"]) if r["ok"] else None

    if not r["ok"]:
        return {"blob_sha": sha, "path": entry["path"], "error": r.get("error"),
                "detail": r.get("raw") or r.get("stderr"), "wall_ms": r["wall_ms"]}
    row = {"blob_sha": sha, "path": entry["path"], "wall_ms": r["wall_ms"],
           "usage": usage, "unanchorable": len(so.get("unanchorable") or [])}
    row.update(score(entry, so.get("anchors") or []))
    return row


def opus_baseline(shas: list[str]) -> dict:
    """The same blobs as Opus already scored them, re-scored the same way."""
    rows = []
    for sha in shas:
        payload = json.loads((CACHE / f"{sha}.anchors.json").read_text())
        entry = {"blob_sha": sha, "path": payload["path"], "repo": payload.get("repo"),
                 "bytes": 0}
        row = {"blob_sha": sha, "wall_ms": payload.get("wall_ms"), "usage": payload["usage"],
               "unanchorable": len(payload.get("unanchorable") or [])}
        row.update(score(entry, payload.get("anchors") or []))
        rows.append(row)
    return summarise(rows, "claude-opus-5")


def summarise(rows: list[dict], model: str) -> dict:
    ok = [r for r in rows if "error" not in r and "skipped" not in r]
    considered = sum(r["considered"] for r in ok)
    correct = sum(r["correct"] for r in ok)
    found = sum(r["status"].get("found", 0) for r in ok)
    cost = sum((r["usage"] or {}).get("total_cost_usd") or 0 for r in ok)
    out_tok = sum((r["usage"] or {}).get("output_tokens") or 0 for r in ok)
    walls = [r["wall_ms"] / 1000 for r in ok if r.get("wall_ms")]
    return {
        "model": model,
        "blobs": len(rows), "ok": len(ok), "errors": len(rows) - len(ok),
        "records": sum(r["records"] for r in ok),
        "anchored": considered,
        "unanchorable": sum(r["unanchorable"] for r in ok),
        "resolve": round(found / considered, 4) if considered else 0,
        "placement": round(correct / considered, 4) if considered else 0,
        "cost_usd": round(cost, 4),
        "cost_per_blob": round(cost / len(ok), 5) if ok else 0,
        "output_tokens": out_tok,
        "wall_s_median": round(statistics.median(walls), 1) if walls else 0,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--thinking", type=int, default=None,
                    help="Gemini thinkingBudget; 0 disables thinking")
    args = ap.parse_args(argv)

    # Blobs Opus converted *and* that carry real documentation, so the
    # comparison is on files where the job is non-trivial.
    pool = []
    for path in CACHE.glob("*.anchors.json"):
        payload = json.loads(path.read_text())
        if payload.get("usage") and (payload.get("anchors") or []):
            pool.append((payload["blob_sha"], payload["path"], payload.get("repo")))
    pool.sort()
    random.Random(args.seed).shuffle(pool)
    chosen = pool[:args.n]
    entries = [{"blob_sha": s, "path": p, "repo": r, "bytes": 0} for s, p, r in chosen]
    pilot.log(f"{len(entries)} blobs, model {args.model}"
              f"{' effort ' + args.effort if supports_effort(args.model) else ' (no effort flag)'}")

    rows: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for row in ex.map(lambda e: one(e, args.model, args.effort, args.thinking), entries):
            rows.append(row)
            tag = row.get("error") or f"{row.get('correct')}/{row.get('considered')}"
            pilot.log(f"  {row['blob_sha'][:8]} {tag}")

    candidate = summarise(rows, args.model)
    # Compare like with like: a blob the candidate failed on (a provider 429,
    # say) must not be scored for Opus either, or the baseline is measured on a
    # different set of files than the candidate.
    succeeded = [r["blob_sha"] for r in rows if "error" not in r and "skipped" not in r]
    baseline = opus_baseline(succeeded)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{args.model}.json").write_text(json.dumps(
        {"candidate": candidate, "baseline": baseline, "rows": rows}, indent=1))

    width = max(len(candidate["model"]), len(baseline["model"]))
    print(f"\n{'metric':16} {baseline['model']:>{width}} {candidate['model']:>{width}}")
    for key in ("blobs", "errors", "records", "anchored", "unanchorable",
                "resolve", "placement", "cost_per_blob", "output_tokens", "wall_s_median"):
        b, c = baseline[key], candidate[key]
        fmt = (lambda v: f"{v:.1%}") if key in ("resolve", "placement") else (
            (lambda v: f"${v:.5f}") if key == "cost_per_blob" else (lambda v: f"{v:,}"))
        print(f"{key:16} {fmt(b):>{width}} {fmt(c):>{width}}")
    if candidate["cost_per_blob"] and baseline["cost_per_blob"]:
        ratio = baseline["cost_per_blob"] / candidate["cost_per_blob"]
        print(f"\n{candidate['model']} is {ratio:.1f}x cheaper per blob "
              f"({candidate['placement']:.1%} vs {baseline['placement']:.1%} placement)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
