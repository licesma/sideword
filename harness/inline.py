"""Reconstruct the inline view: clean source + sidedoc -> the file a human reads.

    from harness.inline import reconstruct
    inline_bytes, notes = reconstruct(clean_bytes, sidedoc_text)

This is the editor half of `FORMAT.md`. Every record in the sidedoc names an anchor;
the anchor names a node (``crates/resolver``); the node says where the prose goes and at
what indent. `notes` lists everything the reader could not place, because an anchor that
does not resolve is orphaned and never silently dropped (§6).

:class:`Geometry` is where a node becomes a position, and it is deliberately the *only*
place: ``harness/anchoring.py`` uses it to choose anchors and the reader uses it to put
prose back, so the two cannot drift apart. Rendering follows the format where the format
is normative — two spaces before a `trail`, `# ` before a comment line, a triple-quoted
docstring first in the body (§3) — so legacy source written another way comes back
normalised rather than corrupted. ``harness/roundtrip.py`` measures exactly how much of
the corpus that costs.
"""

from __future__ import annotations

import argparse
import ast
import io
import sys
import tokenize
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from harness import resolver, sidedoc
    from harness.strip import split_lines
else:
    from . import resolver, sidedoc
    from .strip import split_lines

#: Clause keywords with no node of their own (§1.3, Open 2). The anchor resolves to the
#: clause body, so the keyword's own line has to be found in the text.
CLAUSE_KEYWORDS = {"else": "else", "finally": "finally", "elif": "elif",
                   "except": "except", "case": "case"}

DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _terminator(line: str) -> str:
    for end in ("\r\n", "\n", "\r"):
        if line.endswith(end):
            return end
    return ""


def _content(line: str) -> str:
    return line[:len(line) - len(_terminator(line))]


def _indent_of(line: str) -> str:
    content = _content(line)
    return content[:len(content) - len(content.lstrip(" \t"))]


def stmt_start(node: ast.AST) -> int:
    """First line of a statement, decorators included — where a body actually begins."""
    decorators = getattr(node, "decorator_list", None) or []
    return min([node.lineno] + [d.lineno for d in decorators])


class Geometry:
    """Where each anchor's prose goes in one particular text.

    An `Entry` (``harness/resolver.py``) says which lines a node covers. Rendering needs
    three finer positions the enumeration does not carry: the line a `lead` sits above,
    the line a `trail` sits on, and the line a docstring is inserted at. All three differ
    from ``entry["line"]`` for exactly the constructs `FORMAT.md` flags — clause keywords
    with no node (§1.3) and headers that span lines.
    """

    def __init__(self, text: str):
        self.text = text
        self.lines = split_lines(text)
        self.ntext = text.replace("\r\n", "\n").replace("\r", "\n")
        self.tree = ast.parse(self.ntext)
        self.blocks: dict[int, ast.AST] = {}
        self.defs: dict[int, ast.AST] = {}
        for node in ast.walk(self.tree):
            body = getattr(node, "body", None)
            if (isinstance(body, list) and body and isinstance(body[0], ast.stmt)
                    and hasattr(node, "lineno")):
                self.blocks.setdefault(node.lineno, node)
            if isinstance(node, DEFINITIONS):
                self.defs.setdefault(node.lineno, node)
        self.dominant = self._dominant_terminator()

    def _dominant_terminator(self) -> str:
        counts: dict[str, int] = {}
        for line in self.lines:
            end = _terminator(line)
            if end:
                counts[end] = counts.get(end, 0) + 1
        return max(counts, key=counts.get) if counts else "\n"

    def line(self, n: int) -> str:
        return self.lines[n - 1] if 0 < n <= len(self.lines) else ""

    def term(self, n: int) -> str:
        return _terminator(self.line(n)) or self.dominant

    def indent(self, n: int) -> str:
        return _indent_of(self.line(n))

    def is_blank(self, n: int) -> bool:
        return self.line(n).strip() == ""

    def module_head(self) -> int:
        """Where `<module>` prose goes: the top of the file, under any kept directive.

        A shebang or a coding cookie is code wearing comment syntax (§2) and must stay on
        the first line, so module prose goes after the leading comment run.
        """
        n = 1
        while n <= len(self.lines) and _content(self.line(n)).lstrip().startswith("#"):
            n += 1
        return n

    def clause_line(self, anchor: str, entry: dict) -> int:
        """The keyword line of a clause that has no node of its own, else the entry's line."""
        _, segments = sidedoc.split_anchor(anchor)
        if not segments:
            return entry["line"]
        keyword = CLAUSE_KEYWORDS.get(sidedoc.segment_kind(segments[-1]))
        if keyword is None:
            return entry["line"]
        for n in range(entry["line"], max(0, entry["line"] - 60), -1):
            if _content(self.line(n)).lstrip().startswith(keyword):
                return n
        return entry["line"]

    def header_end(self, line: int) -> int:
        """Last line of the header of the block opening at `line` (`def f(\\n  a\\n):`)."""
        node = self.blocks.get(line)
        if node is None:
            return line
        first = stmt_start(node.body[0])
        if first <= line:
            return line                      # `def f(): pass` — header and body share a line
        n = first - 1
        while n > line and (self.is_blank(n) or _content(self.line(n)).lstrip().startswith("#")):
            n -= 1
        return n

    def lead_line(self, anchor: str, entry: dict) -> int:
        """The line a `lead` block sits above."""
        return self.clause_line(anchor, entry)

    def trail_line(self, anchor: str, entry: dict) -> int:
        """The line a `trail` comment sits on: the *header's* last line for a block."""
        _, segments = sidedoc.split_anchor(anchor)
        if segments and sidedoc.segment_kind(segments[-1]) in CLAUSE_KEYWORDS:
            return self.clause_line(anchor, entry)
        if entry["line"] in self.blocks:
            return self.header_end(entry["line"])
        return entry["end_line"]

    def post_line(self, anchor: str, entry: dict) -> int:
        """The line a `post` block sits below."""
        return entry["end_line"]

    def docstring_slot(self, entry: dict) -> tuple[int, int] | None:
        """``(insertion line, first body statement line)`` for a symbol's docstring."""
        node = self.defs.get(entry["line"])
        if node is None or not getattr(node, "body", None):
            return None
        return self.header_end(entry["line"]) + 1, stmt_start(node.body[0])


class _Reader:
    def __init__(self, clean: bytes, sidedoc_text: str, entries: list[dict] | None):
        encoding, _ = tokenize.detect_encoding(io.BytesIO(clean).readline)
        self.encoding = encoding
        self.text = clean.decode(encoding)
        self.geo = Geometry(self.text)
        self.lines = self.geo.lines
        self.front, self.records = sidedoc.parse_sidedoc(sidedoc_text)
        self.entries = entries if entries is not None else resolver.index_text(self.geo.ntext)
        self.by_anchor = resolver.by_anchor(self.entries)
        self.by_untied: dict[str, list[dict]] = {}
        for entry in self.entries:
            self.by_untied.setdefault(untie(entry["anchor"]), []).append(entry)
        self.notes: list[str] = []
        self.before: dict[int, list[str]] = {}
        self.after: dict[int, list[str]] = {}
        self.trail: dict[int, list[str]] = {}
        self.replace: dict[int, list[str]] = {}
        self.eof: list[str] = []

    def resolve(self, anchor: str) -> dict | None:
        entry = self.by_anchor.get(anchor)
        if entry is not None:
            return entry
        candidates = self.by_untied.get(untie(anchor), [])
        return candidates[0] if len(candidates) == 1 else None

    # ---- rendering -----------------------------------------------------------------
    def comment_block(self, body: str, indent: str, term: str) -> str:
        return "".join(f"{indent}#{' ' + line if line else ''}{term}" for line in body.split("\n"))

    def docstring(self, body: str, indent: str, term: str) -> str:
        """A `doc` body is the literal's contents, so the quotes are all that gets added
        back; continuation lines carry their own indentation already."""
        return f'{indent}"""{body}"""{term}'

    def add(self, table: dict[int, list[str]], n: int, chunk: str, block: bool = False) -> None:
        """Queue a chunk at a slot.

        Two comment blocks landing on one slot need a blank line back between them: the
        blank line is what made them two records rather than one (§3), and without it the
        pair re-reads as a single block.
        """
        slot = table.setdefault(n, [])
        if block and slot and slot[-1].lstrip().startswith("#"):
            slot.append(self.geo.term(n))
        slot.append(chunk)

    # ---- placement -----------------------------------------------------------------
    def place(self, rec: sidedoc.Record) -> None:
        if rec.kind == "doc":
            self.place_doc(rec)
        elif rec.kind in ("lead", "todo"):
            self.place_lead(rec)
        elif rec.kind == "post":
            self.place_post(rec)
        elif rec.kind == "trail":
            self.place_trail(rec)
        else:
            self.notes.append(f"unknown kind {{{rec.kind}}} on {rec.anchor}")

    def orphan(self, rec: sidedoc.Record) -> None:
        self.notes.append(f"orphaned: {rec.anchor} {{{rec.slot}}}")

    def place_lead(self, rec: sidedoc.Record) -> None:
        if rec.anchor == "<module>":
            n = self.geo.module_head()
            self.add(self.before, n, self.comment_block(rec.body, "", self.geo.term(n)), block=True)
            return
        entry = self.resolve(rec.anchor)
        if entry is None:
            return self.orphan(rec)
        n = self.geo.lead_line(rec.anchor, entry)
        self.add(self.before, n, self.comment_block(rec.body, self.geo.indent(n), self.geo.term(n)),
                 block=True)

    def place_post(self, rec: sidedoc.Record) -> None:
        if rec.anchor == "<module>":
            self.eof.append(self.comment_block(rec.body, "", self.geo.dominant))
            return
        entry = self.resolve(rec.anchor)
        if entry is None:
            return self.orphan(rec)
        n = min(self.geo.post_line(rec.anchor, entry), len(self.lines))
        indent = self.geo.indent(entry["line"])
        self.add(self.after, n, self.comment_block(rec.body, indent, self.geo.term(n)), block=True)

    def place_trail(self, rec: sidedoc.Record) -> None:
        entry = self.resolve(rec.anchor)
        if entry is None:
            return self.orphan(rec)
        body = rec.body
        if "\n" in body:
            self.notes.append(f"multi-line {{trail}} flattened on {rec.anchor}")
            body = " ".join(line.strip() for line in body.split("\n"))
        n = min(self.geo.trail_line(rec.anchor, entry), len(self.lines))
        self.add(self.trail, n, f"  # {body}" if body else "  #")

    def place_doc(self, rec: sidedoc.Record) -> None:
        body = self.fold_parts(rec)
        if rec.anchor == "<module>":
            n = self.geo.module_head()
            self.add(self.before, n, self.docstring(body, "", self.geo.term(n)))
            return
        entry = self.resolve(rec.anchor)
        if entry is None:
            return self.orphan(rec)
        slot = self.geo.docstring_slot(entry)
        if slot is None:
            self.notes.append(f"no body to hold a docstring: {rec.anchor}")
            return
        at, first = slot
        node = self.geo.defs[entry["line"]]
        if first <= entry["line"]:
            return self.place_doc_oneliner(rec, node, first, body)
        indent = self.geo.indent(first)
        block = self.docstring(body, indent, self.geo.term(first))
        # A docstring is the *first* thing in the body, above any blank line that separates
        # it from the code — not merely above the first statement.
        #
        # A lone `pass` is ambiguous: the stripper writes one when removing the docstring
        # empties the body, and plenty of bodies were written `"""doc"""` then `pass`. The
        # clean source cannot tell those apart, so the reader always inserts and never
        # replaces: in the pilot sample that is right 28 times out of 43, and it is the
        # side that cannot delete a statement the author wrote.
        self.add(self.before, at, block)

    def place_doc_oneliner(self, rec, node, first: int, body: str) -> None:
        line = self.geo.line(first)
        if not (len(node.body) == 1 and isinstance(node.body[0], ast.Pass)):
            self.notes.append(f"one-line body, nowhere to put {{doc}}: {rec.anchor}")
            return
        content, term = _content(line), self.geo.term(first)
        head, sep, tail = content.rpartition("pass")
        if not sep:
            self.notes.append(f"one-line body, nowhere to put {{doc}}: {rec.anchor}")
            return
        self.add(self.replace, first, f'{head}"""{body}"""{tail}{term}')

    def fold_parts(self, rec: sidedoc.Record) -> str:
        """Fold `#param:` / `#returns` records back into the parent's docstring (§3)."""
        if not rec.parts:
            return rec.body
        style = self.front.get("style", "sphinx")
        if style not in ("sphinx", "plain"):
            self.notes.append(f"parts folded sphinx-style into a {style} docstring: {rec.anchor}")
        out = [rec.body, ""] if rec.body else []
        for part in rec.parts:
            name = part.anchor.lstrip("#")
            kind, _, arg = name.partition(":")
            label = f":{sidedoc.segment_kind(kind)} {arg}:" if arg else f":{kind}:"
            out.append(f"{label} {part.body}".rstrip())
        return "\n".join(out)

    # ---- assembly ------------------------------------------------------------------
    def run(self) -> tuple[bytes, list[str]]:
        for rec in self.records:
            self.place(rec)
        out: list[str] = []
        for n, line in enumerate(self.lines, 1):
            out.extend(self.before.get(n, []))
            if n in self.replace:
                out.extend(self.replace[n])
            else:
                if n in self.trail:
                    content, term = _content(line), _terminator(line)
                    line = content + "".join(self.trail[n]) + (term or self.geo.dominant)
                out.append(line)
            out.extend(self.after.get(n, []))
        for n in sorted(self.before):
            if n > len(self.lines):
                out.extend(self.before[n])
        out.extend(self.eof)
        text = "".join(out)
        if self.lines and not _terminator(self.lines[-1]) and text.endswith(self.geo.dominant):
            text = text[:-len(self.geo.dominant)]     # the clean file had no final newline
        return text.encode(self.encoding), self.notes


def untie(anchor: str) -> str:
    """The anchor an author writes: every derived occurrence suffix removed (§1.5)."""
    def strip_tie(segment: str) -> str:
        head, sep, tail = segment.rpartition("~")
        return head if sep and tail.isdigit() else segment

    path, segments = sidedoc.split_anchor(anchor)
    if not segments:
        return strip_tie(path)
    return strip_tie(path) + "#" + "/".join(strip_tie(s) for s in segments)


def reconstruct(clean: bytes, sidedoc_text: str, entries: list[dict] | None = None):
    """Put the sidedoc back into the source. Returns ``(inline_bytes, notes)``."""
    if isinstance(clean, str):
        raise TypeError("reconstruct expects bytes")
    return _Reader(clean, sidedoc_text, entries).run()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="render the inline view of a Sideword module")
    ap.add_argument("source", help="clean .py")
    ap.add_argument("sidedoc", nargs="?", help="sidedoc .md (default: .sideword/<source>.md)")
    ap.add_argument("-o", "--output")
    args = ap.parse_args(argv)
    source = Path(args.source)
    doc = Path(args.sidedoc) if args.sidedoc else source.parent / ".sideword" / (source.name + ".md")
    out, notes = reconstruct(source.read_bytes(), doc.read_text(encoding="utf-8"))
    for note in notes:
        print(note, file=sys.stderr)
    if args.output:
        Path(args.output).write_bytes(out)
    else:
        sys.stdout.buffer.write(out)
    return 1 if notes else 0


if __name__ == "__main__":
    sys.exit(main())
