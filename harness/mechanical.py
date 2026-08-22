"""Can the -sw corpus be built with no model at all? (EST-119 follow-up)

    .venv/bin/python -m harness.mechanical run --jobs 10
    .venv/bin/python -m harness.mechanical report

`harness/anchoring.py` answers "which node was this comment sitting on?" from the
comment's ORIGINAL POSITION, which is known for every blob in this corpus. This
script runs that path over all 11,609 blobs of `harness/convert_corpus.work_items()`
and, on the 5,448 blobs Opus already converted, puts the two side by side.

Nothing here calls a model. Placement is judged the same way `harness/model_bench.py`
judges it: an anchor is correct when the Rust resolver puts it within one line of
`convert_pilot.FileFacts.expected_lines`.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import os
import random
import re
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from harness import anchoring, astcheck, convert_corpus, inline, resolver, roundtrip, sidedoc, strip
from harness import convert_pilot as pilot
from harness import directives as directives_mod

CACHE = ROOT / "cache"
OUT = ROOT / "corpus" / "convert-corpus"
ROWS_JSON = OUT / "mechanical-rows.json"
REPORT_JSON = OUT / "mechanical.json"
REPORT_MD = OUT / "mechanical.md"

CHUNK = 32
_TIE = re.compile(r"~\d+")


def log(*a: object) -> None:
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------------------------
# the mechanical conversion, with a per-record trace
# ---------------------------------------------------------------------------------------------

class _Facts(pilot.FileFacts):
    """`FileFacts` without its resolver call: only `expected_lines` is wanted here."""

    def _index_lines(self):
        return {}


def trace_anchor(original: bytes, sidecar: list[dict], entries: list[dict]):
    """Run `anchoring._Anchorer` record by record, keeping which record got which anchor.

    `run()` throws that association away — it only needs the artifact. The head-to-head
    needs it, because Opus's answers are keyed by record id.
    """
    an = anchoring._Anchorer(original, sidecar, entries)
    by_anchor = resolver.by_anchor(entries)
    trace: list[dict] = []
    for i, rec in enumerate(an.records, 1):
        rid = f"r{i}"
        if rec.get("action") != "removed":
            trace.append({"id": rid, "status": "kept", "line": rec["line"],
                          "kind": rec["kind"]})
            continue
        n_rec, n_bad = len(an.out.records), len(an.out.unanchorable)
        if rec["kind"] == "docstring":
            an.do_docstring(rec)
        else:
            an.do_comment(rec)
        if len(an.out.records) > n_rec:
            got = an.out.records[-1]
            entry = by_anchor.get(got.anchor)
            trace.append({"id": rid, "status": "anchored", "anchor": got.anchor,
                          "kind": got.kind, "line": rec["line"],
                          "hint": entry["line"] if entry else None})
        elif len(an.out.unanchorable) > n_bad:
            trace.append({"id": rid, "status": "unanchorable", "line": rec["line"],
                          "reason": an.out.unanchorable[-1]["reason"]})
        else:
            trace.append({"id": rid, "status": "vanished", "line": rec["line"]})
    return an.out, trace


def fold_kind(kind: str | None) -> str:
    """`todo` is `lead`/`trail` plus a filter flag (FORMAT.md §3); the mechanical path
    never emits it, so comparing kinds has to fold it away."""
    return "lead" if kind == "todo" else (kind or "")


def bare(anchor: str) -> str:
    return _TIE.sub("", "".join(anchor.split()))


# ---------------------------------------------------------------------------------------------
# scoring: the resolver decides who is right
# ---------------------------------------------------------------------------------------------

def resolve_all(facts, rows: list[dict]) -> dict[str, dict]:
    """`{record id: outcome}` for anchors given as `{id, anchor, line}`."""
    if not rows:
        return {}
    outcomes = pilot.resolve_anchors(facts.utf8, [r["anchor"] for r in rows],
                                     [r.get("line") for r in rows])
    return {r["id"]: o for r, o in zip(rows, outcomes)}


def verdicts(facts, outcomes: dict[str, dict], by_id: dict[str, dict]) -> dict[str, dict]:
    """Per record: did the anchor resolve, and did it land on the record's real line (±1)."""
    out: dict[str, dict] = {}
    for rec in facts.records:
        rid = rec["id"]
        if rid not in outcomes:
            continue
        outcome = outcomes[rid]
        line = outcome.get("line")
        expected, _ambiguous = facts.expected_lines(rec)
        correct = (outcome["status"] == "found" and line is not None
                   and any(abs(line - e) <= 1 for e in expected))
        out[rid] = {"status": outcome["status"], "line": line, "correct": bool(correct),
                    "expected": expected}
    return out


# ---------------------------------------------------------------------------------------------
# one blob
# ---------------------------------------------------------------------------------------------

def analyse(item: dict, original: bytes, o_entries: list[dict], c_entries: list[dict],
            clean: bytes, sidecar: list[dict], directives) -> dict:
    sha = item["blob_sha"]
    row: dict = {"blob_sha": sha, "path": item["path"], "repo": item["repo"],
                 "bytes": len(original)}

    anchored, trace = trace_anchor(original, sidecar, o_entries)
    doc = sidedoc.write_sidedoc(anchored.records)
    row["records"] = len(trace)                      # every documentation record (§3 blocks)
    row["removed_records"] = sum(1 for t in trace if t["status"] != "kept")
    row["anchored"] = sum(1 for t in trace if t["status"] == "anchored")
    row["unanchorable"] = len(anchored.unanchorable)
    row["vanished"] = sum(1 for t in trace if t["status"] == "vanished")
    row["reasons"] = dict(collections.Counter(u["reason"] for u in anchored.unanchorable))

    # 1. the code is unchanged (migrate.py's first gate)
    code_ok, code_detail = astcheck.equal(original, clean, directives)
    row["code_ok"] = bool(code_ok)
    if not code_ok:
        row["code_detail"] = code_detail[:300]

    # 2. no prose is lost (migrate.py's second gate): reconstruct, re-strip, and look
    #    for every block's text in the inline view.
    rebuilt, notes = inline.reconstruct(clean, doc, entries=c_entries)
    _, resid = strip.strip_source(rebuilt, directives)
    declared = {roundtrip.doc_text(u["kind"], u.get("text", "")) for u in anchored.unanchorable}
    got = migrate_prose(resid, rebuilt)
    haystack = roundtrip._squash(" \0 ".join(got))
    dropped = [t for t in migrate_prose(sidecar, original)
               if t and t not in declared and roundtrip._squash(t) not in haystack]
    row["dropped"] = len(dropped)
    if dropped:
        row["dropped_sample"] = dropped[:3]
    row["orphaned"] = len(notes)
    row["exact"] = rebuilt == original

    # 2b. the same question asked of the *artifact* rather than of the round trip.
    #     `dropped` above can only fail a file once the reader has put the prose back,
    #     so a reader bug reads as lost prose. This asks whether the words are in the
    #     sidedoc at all, comparing on word characters only — every marker, banner rule
    #     and escape the format renormalises drops out of both sides.
    want_words = [_words(t) for t in migrate_prose(sidecar, original)]
    _front, parsed = sidedoc.parse_sidedoc(doc)
    hay_words = " \0 ".join(
        [_words(p.body) for p in parsed] + [_words(q.body) for p in parsed for q in p.parts]
        + [_words(u.get("text", "")) for u in anchored.unanchorable])
    absent = [w for w in want_words if w and w not in hay_words]
    row["sidedoc_missing"] = len(absent)
    if absent:
        row["sidedoc_missing_sample"] = absent[:3]

    # 3. head to head, where Opus has an answer for this blob
    opus_path = CACHE / f"{sha}.anchors.json"
    if opus_path.exists():
        try:
            row.update(head_to_head(item, trace, json.loads(opus_path.read_text())))
        except Exception as exc:  # noqa: BLE001
            row["compare_error"] = f"{type(exc).__name__}: {exc}"
    return row


def _words(text: str) -> str:
    """Word characters only: what is left of a block once every rendering convention
    the format is allowed to renormalise (markers, banner rules, quotes, escapes,
    indentation) is taken out."""
    return re.sub(r"[^0-9A-Za-z]+", " ", text).strip()


def migrate_prose(sidecar, source: bytes) -> list[str]:
    lines = strip.split_lines(anchoring._decode(source))
    return [t for t in roundtrip.documentation(sidecar, lines) if t]


def head_to_head(item: dict, trace: list[dict], opus: dict) -> dict:
    out: dict = {"opus": True}
    if not opus.get("usage") and not opus.get("anchors"):
        out["opus_empty"] = True
    facts = _Facts({"blob_sha": item["blob_sha"], "path": item["path"], "repo": item["repo"]})
    if len(facts.records) != len(trace):
        out["compare_error"] = f"record count {len(facts.records)} != {len(trace)}"
        return out

    mech = {t["id"]: t for t in trace}
    o_anchor = {a["id"]: a for a in (opus.get("anchors") or [])}
    o_bad = {u["id"]: u for u in (opus.get("unanchorable") or [])}

    m_rows = [{"id": t["id"], "anchor": t["anchor"], "line": t.get("hint")}
              for t in trace if t["status"] == "anchored"]
    o_rows = [{"id": a["id"], "anchor": a["anchor"], "line": a.get("line")}
              for a in o_anchor.values()]
    m_v = verdicts(facts, resolve_all(facts, m_rows), mech)
    o_v = verdicts(facts, resolve_all(facts, o_rows), o_anchor)

    counts: collections.Counter = collections.Counter()
    samples: list[dict] = []
    gaveup: list[dict] = []
    for rec in facts.records:
        rid = rec["id"]
        t = mech[rid]
        m_state = t["status"]
        o_state = ("anchored" if rid in o_anchor else
                   "unanchorable" if rid in o_bad else "missing")
        if m_state == "kept":
            counts["kept_in_source"] += 1
            continue
        counts["compared"] += 1
        counts[f"mech_{m_state}"] += 1
        counts[f"opus_{o_state}"] += 1
        if m_state != "anchored" or o_state != "anchored":
            counts["not_both_anchored"] += 1
            # The interesting half: mechanical gave up where Opus did not. Was Opus right?
            if m_state == "unanchorable" and o_state == "anchored":
                ov = o_v.get(rid)
                counts["mech_gaveup_opus_correct" if ov and ov["correct"] else
                       "mech_gaveup_opus_wrong"] += 1
                if len(gaveup) < 1:
                    gaveup.append({
                        "path": item["path"], "id": rid, "reason": t.get("reason"),
                        "text": (rec.get("text") or rec.get("first_line") or "")[:120],
                        "opus": o_anchor[rid]["anchor"], "opus_kind": o_anchor[rid]["kind"],
                        "opus_correct": bool(ov and ov["correct"]),
                        "opus_status": ov and ov["status"]})
            elif o_state == "unanchorable" and m_state == "anchored":
                mv = m_v.get(rid)
                counts["opus_gaveup_mech_correct" if mv and mv["correct"] else
                       "opus_gaveup_mech_wrong"] += 1
            continue

        same_text = bare(t["anchor"]) == bare(o_anchor[rid]["anchor"])
        same_kind = fold_kind(t["kind"]) == fold_kind(o_anchor[rid]["kind"])
        mv, ov = m_v.get(rid), o_v.get(rid)
        same_target = bool(mv and ov and mv["line"] is not None and mv["line"] == ov["line"])
        counts["same_anchor_text"] += same_text
        counts["same_kind"] += same_kind
        counts["same_target_line"] += same_target
        counts["mech_correct"] += bool(mv and mv["correct"])
        counts["opus_correct"] += bool(ov and ov["correct"])
        counts["mech_resolved"] += bool(mv and mv["status"] == "found")
        counts["opus_resolved"] += bool(ov and ov["status"] == "found")
        if same_text:
            continue
        counts["differ"] += 1
        m_ok, o_ok = bool(mv and mv["correct"]), bool(ov and ov["correct"])
        counts["differ_both_right" if m_ok and o_ok else
               "differ_mech_right" if m_ok else
               "differ_opus_right" if o_ok else "differ_neither_right"] += 1
        if len(samples) < 2:
            samples.append({
                "path": item["path"], "blob_sha": item["blob_sha"], "id": rid,
                "rkind": rec["rkind"], "record_line": rec["line"],
                "text": (rec.get("text") or rec.get("first_line") or "")[:160],
                "mech": t["anchor"], "mech_kind": t["kind"],
                "opus": o_anchor[rid]["anchor"], "opus_kind": o_anchor[rid]["kind"],
                "mech_line": mv and mv["line"], "opus_line": ov and ov["line"],
                "mech_status": mv and mv["status"], "opus_status": ov and ov["status"],
                "expected": mv["expected"] if mv else (ov["expected"] if ov else None),
                "mech_correct": m_ok, "opus_correct": o_ok,
            })
    out["cmp"] = dict(counts)
    out["samples"] = samples
    out["gaveup"] = gaveup
    return out


# ---------------------------------------------------------------------------------------------
# batching
# ---------------------------------------------------------------------------------------------

def do_chunk(items: list[dict]) -> list[dict]:
    directives = directives_mod.load()
    raw = roundtrip.blobs([i["blob_sha"] for i in items])
    rows: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        prepared: dict[str, tuple] = {}
        for item in items:
            sha = item["blob_sha"]
            original = raw.get(sha)
            if original is None:
                rows.append({"blob_sha": sha, "path": item["path"], "error": "blob missing"})
                continue
            try:
                clean, sidecar = strip.strip_source(original, directives)
                otext = anchoring._decode(original).replace("\r\n", "\n").replace("\r", "\n")
                ctext = anchoring._decode(clean).replace("\r\n", "\n").replace("\r", "\n")
            except Exception as exc:  # noqa: BLE001
                rows.append({"blob_sha": sha, "path": item["path"],
                             "error": f"strip: {type(exc).__name__}: {exc}"})
                continue
            op, cp = tmpdir / f"o{sha}.py", tmpdir / f"c{sha}.py"
            op.write_text(otext, encoding="utf-8")
            cp.write_text(ctext, encoding="utf-8")
            prepared[sha] = (item, original, clean, sidecar, op, cp)
        indexed = resolver.index_files([p for v in prepared.values() for p in v[4:6]])
        for sha, (item, original, clean, sidecar, op, cp) in prepared.items():
            if str(op) not in indexed or str(cp) not in indexed:
                rows.append({"blob_sha": sha, "path": item["path"], "error": "does not parse"})
                continue
            try:
                rows.append(analyse(item, original, indexed[str(op)], indexed[str(cp)],
                                    clean, sidecar, directives))
            except Exception as exc:  # noqa: BLE001
                rows.append({"blob_sha": sha, "path": item["path"],
                             "error": f"{type(exc).__name__}: {exc}",
                             "trace": traceback.format_exc(limit=4)})
    return rows


def run(items: list[dict], jobs: int) -> list[dict]:
    chunks = [items[i:i + CHUNK] for i in range(0, len(items), CHUNK)]
    rows: list[dict] = []
    with cf.ProcessPoolExecutor(max_workers=jobs) as ex:
        for i, part in enumerate(ex.map(do_chunk, chunks), 1):
            rows.extend(part)
            if i % 20 == 0:
                log(f"  {len(rows)}/{len(items)} blobs")
    return rows


# ---------------------------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------------------------

def summarise(rows: list[dict], by_instance: dict[str, list[str]]) -> dict:
    ok = [r for r in rows if "error" not in r]
    reasons: collections.Counter = collections.Counter()
    cmp_total: collections.Counter = collections.Counter()
    for r in ok:
        reasons.update(r.get("reasons") or {})
        cmp_total.update(r.get("cmp") or {})
    records = sum(r["removed_records"] for r in ok)
    with_opus = [r for r in ok if r.get("opus")]

    per_blob = {r["blob_sha"]: r for r in ok}
    inst_rows = []
    for instance, shas in sorted(by_instance.items()):
        subset = [per_blob[s] for s in shas if s in per_blob]
        rec = sum(r["removed_records"] for r in subset)
        una = sum(r["unanchorable"] for r in subset)
        inst_rows.append({
            "instance_id": instance, "blobs": len(shas), "analysed": len(subset),
            "records": rec, "unanchorable": una,
            "rate": round(una / rec, 5) if rec else 0,
            "dropped": sum(r["dropped"] for r in subset),
            "sidedoc_missing": sum(r.get("sidedoc_missing", 0) for r in subset),
            "code_changed": sum(1 for r in subset if not r["code_ok"]),
        })

    summary = {
        "blobs": len(rows),
        "analysed": len(ok),
        "errors": len(rows) - len(ok),
        "records": records,
        "records_kept_in_source": sum(r["records"] - r["removed_records"] for r in ok),
        "anchored": sum(r["anchored"] for r in ok),
        "unanchorable": sum(r["unanchorable"] for r in ok),
        "unanchorable_rate": round(sum(r["unanchorable"] for r in ok) / records, 5) if records else 0,
        "vanished": sum(r["vanished"] for r in ok),
        "dropped": sum(r["dropped"] for r in ok),
        "files_dropping_prose": sum(1 for r in ok if r["dropped"]),
        "sidedoc_missing": sum(r.get("sidedoc_missing", 0) for r in ok),
        "files_missing_from_sidedoc": sum(1 for r in ok if r.get("sidedoc_missing")),
        "code_changed": sum(1 for r in ok if not r["code_ok"]),
        "orphaned": sum(r["orphaned"] for r in ok),
        "byte_exact": sum(1 for r in ok if r["exact"]),
        "reasons": dict(reasons.most_common()),
        "blobs_with_opus": len(with_opus),
        "cmp": dict(cmp_total),
    }
    return {"summary": summary, "per_instance": inst_rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    r.add_argument("--limit", type=int)
    sub.add_parser("report")
    args = ap.parse_args(argv)

    items, by_instance = convert_corpus.work_items()
    if args.cmd == "run":
        if args.limit:
            items = items[:args.limit]
            keep = {i["blob_sha"] for i in items}
            by_instance = {k: [s for s in v if s in keep] for k, v in by_instance.items()}
        log(f"{len(items)} blobs, {args.jobs} jobs")
        rows = run(items, args.jobs)
        OUT.mkdir(parents=True, exist_ok=True)
        ROWS_JSON.write_text(json.dumps(rows))
    else:
        rows = json.loads(ROWS_JSON.read_text())

    data = summarise(rows, by_instance)
    pool = [s for r in rows for s in (r.get("samples") or [])]
    random.Random(11).shuffle(pool)
    data["disagreements"] = pool[:20]
    data["errors"] = [{k: v for k, v in r.items() if k != "trace"}
                      for r in rows if "error" in r][:40]
    REPORT_JSON.write_text(json.dumps(data, indent=1))
    print(json.dumps(data["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
