"""The round trip: original -> strip -> artifacts -> reconstruct -> original.

    .venv/bin/python -m harness.roundtrip --sample        # the 100-blob pilot sample
    .venv/bin/python -m harness.roundtrip --all --limit 2000
    .venv/bin/python -m harness.roundtrip --shas <sha> --diff

For every blob it checks three things, weakest to strongest:

1. **byte-exact** — the reconstruction is the original, byte for byte. Where it is not,
   the diff is classified, because the interesting question is *why*: `FORMAT.md` is
   normative about how a record renders (two spaces before a `trail`, `# ` before a
   comment, triple-double-quotes around a docstring), so legacy source written another
   way comes back normalised. That is a format finding, not a bug.
2. **code-identical** — stripping the reconstruction returns the clean source exactly.
   The reader may only add prose; if it moves, drops or rewrites a line of code, this
   fails.
3. **records preserved** — every documentation block comes back, once. This is the check
   that would have caught the collision: two records sharing an (anchor, kind) slot, with
   no tie to tell them apart, silently become one.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import difflib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
    from harness import anchoring, directives as directives_mod, inline, resolver, sidedoc, strip
else:
    from . import anchoring, directives as directives_mod, inline, resolver, sidedoc, strip

CACHE = ROOT / "cache"
MIRROR = Path.home() / "repos" / "sideword-corpus"
SAMPLE = ROOT / "corpus" / "convert-pilot" / "sample.json"
REPORT = ROOT / "corpus" / "roundtrip-report.json"
REPORT_MD = ROOT / "corpus" / "roundtrip-report.md"

BATCH = 64

_TRAIL = re.compile(r"^(?P<code>.*\S)(?P<gap>[ \t]+)#(?P<rest>.*)$")
_LEADING_HASH = re.compile(r"^(?P<indent>[ \t]*)#(?P<rest>.*)$")
_QUOTE_PREFIX = re.compile(r"(?<![\w])[rRuUbBfF]{1,3}(?=\"\"\"|''')")
_LONE_STRING = re.compile(r"^(?P<indent>\s*)(?P<q>\"|')(?P<body>(?:(?!(?P=q)).)*)(?P=q)$")


# ---- corpus access ----------------------------------------------------------------------

def blobs(shas: list[str]) -> dict[str, bytes]:
    """Read many blobs from the mirror with one `git cat-file --batch`."""
    proc = subprocess.Popen(["git", "-C", str(MIRROR), "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    out: dict[str, bytes] = {}
    proc.stdin.write(("\n".join(shas) + "\n").encode())
    proc.stdin.close()
    for _ in shas:
        header = proc.stdout.readline().decode().split()
        if len(header) < 3:
            continue
        sha, _kind, size = header[0], header[1], int(header[2])
        out[sha] = proc.stdout.read(size)
        proc.stdout.read(1)
    proc.wait()
    return out


def sidecar_of(sha: str) -> list[dict]:
    path = CACHE / f"{sha}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---- diff classification -----------------------------------------------------------------

def canonical(line: str) -> str:
    """A line with everything `FORMAT.md` normalises away taken out.

    Two lines with the same canonical form differ only in ways the format does not carry,
    so the difference is a rendering convention rather than lost information.
    """
    line = line.rstrip("\r\n")
    line = _QUOTE_PREFIX.sub("", line).replace("'''", '"""')
    lone = _LONE_STRING.match(line)
    if lone:            # a docstring written with single quotes is still a docstring
        line = '{}"""{}"""'.format(lone.group("indent"), lone.group("body"))
    trail = _TRAIL.match(line)
    if trail and not _leading_comment(line):
        rest = trail.group("rest")
        return f"{trail.group('code')}  #{' ' + rest.lstrip() if rest.strip() else ''}"
    lead = _LEADING_HASH.match(line)
    if lead:
        rest = lead.group("rest")
        return f"#{' ' + rest.lstrip() if rest.strip() else ''}"      # indent normalised too
    return line


def _leading_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def classify(original: bytes, rebuilt: bytes) -> list[str]:
    """Why these two differ, in the format's own terms.

    Whole-file first: if every non-blank line survives in order once rendering is
    normalised, then nothing was lost and the only differences are how the format renders
    and where it puts the blank lines. Only when that fails is a per-hunk reading needed,
    and only then can a difference mean something went missing.
    """
    a = original.decode("utf-8", "replace").splitlines()
    b = rebuilt.decode("utf-8", "replace").splitlines()
    reasons: set[str] = set()

    live_a, live_b = [x for x in a if x.strip()], [x for x in b if x.strip()]
    if [canonical(x) for x in live_a] == [canonical(x) for x in live_b]:
        if [canonical(x) if x.strip() else "" for x in a] != \
                [canonical(x) if x.strip() else "" for x in b]:
            reasons.add("blank-line placement")
        if live_a != live_b:
            reasons.update(_normalisation_reasons(live_a, live_b))
        return sorted(reasons)

    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        left, right = a[i1:i2], b[j1:j2]
        if [canonical(x) for x in left] == [canonical(x) for x in right]:
            reasons.update(_normalisation_reasons(left, right))
            continue
        lean, rean = [x for x in left if x.strip()], [x for x in right if x.strip()]
        if [canonical(x) for x in lean] == [canonical(x) for x in rean]:
            # same text, different distribution of the blank lines around it
            reasons.add("blank-line placement")
            if lean != rean:
                reasons.update(_normalisation_reasons(lean, rean))
            continue
        if sorted(canonical(x) for x in lean) == sorted(canonical(x) for x in rean):
            reasons.add("record moved")
            continue
        if _only_pass(lean, rean):
            # `"""doc"""` alone and `"""doc"""` + `pass` strip to the same clean source
            reasons.add("pass ambiguity")
            continue
        reasons.add("content differs")
    return sorted(reasons)


def _only_pass(left: list[str], right: list[str]) -> bool:
    """The two sides agree except for a `pass` the clean source cannot account for."""
    keep = lambda xs: [canonical(x) for x in xs if x.strip() != "pass"]
    return keep(left) == keep(right) and left != right


def _normalisation_reasons(left: list[str], right: list[str]) -> set[str]:
    out: set[str] = set()
    for x, y in zip(left, right):
        if x == y:
            continue
        if _leading_comment(x) or _leading_comment(y):
            if x.lstrip() == y.lstrip():
                out.add("comment indent")
            elif x.lstrip().rstrip() != y.lstrip().rstrip():
                out.add("comment marker spacing")
            else:
                out.add("comment marker spacing")
            continue
        tx, ty = _TRAIL.match(x), _TRAIL.match(y)
        if tx and ty and tx.group("gap") != ty.group("gap"):
            out.add("trailing comment gap")
            continue
        if '"""' in y or "'''" in x:
            out.add("docstring quote style")
            continue
        out.add("whitespace")
    if len(left) != len(right):
        out.add("whitespace")
    return out or {"whitespace"}


# ---- the round trip ----------------------------------------------------------------------

def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def doc_text(kind: str, text: str) -> str:
    """One record's prose, with everything the format is allowed to renormalise
    taken off: comment markers, string prefixes, quote style. What is left is
    the payload, and losing *that* is the only real loss."""
    if kind == "comment":
        # Strip the marker *and* any banner run of `#`, from both sides. A
        # `#### BEGIN LICENSE ####` line comes back as `# ### BEGIN ...` once
        # the writer re-renders the marker, which moves a `#` into the body
        # without changing a word of the prose.
        body = "\n".join(re.sub(r"^[#\s]+", "", line).rstrip() for line in text.split("\n"))
    else:
        body = re.sub(r'^[rbuRBUfF]+(?=[\'"])', "", text.strip()).strip("\"' \n\t")
    return body.strip()


def documentation(sidecar: list[dict], lines: list[str]) -> list[str]:
    """Every documentation block's text, normalised — the thing that must not be lost."""
    out = []
    for rec in anchoring.doc_records(sidecar, lines):
        if rec.get("action") != "removed":
            continue
        out.append(doc_text(rec["kind"], rec["text"]))
    return out


def run_one(entry: dict, original: bytes, orig_entries: list[dict], clean_entries: list[dict],
            directives, keep_diff: bool = False) -> dict:
    sha = entry["blob_sha"]
    result = {"blob_sha": sha, "repo": entry.get("repo"), "path": entry.get("path"),
              "bytes": len(original)}
    clean = (CACHE / f"{sha}.py").read_bytes()
    sidecar = sidecar_of(sha)

    anchored = anchoring.anchor_records(original, sidecar, orig_entries)
    doc = sidedoc.write_sidedoc(anchored.records)
    index = sidedoc.write_index(entry.get("path", sha), anchored.records, doc)
    result["records"] = len(anchored.records)
    result["index_lines"] = index.count("\n") - 1
    result["unanchorable"] = anchored.unanchorable
    result["lossy"] = collections.Counter(x["what"] for x in anchored.lossy)
    ties = sum(1 for r in sidedoc.assign_ties(sidedoc.fold_parts(anchored.records)) if r.tie)
    result["tied_records"] = ties

    rebuilt, notes = inline.reconstruct(clean, doc, entries=clean_entries)
    result["notes"] = notes
    result["exact"] = rebuilt == original

    restripped, resid = strip.strip_source(rebuilt, directives)
    result["code_identical"] = restripped == clean
    # A blank line between two blocks on one anchor is the one thing the reader adds that
    # the stripper cannot take back out (§3 ties): the separating blank line stayed in the
    # clean source, so re-stripping the inline view finds two of them. Counted apart from
    # a reader that actually damaged code.
    result["code_identical_nonblank"] = (
        [l for l in restripped.splitlines() if l.strip()] == [l for l in clean.splitlines() if l.strip()])

    lines = anchoring.strip.split_lines(anchoring._decode(original))
    want = documentation(sidecar, lines)
    got = documentation(resid, anchoring.strip.split_lines(anchoring._decode(rebuilt)))
    # Three outcomes, not two. A record can come back; it can be *declared*
    # unanchorable, which FORMAT.md §6 requires be surfaced and which the
    # artifact duly reports; or it can vanish with nobody saying so. Only the
    # last is a bug, and conflating it with the second reported 15 failing
    # files here when nothing had actually been lost.
    missing = list((collections.Counter(want) - collections.Counter(got)).elements())
    extra = list((collections.Counter(got) - collections.Counter(want)).elements())
    # A block can also come back split differently — one paragraph rendered as
    # two, or two merged — which moves text between records without losing a
    # word of it. So "dropped" is a question about *content*, not about block
    # identity: it is dropped only if its prose is nowhere in the rebuilt file.
    declared = {doc_text(u["kind"], u.get("text", "")) for u in anchored.unanchorable}
    haystack = _squash(" \u0000 ".join(got))
    dropped = [m for m in missing
               if m not in declared and _squash(m) and _squash(m) not in haystack]

    result["records_preserved"] = not missing and not extra
    result["records_accounted"] = not dropped
    result["n_declared_unanchorable"] = len(anchored.unanchorable)
    if missing or extra:
        result["records_lost"] = missing[:5]
        result["records_added"] = extra[:5]
        result["n_lost"], result["n_added"] = len(missing), len(extra)
    if dropped:
        result["records_dropped"] = dropped[:5]
        result["n_dropped"] = len(dropped)
    result["reasons"] = [] if result["exact"] else classify(original, rebuilt)
    if not result["exact"] and keep_diff:
        result["diff"] = "".join(difflib.unified_diff(
            original.decode("utf-8", "replace").splitlines(True),
            rebuilt.decode("utf-8", "replace").splitlines(True),
            "original", "reconstructed", n=1))[:4000]
    return result


def run(sample: list[dict], keep_diff: bool = False) -> list[dict]:
    directives = directives_mod.load()
    results: list[dict] = []
    for start in range(0, len(sample), BATCH):
        chunk = [e for e in sample[start:start + BATCH] if (CACHE / f"{e['blob_sha']}.py").exists()]
        raw = blobs([e["blob_sha"] for e in chunk])
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            paths: dict[str, tuple[Path, Path]] = {}
            for e in chunk:
                sha = e["blob_sha"]
                original = raw.get(sha)
                if original is None:
                    continue
                try:
                    otext = anchoring._decode(original)
                    ctext = anchoring._decode((CACHE / f"{sha}.py").read_bytes())
                except Exception:
                    continue
                op = tmpdir / f"o{sha}.py"
                cp = tmpdir / f"c{sha}.py"
                op.write_text(otext.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8")
                cp.write_text(ctext.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8")
                paths[sha] = (op, cp)
            indexed = resolver.index_files([p for pair in paths.values() for p in pair])
            for e in chunk:
                sha = e["blob_sha"]
                if sha not in paths:
                    results.append({"blob_sha": sha, "error": "unreadable"})
                    continue
                op, cp = paths[sha]
                if str(op) not in indexed or str(cp) not in indexed:
                    results.append({"blob_sha": sha, "repo": e.get("repo"), "path": e.get("path"),
                                    "error": "does not parse"})
                    continue
                try:
                    results.append(run_one(e, raw[sha], indexed[str(op)], indexed[str(cp)],
                                           directives, keep_diff))
                except Exception as exc:      # a crash is a result, not the end of the run
                    results.append({"blob_sha": sha, "repo": e.get("repo"), "path": e.get("path"),
                                    "error": f"{type(exc).__name__}: {exc}"})
        print(f"  {min(start + BATCH, len(sample))}/{len(sample)}", file=sys.stderr, flush=True)
    return results


# ---- reporting ---------------------------------------------------------------------------

#: Failure causes, worst first. A file's primary cause is the worst thing in its diff.
SEVERITY = ("records dropped", "content differs", "record moved", "pass ambiguity",
            "blank-line placement", "comment indent", "comment marker spacing",
            "trailing comment gap", "docstring quote style", "whitespace")


def primary_cause(result: dict) -> str:
    """One cause per file: the worst thing that happened to it."""
    reasons = set(result.get("reasons", []))
    if result.get("unanchorable"):
        reasons.add("records dropped")
    for reason in SEVERITY:
        if reason in reasons:
            return reason
    return "byte-exact" if result.get("exact") else "unclassified"


def summarise(results: list[dict]) -> dict:
    ok = [r for r in results if "error" not in r]
    exact = [r for r in ok if r["exact"]]
    reasons = collections.Counter()
    for r in ok:
        for reason in r["reasons"]:
            reasons[reason] += 1
    lossy = collections.Counter()
    for r in ok:
        lossy.update(r.get("lossy") or {})
    return {
        "files": len(results),
        "errors": collections.Counter(r["error"].split(":")[0] for r in results if "error" in r),
        "exact": len(exact),
        "code_identical": sum(1 for r in ok if r["code_identical"]),
        "code_identical_nonblank": sum(1 for r in ok if r["code_identical_nonblank"]),
        "records_preserved": sum(1 for r in ok if r["records_preserved"]),
        "records_accounted": sum(1 for r in ok if r.get("records_accounted", True)),
        "records_dropped": sum(r.get("n_dropped", 0) for r in ok),
        "records": sum(r["records"] for r in ok),
        "tied_records": sum(r["tied_records"] for r in ok),
        "unanchorable": sum(len(r["unanchorable"]) for r in ok),
        "orphaned": sum(len(r["notes"]) for r in ok),
        "failure_reasons": dict(reasons.most_common()),
        "normalised_away": dict(lossy.most_common()),
        "primary_cause": dict(collections.Counter(primary_cause(r) for r in ok).most_common()),
        "only_normalisation": sum(
            1 for r in ok if not r["exact"]
            and set(r["reasons"]) <= {"comment marker spacing", "trailing comment gap",
                                      "docstring quote style", "comment indent", "whitespace"}),
    }


def markdown(summary: dict, results: list[dict]) -> str:
    ok = [r for r in results if "error" not in r]
    n = max(1, len(ok))
    buf = ["# Round trip: original -> strip -> artifacts -> reconstruct", "",
           f"{summary['files']} blobs, {summary['records']} documentation records, "
           f"{summary['tied_records']} of them tied on an (anchor, kind) slot.", "",
           "| check | files | share |", "|---|---:|---:|"]
    for label, key in (("byte-exact", "exact"), ("code identical after re-strip", "code_identical"),
                       ("code identical ignoring blank lines", "code_identical_nonblank"),
                       ("every record preserved", "records_preserved"),
                       ("no record dropped unreported", "records_accounted")):
        buf.append(f"| {label} | {summary[key]} | {100 * summary[key] / n:.0f}% |")
    buf.append(f"| exact once the format's own normalisations are allowed | "
               f"{summary['exact'] + summary['only_normalisation']} | "
               f"{100 * (summary['exact'] + summary['only_normalisation']) / n:.0f}% |")
    buf += ["", "## Why the rest differ", "",
            "Each file counted once, under the worst thing in its diff.", "",
            "| primary cause | files |", "|---|---:|"]
    for reason, count in summary["primary_cause"].items():
        if reason != "byte-exact":
            buf.append(f"| {reason} | {count} |")
    buf += ["", "Every reason seen anywhere in a diff (a file can appear in several rows):",
            "", "| reason | files |", "|---|---:|"]
    for reason, count in summary["failure_reasons"].items():
        buf.append(f"| {reason} | {count} |")
    buf += ["", "## What the format normalises away", "", "| record property | records |", "|---|---:|"]
    for what, count in summary["normalised_away"].items():
        buf.append(f"| {what} | {count} |")
    hard = [r for r in ok if not r.get("records_accounted", True) or not r["code_identical"]]
    if hard:
        buf += ["", "## Files that lost something", "", "| file | lost | added | code |", "|---|---:|---:|---|"]
        for r in hard[:40]:
            buf.append(f"| {r['path']} | {r.get('n_lost', 0)} | {r.get('n_added', 0)} | "
                       f"{'ok' if r['code_identical'] else 'CHANGED'} |")
    if summary["errors"]:
        buf += ["", "## Errors", ""] + [f"- {k}: {v}" for k, v in summary["errors"].items()]
    return "\n".join(buf) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sample", action="store_true", help="the 100 blobs of corpus/convert-pilot/sample.json")
    ap.add_argument("--all", action="store_true", help="every blob in cache/")
    ap.add_argument("--shas", nargs="*", help="specific blob shas")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--diff", action="store_true", help="print a unified diff per failing blob")
    ap.add_argument("--out", default=str(REPORT))
    args = ap.parse_args(argv)

    if args.shas:
        entries = [{"blob_sha": sha, "path": sha} for sha in args.shas]
    elif args.all:
        shas = sorted(p.stem for p in CACHE.glob("*.py"))
        entries = [{"blob_sha": sha, "path": sha} for sha in shas]
    else:
        entries = json.loads(SAMPLE.read_text())
    if args.limit:
        entries = entries[:args.limit]

    results = run(entries, keep_diff=args.diff)
    summary = summarise(results)
    print(json.dumps(summary, indent=1, default=str))

    if args.diff:
        for r in results:
            if r.get("exact", True):
                continue
            print(f"\n=== {r.get('path')} {r['blob_sha']} {r.get('reasons')}")
            print(r.get("diff", r.get("error", "")))

    Path(args.out).write_text(json.dumps({"summary": summary, "results": results},
                                         indent=1, default=str))
    REPORT_MD.write_text(markdown(summary, results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
