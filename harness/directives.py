"""Directive allowlist: ``load(path)`` + ``Directives.classify(comment_text, lineno)``.

Schema and matching semantics are documented in the header of corpus/directives.toml:

  kind = "prefix"   -> body starts with pattern, body = comment text with the leading '#'
                       removed and leading whitespace stripped.
  kind = "contains" -> pattern occurs anywhere in the full comment text (incl. '#').
  kind = "regex"    -> re.search(pattern, full_comment_text).
  ignore_case       -> default false.
  line              -> "any" (default) | "N" | "N-M": physical line the comment must be on.

Classification order: [[keep]] entries first (any match -> keep), then [[human]] entries,
then [[watch]] entries (-> unresolved), else remove.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

KEEP = "keep"
HUMAN = "human"
UNRESOLVED = "unresolved"
REMOVE = "remove"

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "corpus" / "directives.toml"


def _parse_line_spec(spec) -> tuple[int, int] | None:
    """'any' -> None; 'N' -> (N, N); 'N-M' -> (N, M)."""
    if spec is None:
        return None
    if isinstance(spec, int):
        return (spec, spec)
    s = str(spec).strip()
    if s == "" or s == "any":
        return None
    if "-" in s:
        lo, hi = s.split("-", 1)
        return (int(lo), int(hi))
    n = int(s)
    return (n, n)


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    pattern: str
    kind: str
    ignore_case: bool = False
    line: tuple[int, int] | None = None
    section: str = "keep"
    _regex: re.Pattern | None = None
    _needle: str = ""

    @classmethod
    def from_entry(cls, entry: dict, section: str, index: int) -> "Rule":
        kind = str(entry.get("kind", "prefix"))
        if kind not in ("prefix", "contains", "regex"):
            raise ValueError(f"[[{section}]] #{index}: unknown kind {kind!r}")
        pattern = entry.get("pattern")
        if not isinstance(pattern, str):
            raise ValueError(f"[[{section}]] #{index}: missing string 'pattern'")
        ignore_case = bool(entry.get("ignore_case", False))
        name = str(entry.get("name") or f"{section}-{index}")
        regex = None
        needle = pattern
        if kind == "regex":
            regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        elif ignore_case:
            needle = pattern.lower()
        return cls(
            name=name,
            pattern=pattern,
            kind=kind,
            ignore_case=ignore_case,
            line=_parse_line_spec(entry.get("line")),
            section=section,
            _regex=regex,
            _needle=needle,
        )

    def matches(self, comment_text: str, lineno: int) -> bool:
        if self.line is not None and not (self.line[0] <= lineno <= self.line[1]):
            return False
        if self.kind == "regex":
            return self._regex.search(comment_text) is not None
        if self.kind == "contains":
            hay = comment_text.lower() if self.ignore_case else comment_text
            return self._needle in hay
        # prefix
        body = comment_text[1:] if comment_text.startswith("#") else comment_text
        body = body.lstrip()
        if self.ignore_case:
            body = body.lower()
        return body.startswith(self._needle)


class Directives:
    """Ordered rule lists loaded from directives.toml."""

    __slots__ = ("keep", "human", "watch", "version", "source")

    def __init__(self, keep, human=(), watch=(), version=None, source=None):
        self.keep = tuple(keep)
        self.human = tuple(human)
        self.watch = tuple(watch)
        self.version = version
        self.source = source

    @classmethod
    def from_dict(cls, data: dict, source=None) -> "Directives":
        def rules(section):
            entries = data.get(section) or []
            return [Rule.from_entry(e, section, i) for i, e in enumerate(entries)]

        return cls(
            keep=rules("keep"),
            human=rules("human"),
            watch=rules("watch"),
            version=data.get("version"),
            source=source,
        )

    def classify(self, comment_text: str, lineno: int) -> tuple[str, str | None]:
        """Return ("keep", rule) | ("human", rule) | ("unresolved", watch) | ("remove", None)."""
        for rule in self.keep:
            if rule.matches(comment_text, lineno):
                return (KEEP, rule.name)
        for rule in self.human:
            if rule.matches(comment_text, lineno):
                return (HUMAN, rule.name)
        for rule in self.watch:
            if rule.matches(comment_text, lineno):
                return (UNRESOLVED, rule.name)
        return (REMOVE, None)

    def __repr__(self):
        return (f"Directives(keep={len(self.keep)}, human={len(self.human)}, "
                f"watch={len(self.watch)}, source={self.source!r})")


def load(path=DEFAULT_PATH) -> Directives:
    """Read a directives TOML file (tomllib) and return a Directives object."""
    p = Path(path)
    with open(p, "rb") as fh:
        data = tomllib.load(fh)
    return Directives.from_dict(data, source=str(p))


def loads(text: str) -> Directives:
    """Parse directives from a TOML string (tests)."""
    return Directives.from_dict(tomllib.loads(text), source="<string>")
