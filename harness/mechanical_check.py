"""Can the benchmark corpus be converted without a model?

    .venv/bin/python -m harness.mechanical_check --limit 500
    .venv/bin/python -m harness.mechanical_check            # all 11,609

`harness/anchoring.py` anchors each record from the position the comment
occupied in the original file. For a *migration* that position is known, so the
question "which anchor?" is a parse and a lookup, not a judgement — which is
what a model was being paid to supply.

The two outcomes that would rule mechanical conversion out are prose going
missing and code changing. A merely higher unanchorable rate would not: those
records are reported, per `FORMAT.md` §6, not lost.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from harness import anchoring, astcheck, convert_corpus, roundtrip, strip
from harness import directives as directives_mod

CACHE = ROOT / "cache"
OUT = ROOT / "corpus" / "convert-corpus"
BATCH = 200

_D = None


def directives():
    global _D
    if _D is None:
        _D = directives_mod.load()
    return _D


def one(sha: str, path: str, original: bytes) -> dict:
    row = {"blob_sha": sha, "path": path}
    try:
        art = anchoring.convert(original, directives())
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row

    anchored = art["anchored"]
    row["records"] = len(art["records"])
    row["unanchorable"] = len(anchored.unanchorable)
    row["reasons"] = collections.Counter(u["reason"] for u in anchored.unanchorable)

    # The code must be untouched: same AST, tool directives still in place.
    ok, detail = astcheck.equal(original, art["source"], directives())
    row["code_ok"] = ok
    if not ok:
        row["code_detail"] = detail[:200]

    # No prose may vanish unreported. Same content test the round trip uses.
    declared = {roundtrip.doc_text(u["kind"], u.get("text", "")) for u in anchored.unanchorable}
    lines = strip.split_lines(anchoring._decode(original))
    want = [t for t in roundtrip.documentation(art["sidecar"], lines) if t]
    have = roundtrip._squash(" \0 ".join(
        roundtrip.doc_text("comment", r.body) if r.kind != "doc" else r.body
        for r in art["records"]))
    row["dropped"] = sum(1 for t in want
                         if t not in declared and roundtrip._squash(t) not in have)
    return row


def run(items: list[dict], jobs: int) -> list[dict]:
    rows: list[dict] = []
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        sources = roundtrip.blobs([i["blob_sha"] for i in chunk])
        work = [(i["blob_sha"], i["path"], sources[i["blob_sha"]])
                for i in chunk if i["blob_sha"] in sources]
        with cf.ProcessPoolExecutor(max_workers=jobs) as ex:
            rows.extend(ex.map(_star, work, chunksize=4))
        print(f"  {min(start + BATCH, len(items))}/{len(items)}", file=sys.stderr, flush=True)
    return rows


def _star(args):
    return one(*args)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default=str(OUT / "mechanical.json"))
    args = ap.parse_args(argv)

    items, by_instance = convert_corpus.work_items()
    if args.limit:
        items = list(items)
        random.Random(args.seed).shuffle(items)
        items = items[:args.limit]
    print(f"{len(items):,} blobs", file=sys.stderr)

    rows = run(items, args.jobs)
    ok = [r for r in rows if "error" not in r]
    reasons: collections.Counter = collections.Counter()
    for r in ok:
        reasons.update(r.get("reasons") or {})
    records = sum(r["records"] for r in ok)
    unanch = sum(r["unanchorable"] for r in ok)

    summary = {
        "blobs": len(rows),
        "errors": len(rows) - len(ok),
        "records": records,
        "unanchorable": unanch,
        "unanchorable_rate": round(unanch / records, 5) if records else 0,
        "files_code_changed": sum(1 for r in ok if not r["code_ok"]),
        "files_losing_prose": sum(1 for r in ok if r["dropped"]),
        "records_dropped": sum(r["dropped"] for r in ok),
        "reasons": dict(reasons.most_common(8)),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": [
        {k: (dict(v) if isinstance(v, collections.Counter) else v) for k, v in r.items()}
        for r in rows]}, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
