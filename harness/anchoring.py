"""Anchor a stripper sidecar positionally — the mechanical baseline the round trip runs on.

    from harness.anchoring import anchor_records
    result = anchor_records(original_bytes, sidecar_records, entries)

Naming anchors *well* is the one model step of the pipeline (``harness/convert_pilot.py``):
which node a paragraph is really about is a judgement. This is not that. It answers the
much smaller question the round trip needs — *which node was this comment sitting on?* —
by walking the anchor space the resolver enumerates and matching it against where the
record physically was. That makes the writer and the reader testable on 11,609 real blobs
without a single model call.

The placement rules follow `FORMAT.md`:

* a block above a statement is `lead` on it (§3); a block below one with nothing after it
  is `post` (§3); a comment sharing a line with code is `trail`;
* prose above the first statement or below the last with a blank line between it and the
  code anchors on `<module>`, which names the module as a container (§1.3);
* a docstring is `doc` on the symbol that owns it (§1.1);
* whether a block leads or trails is decided by which side it is adjacent to, since that
  is the side the editor can put it back on.
"""

from __future__ import annotations

import argparse
import ast
import bisect
import io
import json
import re
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from harness import inline, resolver, sidedoc, strip
else:
    from . import inline, resolver, sidedoc, strip

#: Sidecar kinds that carry documentation (`harness/CONTRACT.md`).
DOC_KINDS = ("comment", "docstring", "doctest_docstring", "stray_string")

_QUOTE = re.compile(r'^(?P<prefix>[rRuUbBfF]{0,3})(?P<quote>"""|\'\'\'|"|\')')

DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


@dataclass
class Anchored:
    records: list[sidedoc.Record] = field(default_factory=list)
    unanchorable: list[dict] = field(default_factory=list)
    #: per-record diagnostics: quote styles and spacings the format normalises away
    lossy: list[dict] = field(default_factory=list)


def _decode(src: bytes) -> str:
    encoding, _ = tokenize.detect_encoding(io.BytesIO(src).readline)
    return src.decode(encoding)


def _indent(text: str) -> str:
    return text[:len(text) - len(text.lstrip(" \t"))]


def doc_records(sidecar: list[dict], lines: list[str]) -> list[dict]:
    """The sidecar's documentation records, as blocks (§3), in source order."""
    recs = [r for r in sidecar if r.get("kind") in DOC_KINDS]
    recs.sort(key=lambda r: (r["line"], r.get("col", 0)))
    return strip.group_comment_blocks(recs, lines)


class _Anchorer:
    def __init__(self, original: bytes, sidecar: list[dict], entries: list[dict]):
        self.text = _decode(original)
        self.geo = inline.Geometry(self.text)
        self.lines = self.geo.lines
        self.sidecar = sidecar
        self.records = doc_records(sidecar, self.lines)
        self.entries = entries
        self.module = next((e for e in entries if e["target"] == "module"), None)
        self.body = [e for e in entries if e["target"] != "module"]
        # Where the reader would put each kind of record for each anchor. Choosing an
        # anchor against these tables is what keeps the two halves in step: the anchorer
        # never picks an anchor the reader would render somewhere else.
        self.lead_at: dict[int, list[dict]] = {}
        self.trail_at: dict[int, list[dict]] = {}
        self.post_at: dict[int, list[dict]] = {}
        for entry in self.body:
            anchor = entry["anchor"]
            self.lead_at.setdefault(self.geo.lead_line(anchor, entry), []).append(entry)
            self.trail_at.setdefault(self.geo.trail_line(anchor, entry), []).append(entry)
            self.post_at.setdefault(self.geo.post_line(anchor, entry), []).append(entry)
        self.lead_lines = sorted(self.lead_at)
        self.post_lines = sorted(self.post_at)
        self.vanishing = self._vanishing()
        self.out = Anchored()

    # ---- geometry ------------------------------------------------------------------
    def line(self, n: int) -> str:
        return self.geo.line(n)

    def is_blank(self, n: int) -> bool:
        return self.geo.is_blank(n)

    def indent(self, n: int) -> str:
        return self.geo.indent(n)

    def _vanishing(self) -> set[int]:
        """Original lines the stripper deletes outright, so they leave no gap behind."""
        gone: set[int] = set()
        for rec in self.sidecar:
            if rec.get("action") != "removed":
                continue
            start, end = rec["line"], rec.get("end_line", rec["line"])
            if rec["kind"] not in ("comment", "docstring"):
                continue
            if self.line(start)[:rec.get("col", 0)].strip() != "":
                continue               # shares its line with code: the line survives
            gone.update(range(start, end + 1))
        return gone

    def enclosing_expression(self, line: int) -> dict | None:
        """The innermost simple statement whose span strictly contains `line`.

        A comment inside a `def` or an `if` is ordinary; a comment inside a *simple*
        statement is inside an expression, where the grammar names elements only as far
        as §1.4 reaches.
        """
        best = None
        for entry in self.body:
            if entry["line"] >= line or line > entry["end_line"]:
                continue
            if entry["line"] in self.geo.blocks or entry["target"] in ("definition", "part"):
                continue
            span = entry["end_line"] - entry["line"]
            if best is None or span < best[0]:
                best = (span, entry)
        return best[1] if best else None

    def containing_statement(self, line: int) -> dict | None:
        """The innermost statement whose span covers `line`, block headers included.

        Broader than `enclosing_expression`: a trailing comment can sit on a
        continuation line of an `if (...)` header, where nothing is rendered on
        its own line and the enclosing construct is exactly the block it opens.
        """
        best = None
        for entry in self.body:
            if not entry["line"] <= line <= entry["end_line"]:
                continue
            if entry["target"] == "part":
                continue
            span = entry["end_line"] - entry["line"]
            if best is None or span < best[0]:
                best = (span, entry)
        return best[1] if best else None

    def next_lead(self, after: int) -> int | None:
        i = bisect.bisect_right(self.lead_lines, after)
        return self.lead_lines[i] if i < len(self.lead_lines) else None

    def prev_end(self, before: int) -> int | None:
        i = bisect.bisect_left(self.post_lines, before)
        return self.post_lines[i - 1] if i > 0 else None

    def blanks_between(self, lo: int, hi: int) -> int:
        """Lines strictly between `lo` and `hi` that survive stripping as blank lines."""
        return sum(1 for n in range(lo + 1, hi) if self.is_blank(n) and n not in self.vanishing)

    # ---- choosing an entry ----------------------------------------------------------
    @staticmethod
    def _depth(entry: dict) -> int:
        return sidedoc.anchor_depth(entry["anchor"])

    def pick_lead(self, line: int) -> dict | None:
        """A block above `line` documents the outermost thing that starts there."""
        candidates = self.lead_at.get(line, [])
        named = [e for e in candidates if e["target"] != "part"] or candidates
        if not named:
            return None
        return min(named, key=lambda e: (self._depth(e), len(e["anchor"])))

    def pick_post(self, line: int, indent: str) -> dict | None:
        """A block below `line` documents the innermost thing that ends there at its indent."""
        candidates = self.post_at.get(line, [])
        if not candidates:
            return None
        same = [e for e in candidates if self.indent(e["line"]) == indent]
        pool = same or [e for e in candidates if len(self.indent(e["line"])) <= len(indent)] or candidates
        return max(pool, key=lambda e: (self._depth(e), e["line"]))

    def pick_trail(self, line: int) -> dict | None:
        """A comment sharing a line with code documents the innermost thing rendered there."""
        candidates = self.trail_at.get(line, [])
        named = [e for e in candidates if e["target"] != "part"] or candidates
        if not named:
            return None
        return max(named, key=lambda e: (self._depth(e), e["line"]))

    def pick_owner(self, owner: str, line: int) -> dict | None:
        if owner == "<module>" or owner is None:
            return self.module
        best = None
        for entry in self.entries:
            if entry["target"] not in ("definition", "module"):
                continue
            path = sidedoc.split_anchor(entry["anchor"])[0]
            if path.rsplit("~", 1)[0] != owner and path != owner:
                continue
            if not entry["line"] <= line <= entry["end_line"]:
                continue
            span = entry["end_line"] - entry["line"]
            if best is None or span < best[0]:
                best = (span, entry)
        return best[1] if best else None

    # ---- records --------------------------------------------------------------------
    def reject(self, rec: dict, reason: str) -> None:
        # The text goes in the report too: a consumer has to be able to tell a
        # record the grammar cannot name from a record that was silently lost,
        # and it cannot do that from a line number alone.
        self.out.unanchorable.append({"kind": rec["kind"], "line": rec["line"],
                                      "reason": reason, "text": rec.get("text", "")})

    def note_lossy(self, rec: dict, what: str, detail: str = "") -> None:
        self.out.lossy.append({"line": rec["line"], "what": what, "detail": detail})

    def run(self) -> Anchored:
        for rec in self.records:
            if rec.get("action") != "removed":
                continue          # kept in the source: doctests, stray strings, directives
            if rec["kind"] == "docstring":
                self.do_docstring(rec)
            else:
                self.do_comment(rec)
        return self.out

    def do_docstring(self, rec: dict) -> None:
        entry = self.pick_owner(rec.get("owner"), rec["line"])
        if entry is None:
            self.reject(rec, "no symbol owns this docstring")
            return
        text = rec["text"]
        match = _QUOTE.match(text)
        if not match:
            self.reject(rec, "docstring literal not recognised")
            return
        prefix, quote = match.group("prefix"), match.group("quote")
        if prefix or quote != '"""':
            self.note_lossy(rec, "docstring-quotes", prefix + quote)
        body = text[len(prefix) + len(quote):]
        if body.endswith(quote):
            body = body[:-len(quote)]
        self.out.records.append(sidedoc.Record(entry["anchor"], "doc", body))

    def do_comment(self, rec: dict) -> None:
        start, end = rec["line"], rec.get("end_line", rec["line"])
        col = rec.get("col", 0)
        body = self.comment_body(rec)
        if self.line(start)[:col].strip() != "":
            self.do_trailing(rec, start, col, body)
            return

        indent = self.indent(start)
        nxt = self.next_lead(end)
        prv = self.prev_end(start)
        inside = self.enclosing_expression(start)
        if inside is not None and (nxt is None or nxt > inside["end_line"]):
            # Inside a multi-line expression with no element of its own to name (§1.4
            # stops at dict / call / list literals). §1.7 says hoist it to the enclosing
            # statement: the comment renders a line or two above where it was written,
            # which is a rendering cost, not a lost record. Leaving it unanchorable would
            # drop it from the artifact entirely — and in a converted corpus that means
            # the Sideword copy holds less prose than the original it is compared against.
            self.note_lossy(rec, "hoisted-from-expression", inside["anchor"])
            self.emit(rec, inside, "lead", body, self.geo.indent(inside["line"]), indent)
            return
        above = self.blanks_between(prv if prv is not None else 0, start)
        below = self.blanks_between(end, nxt if nxt is not None else len(self.lines) + 1)
        # a block at a deeper indent than what follows is closing the block it sits in
        closes = nxt is not None and len(self.indent(nxt)) < len(indent)

        if nxt is None or closes:
            if prv is None:
                # Nothing precedes it and nothing follows: a file whose only content is
                # this comment. It is about the module, which is exactly what `<module>`
                # names (§1.3).
                self.out.records.append(sidedoc.Record("<module>", "post", body))
                return
            if not closes and below < above and indent == "":
                self.out.records.append(sidedoc.Record("<module>", "post", body))
                return
            entry = self.pick_post(prv, indent)
            if entry is None:
                self.reject(rec, "nothing ends before this block")
                return
            self.emit(rec, entry, "post", body, self.geo.indent(entry["line"]), indent)
            return

        if prv is None and above < below and indent == "":
            self.out.records.append(sidedoc.Record("<module>", "lead", body))
            return
        if prv is not None and above == 0 and below > 0:
            entry = self.pick_post(prv, indent)
            if entry is not None:
                self.emit(rec, entry, "post", body, self.geo.indent(entry["line"]), indent)
                return
        entry = self.pick_lead(nxt)
        if entry is None:
            self.reject(rec, "nothing starts on the line below")
            return
        self.emit(rec, entry, "lead", body, self.indent(nxt), indent)

    def do_trailing(self, rec: dict, start: int, col: int, body: str) -> None:
        entry = self.pick_trail(start)
        if entry is None:
            # A trailing comment on a continuation line of a multi-line statement: the
            # line it sits on renders nothing of its own. Hoist to the statement (§1.7).
            entry = self.containing_statement(start)
            if entry is None:
                self.reject(rec, "nothing is rendered on this line")
                return
            # Hoist as `lead`, not `trail`. §3 renders a `trail` on the statement's
            # *last* line, which is not where this comment was and may already carry a
            # tool directive — that collision loses a record. A `lead` renders above the
            # statement, cannot collide, and ties under §3 when several hoist together.
            self.note_lossy(rec, "hoisted-from-continuation", entry["anchor"])
            self.emit(rec, entry, "lead", body, self.geo.indent(entry["line"]),
                      self.indent(start))
            return
        prefix = self.line(start)[:col]
        gap = len(prefix) - len(prefix.rstrip())
        if gap != 2:
            self.note_lossy(rec, "trail-gap", str(gap))
        self.out.records.append(sidedoc.Record(entry["anchor"], "trail", body))

    def emit(self, rec: dict, entry: dict, kind: str, body: str, rendered_indent: str,
             indent: str) -> None:
        if rendered_indent != indent:
            self.note_lossy(rec, "comment-indent", f"{len(indent)}->{len(rendered_indent)}")
        self.out.records.append(sidedoc.Record(entry["anchor"], kind, body))

    def comment_body(self, rec: dict) -> str:
        out = []
        for line in rec["text"].split("\n"):
            line = line.lstrip()[1:]          # drop the '#'
            if line.startswith(" "):
                line = line[1:]
            elif line:
                self.note_lossy(rec, "no-space-after-hash", line[:20])
            out.append(line)
        return "\n".join(out)


def anchor_records(original: bytes, sidecar: list[dict], entries: list[dict]) -> Anchored:
    """Positionally anchor a stripper sidecar against the file's anchor space."""
    return _Anchorer(original, sidecar, entries).run()


def convert(original: bytes, directives, keep_owners=None) -> dict:
    """Original bytes -> the three artifacts, in memory.

    ``{"source": clean bytes, "index": str, "sidedoc": str, "anchored": Anchored}``

    ``keep_owners`` is the docstring context pass 1 stripped this blob under (see
    ``strip.strip_source``); a docstring kept in the source is not a sidedoc record.
    """
    clean, sidecar = strip.strip_source(original, directives, keep_owners)
    entries = resolver.index_text(_decode(original).replace("\r\n", "\n").replace("\r", "\n"))
    anchored = anchor_records(original, sidecar, entries)
    doc = sidedoc.write_sidedoc(anchored.records)
    return {"source": clean, "sidedoc": doc, "anchored": anchored,
            "records": anchored.records, "sidecar": sidecar}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="convert a legacy .py into the three artifacts")
    ap.add_argument("input")
    ap.add_argument("--out-dir", default=None, help="write <dir>/<name>.py and <dir>/.sideword/<name>.py.{idx,md}")
    ap.add_argument("--directives", default=None)
    args = ap.parse_args(argv)

    if __package__ in (None, ""):
        from harness import directives as directives_mod
    else:
        from . import directives as directives_mod
    d = directives_mod.load(args.directives) if args.directives else directives_mod.load()

    src = Path(args.input)
    result = convert(src.read_bytes(), d)
    rel = src.name
    index_text = sidedoc.write_index(rel, result["records"], result["sidedoc"])
    if not args.out_dir:
        sys.stdout.write(index_text + "\n" + result["sidedoc"])
        return 0
    out = Path(args.out_dir)
    (out / ".sideword").mkdir(parents=True, exist_ok=True)
    (out / rel).write_bytes(result["source"])
    (out / ".sideword" / (rel + ".idx")).write_text(index_text, encoding="utf-8")
    (out / ".sideword" / (rel + ".md")).write_text(result["sidedoc"], encoding="utf-8")
    if result["anchored"].unanchorable:
        print(json.dumps(result["anchored"].unanchorable, indent=1), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
