"""The two artifacts `FORMAT.md` defines and nothing used to write: the index (§4)
and the sidedoc (§5).

    from harness.sidedoc import Record, write_sidedoc, write_index, parse_sidedoc

    records = [Record("<module>", "doc", "Shopping cart and checkout."), ...]
    md  = write_sidedoc(records)                  # .sideword/src/cart.py.md
    idx = write_index("src/cart.py", records, md) # .sideword/src/cart.py.idx

`write_sidedoc` -> `parse_sidedoc` is a bijection on record text: every byte of a
record body survives, and the reader (``harness/inline.py``) puts it back in the source.

Three things here are load-bearing:

* **Ties.** Several blocks on one anchor take an occurrence suffix on the kind —
  ``{lead~1}``, ``{lead~2}`` (§3, §1.5), assigned from source order and never authored.
  Without them a second record silently overwrites the first: 48% of the records in
  the EST-111 pilot shared an (anchor, kind) slot with another record.
* **Escaping.** A body line that starts with ``#`` would read back as a heading, so it
  is prefixed with a backslash. The transform is a bijection on lines, which is what
  keeps the round trip byte-exact.
* **The index never summarises.** It says *that* an anchor is documented and how big
  the doc is. Any summary leaks the doc into every context and defeats the point (§4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FORMAT_VERSION = "sideword/1"

#: Kinds a record can carry (§3). `todo` is `lead` or `trail` plus a filter flag.
KINDS = ("doc", "lead", "trail", "post", "todo")

#: Segment kinds that are parts of a symbol rather than places in its body (§1.2).
#: A `doc` record on one of these folds into the parent's docstring and loses its kind.
PART_KINDS = ("param", "returns", "raises")

#: Every segment kind the grammar knows (§1.2–§1.4). Used only to split an anchor's
#: segments the way §1.6 says a reader must: a `/` separates when a known kind follows.
SEGMENT_KINDS = (
    "async with", "async for", "decorator", "continue", "nonlocal", "finally", "returns",
    "import", "global", "assert", "except", "raises", "assign", "return", "while", "yield",
    "break", "match", "param", "raise", "with", "case", "elif", "else", "expr", "call",
    "item", "pass", "for", "key", "arg", "del", "if", "try",
)

_HEADING = re.compile(r"^## (?P<anchor>.+?) \{(?P<kind>[a-z]+)(?:~(?P<tie>\d+))?\}$")
_PART_HEADING = re.compile(r"^### (?P<part>#.+)$")
_ESCAPE = re.compile(r"^(\\*)#")
_UNESCAPE = re.compile(r"^\\(\\*#)")
_SEGMENT_SPLIT = re.compile(
    r"/(?=(?:" + "|".join(re.escape(k) for k in SEGMENT_KINDS) + r")(?::|/|~|$))"
)


@dataclass
class Record:
    """One documentation block: what it is about, how it renders, what it says."""

    anchor: str
    kind: str | None            # None for a part folded under its parent (§3)
    body: str
    tie: int | None = None      # occurrence suffix on the kind, derived by `assign_ties`
    parts: list["Record"] = field(default_factory=list)

    @property
    def slot(self) -> str:
        """The heading's kind field, tie included."""
        return self.kind if self.tie is None else f"{self.kind}~{self.tie}"

    @property
    def lines(self) -> int:
        return len(self.body.split("\n")) if self.body else 0


# ---- anchor text ------------------------------------------------------------------------
# Shallow text operations only. Enumeration, resolution and tie assignment over *source*
# stay in crates/resolver; nothing here decides what an anchor names.

def split_anchor(anchor: str) -> tuple[str, list[str]]:
    """``("Cart.add", ["assign:x", "if:y"])`` — path, then segments (§1)."""
    path, sep, rest = anchor.partition("#")
    if not sep:
        return path, []
    return path, _SEGMENT_SPLIT.split(rest)


def segment_kind(segment: str) -> str:
    """The kind of one segment: ``assign:self.total`` -> ``assign``."""
    head = segment.split(":", 1)[0]
    return head.split("~", 1)[0].strip()


def anchor_depth(anchor: str) -> int:
    return len(split_anchor(anchor)[1])


def part_of(anchor: str) -> tuple[str, str] | None:
    """Split ``Cart.add#param:qty`` into its parent and the part segment, or None.

    A part is a *single* segment naming a piece of the symbol's signature (§1.2); a
    `param` nested under a statement is not a thing the grammar can produce.
    """
    path, segments = split_anchor(anchor)
    if len(segments) != 1 or segment_kind(segments[0]) not in PART_KINDS:
        return None
    return path, "#" + segments[0]


# ---- body escaping ----------------------------------------------------------------------

def escape_body(text: str) -> str:
    """Make a body safe to sit under a markdown heading, reversibly."""
    return "\n".join(_ESCAPE.sub(r"\\\1#", line) for line in text.split("\n"))


def unescape_body(text: str) -> str:
    return "\n".join(_UNESCAPE.sub(r"\1", line) for line in text.split("\n"))


# ---- ties -------------------------------------------------------------------------------

def assign_ties(records: list[Record]) -> list[Record]:
    """Number records that share an (anchor, kind) slot, in source order (§3).

    Mutates and returns the list. A slot with one record keeps ``tie=None``: an untied
    anchor is what an author writes, and numbering it would be noise.
    """
    counts: dict[tuple[str, str | None], int] = {}
    for rec in records:
        counts[(rec.anchor, rec.kind)] = counts.get((rec.anchor, rec.kind), 0) + 1
    seen: dict[tuple[str, str | None], int] = {}
    for rec in records:
        key = (rec.anchor, rec.kind)
        if counts[key] < 2:
            rec.tie = None
            continue
        seen[key] = seen.get(key, 0) + 1
        rec.tie = seen[key]
    return records


def fold_parts(records: list[Record]) -> list[Record]:
    """Move ``doc`` records on `#param:` / `#returns` / `#raises` under their parent (§5).

    A part whose parent has no record of its own keeps a heading of its own, so nothing
    is dropped just because the symbol went undocumented.
    """
    copies = [Record(r.anchor, r.kind, r.body, r.tie, list(r.parts)) for r in records]
    out: list[Record] = []
    by_anchor: dict[str, Record] = {}
    for rec in copies:
        if rec.kind == "doc" and rec.anchor not in by_anchor:
            by_anchor[rec.anchor] = rec
    for rec in copies:
        split = part_of(rec.anchor) if rec.kind == "doc" else None
        parent = by_anchor.get(split[0]) if split else None
        if parent is not None and parent is not rec:
            parent.parts.append(Record(split[1], None, rec.body))
            continue
        out.append(rec)
    return out


# ---- sidedoc (§5) -----------------------------------------------------------------------

def detect_style(records: list[Record]) -> str:
    """The docstring convention the file is written in, for the reader to fold parts into."""
    text = "\n".join(r.body for r in records if r.kind == "doc")
    if re.search(r"^\s*:(param|returns?|rtype|raises)\b", text, re.M):
        return "sphinx"
    if re.search(r"^\s*(Parameters|Returns|Raises)\s*\n\s*-{3,}", text, re.M):
        return "numpy"
    if re.search(r"^\s*(Args|Returns|Raises):\s*$", text, re.M):
        return "google"
    return "plain"


def write_sidedoc(records: list[Record], style: str | None = None) -> str:
    """Render the sidedoc: markdown, `##` heading text is the anchor verbatim (§5)."""
    records = fold_parts(list(records))
    assign_ties(records)
    style = style or detect_style(records)
    buf = ["---", f"style: {style}", "---", ""]
    for rec in records:
        buf.append(f"## {rec.anchor} {{{rec.slot}}}")
        buf.append(escape_body(rec.body))
        buf.append("")
        for part in rec.parts:
            buf.append(f"### {part.anchor}")
            buf.append(escape_body(part.body))
            buf.append("")
    return "\n".join(buf)


def parse_sidedoc(text: str) -> tuple[dict[str, str], list[Record]]:
    """Inverse of :func:`write_sidedoc`: ``(front_matter, records)``."""
    lines = text.split("\n")
    front: dict[str, str] = {}
    i = 0
    if lines and lines[0] == "---":
        i = 1
        while i < len(lines) and lines[i] != "---":
            key, sep, value = lines[i].partition(":")
            if sep:
                front[key.strip()] = value.strip()
            i += 1
        i += 1
        while i < len(lines) and lines[i] == "":
            i += 1

    records: list[Record] = []
    current: Record | None = None
    part: Record | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal body
        target = part or current
        if target is not None:
            if body and body[-1] == "":
                body.pop()             # the blank line `write_sidedoc` puts before the next heading
            target.body = unescape_body("\n".join(body))
        body = []

    for line in lines[i:]:
        head = _HEADING.match(line)
        if head:
            flush()
            part = None
            tie = head.group("tie")
            current = Record(head.group("anchor"), head.group("kind"), "",
                             tie=int(tie) if tie else None)
            records.append(current)
            continue
        sub = _PART_HEADING.match(line)
        if sub and current is not None:
            flush()
            part = Record(sub.group("part"), None, "")
            current.parts.append(part)
            continue
        if current is None:
            continue                    # prose before the first heading is not a record
        body.append(line)
    flush()
    return front, records


# ---- index (§4) -------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Budget for retrieving the sidedoc: ~4 characters a token, rounded to be honest
    about being an estimate."""
    tokens = round(len(text) / 4)
    step = 10 if tokens >= 100 else 5
    return max(step, int(round(tokens / step)) * step)


#: Width the anchor column pads to. Longer anchors overflow rather than widen
#: every other row (§4 — the index has to stay cheap).
ANCHOR_COLUMN = 56


def write_index(path: str, records: list[Record], sidedoc: str) -> str:
    """Render the index: one line per record, parts rolled onto the parent's row (§4)."""
    records = fold_parts(list(records))
    assign_ties(records)
    rows = []
    for rec in records:
        rollup = " ".join("+" + p.anchor.lstrip("#") for p in rec.parts)
        rows.append((rec.anchor, rec.slot, f"{rec.lines}L", rollup))
    # Pad to the common case, not to the worst one. A discriminator is source
    # text and can run to hundreds of characters (§1.6); padding every row to
    # the longest of them turned the index into 60% of the sidedoc's size, when
    # §4's whole premise is that it is cheap enough to always read. Anything
    # wider than the column simply overflows with a single space after it.
    anchor_w = min(max([len(r[0]) for r in rows], default=0), ANCHOR_COLUMN) + 2
    kind_w = max([len(r[1]) for r in rows], default=0) + 2
    header = (f"{FORMAT_VERSION}  {path}  {len(records)} record"
              f"{'' if len(records) == 1 else 's'}  ~{estimate_tokens(sidedoc)} tok")
    out = [header]
    for anchor, slot, count, rollup in rows:
        pad = anchor_w if len(anchor) < anchor_w else len(anchor) + 1
        line = f"{anchor:<{pad}}{slot:<{kind_w}}{count}"
        if rollup:
            line += "  " + rollup
        out.append(line)
    return "\n".join(out) + "\n"
