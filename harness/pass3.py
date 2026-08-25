"""Pass 3: the Sideword artifacts for every cached blob, without a model.

    uv run python -m harness.pass3            # convert all 11,609
    uv run python -m harness.pass3 --check    # verify only, write nothing

For each blob this writes two files beside the strip cache:

    cache/<sha>.sw.md     the sidedoc   (FORMAT.md §5)
    cache/<sha>.sw.idx    the index     (FORMAT.md §4)

Content-addressed like pass 1, so a blob shared by several instances is
converted once, and a rerun is a no-op.

**No model is involved.** A comment in an existing repository already sits beside
what it describes, so its anchor is a parse and a lookup — that is what
`harness/anchoring.py` does. The model was answering a different question (can
an anchor be *chosen* from scratch, with no position to read), which matters for
authoring and not for migration.

The trade is that this is positionally faithful and semantically blind: a comment
written inside a body but *about* the enclosing function files under the
statement it precedes. Docstrings are unaffected — Python's grammar hands those
to the owning symbol — and they are ~31% of records.

`cache/<sha>.anchors.json`, the model's output for 5,448 of these blobs, is left
strictly alone. It cost $815, it cannot be regenerated for free, and it is the
only dataset that could settle the semantic question later.

Two gates per blob, and a failure writes nothing for that blob:

* the clean source is AST-equal to the original, with the `# noqa` family intact;
* no documentation block goes missing without being reported (§6).
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from harness import anchoring, astcheck, convert_corpus, roundtrip, sidedoc, strip
from harness import directives as directives_mod

CACHE = ROOT / "cache"
REPORT_JSON = ROOT / "corpus" / "pass3-report.json"
REPORT_MD = ROOT / "corpus" / "pass3-report.md"
BATCH = 200

_D = None


def directives():
    global _D
    if _D is None:
        _D = directives_mod.load()
    return _D


def sidedoc_path(sha: str) -> Path:
    return CACHE / f"{sha}.sw.md"


def index_path(sha: str) -> Path:
    return CACHE / f"{sha}.sw.idx"


def keep_owners_of(sha: str) -> list[tuple[str, str]]:
    """The docstring context pass 1 stripped this blob under (``stats.keep_owners``)."""
    p = CACHE / f"{sha}.jsonl"
    try:
        lines = [l for l in p.read_text(encoding="utf-8").split("\n") if l]
    except OSError:
        return []
    return strip.keep_owners_from_sidecar(json.loads(l) for l in lines[-1:])


def convert(sha: str, path: str, original: bytes, check: bool) -> dict:
    row = {"blob_sha": sha, "path": path}
    keep_owners = keep_owners_of(sha)
    try:
        art = anchoring.convert(original, directives(), keep_owners)
    except Exception as exc:  # noqa: BLE001 — one bad blob must not stop the corpus
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row

    anchored = art["anchored"]
    row["records"] = len(art["records"])
    row["unanchorable"] = len(anchored.unanchorable)

    ok, detail = astcheck.equal(original, art["source"], directives(), keep_owners)
    row["code_ok"] = ok
    if not ok:
        row["code_detail"] = detail[:200]

    declared = {roundtrip.doc_text(u["kind"], u.get("text", "")) for u in anchored.unanchorable}
    lines = strip.split_lines(anchoring._decode(original))
    want = [t for t in roundtrip.documentation(art["sidecar"], lines) if t]
    have = roundtrip._squash(" \0 ".join(
        roundtrip.doc_text("comment", r.body) if r.kind != "doc" else r.body
        for r in art["records"]))
    row["dropped"] = sum(1 for t in want
                         if t not in declared and roundtrip._squash(t) not in have)

    if not ok or row["dropped"]:
        return row                      # gated: write nothing for this blob

    doc = art["sidedoc"]
    index = sidedoc.write_index(path, art["records"], doc)
    row["written"] = False
    if not check:
        sidedoc_path(sha).write_text(doc, encoding="utf-8")
        index_path(sha).write_text(index, encoding="utf-8")
        row["written"] = True
    row["sidedoc_bytes"] = len(doc.encode())
    row["index_bytes"] = len(index.encode())
    return row


def _star(args):
    return convert(*args)


def run(items: list[dict], jobs: int, check: bool, force: bool) -> list[dict]:
    todo = [i for i in items
            if force or check or not sidedoc_path(i["blob_sha"]).exists()]
    done = len(items) - len(todo)
    print(f"{len(items):,} blobs, {len(todo):,} to convert, {done:,} already done",
          file=sys.stderr, flush=True)

    rows: list[dict] = []
    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        sources = roundtrip.blobs([i["blob_sha"] for i in chunk])
        work = [(i["blob_sha"], i["path"], sources[i["blob_sha"]], check)
                for i in chunk if i["blob_sha"] in sources]
        with cf.ProcessPoolExecutor(max_workers=jobs) as ex:
            rows.extend(ex.map(_star, work, chunksize=4))
        print(f"  {min(start + BATCH, len(todo)):,}/{len(todo):,}", file=sys.stderr, flush=True)
    return rows


def summarise(rows: list[dict], by_instance: dict[str, list[str]]) -> dict:
    ok = [r for r in rows if "error" not in r]
    records = sum(r.get("records", 0) for r in ok)
    unanch = sum(r.get("unanchorable", 0) for r in ok)
    per_instance = []
    have = {r["blob_sha"] for r in ok if r.get("written") or r.get("sidedoc_bytes")}
    for instance, shas in sorted(by_instance.items()):
        uniq = set(shas)
        per_instance.append({
            "instance_id": instance, "blobs": len(uniq),
            "converted": sum(1 for s in uniq if sidedoc_path(s).exists()),
        })
    return {
        "blobs": len(rows),
        "errors": len(rows) - len(ok),
        "gated_code_changed": sum(1 for r in ok if not r.get("code_ok", True)),
        "gated_prose_lost": sum(1 for r in ok if r.get("dropped")),
        "records": records,
        "unanchorable": unanch,
        "unanchorable_rate": round(unanch / records, 6) if records else 0,
        "sidedoc_bytes": sum(r.get("sidedoc_bytes", 0) for r in ok),
        "index_bytes": sum(r.get("index_bytes", 0) for r in ok),
        "instances_complete": sum(1 for r in per_instance if r["converted"] == r["blobs"]),
        "per_instance": per_instance,
    }


def write_report(summary: dict) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(summary, indent=1))
    L = ["# Pass 3 report (Sideword artifacts, mechanical)\n",
         "No model. Anchors derive from the position each comment already occupied.\n",
         "| | |", "|---|---|",
         f"| blobs | {summary['blobs']:,} |",
         f"| errors | {summary['errors']} |",
         f"| gated: code changed | {summary['gated_code_changed']} |",
         f"| gated: prose lost | {summary['gated_prose_lost']} |",
         f"| documentation records | {summary['records']:,} |",
         f"| unanchorable | {summary['unanchorable']:,} ({summary['unanchorable_rate']:.4%}) |",
         f"| sidedoc bytes | {summary['sidedoc_bytes']:,} |",
         f"| index bytes | {summary['index_bytes']:,} |",
         f"| instances fully converted | {summary['instances_complete']}/30 |",
         "", "## Per instance\n",
         "| instance | blobs | converted |", "|---|--:|--:|"]
    for r in summary["per_instance"]:
        L.append(f"| {r['instance_id']} | {r['blobs']:,} | {r['converted']:,} |")
    REPORT_MD.write_text("\n".join(L) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="verify only; write nothing")
    ap.add_argument("--force", action="store_true", help="reconvert blobs already done")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args(argv)

    items, by_instance = convert_corpus.work_items()
    if args.limit:
        items = items[:args.limit]

    rows = run(items, args.jobs, args.check, args.force)
    summary = summarise(rows, by_instance)
    if not args.check:
        write_report(summary)
    printable = {k: v for k, v in summary.items() if k != "per_instance"}
    print(json.dumps(printable, indent=1))

    for r in rows:
        if "error" in r:
            print(f"ERROR {r['path']}: {r['error']}", file=sys.stderr)
        elif not r.get("code_ok", True):
            print(f"CODE CHANGED {r['path']}: {r.get('code_detail','')[:160]}", file=sys.stderr)
        elif r.get("dropped"):
            print(f"PROSE LOST {r['path']}: {r['dropped']} record(s)", file=sys.stderr)

    bad = summary["errors"] + summary["gated_code_changed"] + summary["gated_prose_lost"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
