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

Docstrings have their own tiers (``Directives.classify_docstring``):

  [[docstrings]]      general, repo-agnostic: ``pattern``/``kind``/``ignore_case`` on the
                      docstring's value, ``owner`` (regex, fullmatch on the qualified owner
                      name) and ``module`` (regex, search over the module source). Every
                      field present must match.
  [consumption]       switches for the static consumption analysis (harness/docuse.py).
  [[repo]]            per-repository deviations: ``repo = "owner/name"`` plus nested
                      ``[[repo.docstrings]]`` entries with a ``path`` regex (fullmatch on
                      the repo-relative path) and the same fields as [[docstrings]].
                      Resolved by pass 1 (``Directives.repo_docstring_rules``), which
                      knows the repo and path; the stripper itself never sees a repo name.
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


@dataclass(frozen=True, slots=True)
class DocRule:
    """One ``[[docstrings]]`` or ``[[repo.docstrings]]`` entry.

    A rule matches a docstring when every field it carries matches: ``pattern`` against
    the docstring's value (same kinds as comment rules; ``prefix`` = value starts with
    pattern), ``owner`` against the qualified owner name (``<module>``, ``Cls``,
    ``Cls.meth``, ``f.inner``; ``re.fullmatch``), ``module`` against the whole module
    source (``re.search``) and ``path`` against the repo-relative path (``re.fullmatch``,
    per-repo tier only). A rule with none of them never matches.
    """
    name: str
    section: str
    pattern: str | None = None
    kind: str = "contains"
    ignore_case: bool = False
    owner: str | None = None
    module: str | None = None
    path: str | None = None
    _pattern_re: re.Pattern | None = None
    _owner_re: re.Pattern | None = None
    _module_re: re.Pattern | None = None
    _path_re: re.Pattern | None = None

    @classmethod
    def from_entry(cls, entry: dict, section: str, index: int, need_path: bool = False) -> "DocRule":
        name = str(entry.get("name") or f"{section}-{index}")
        pattern = entry.get("pattern")
        kind = str(entry.get("kind", "contains"))
        if kind not in ("prefix", "contains", "regex"):
            raise ValueError(f"[[{section}]] #{index} ({name}): unknown kind {kind!r}")
        if pattern is not None and not isinstance(pattern, str):
            raise ValueError(f"[[{section}]] #{index} ({name}): 'pattern' must be a string")
        ignore_case = bool(entry.get("ignore_case", False))
        owner = entry.get("owner")
        module = entry.get("module")
        path = entry.get("path")
        for field_name, value in (("owner", owner), ("module", module), ("path", path)):
            if value is not None and not isinstance(value, str):
                raise ValueError(f"[[{section}]] #{index} ({name}): {field_name!r} must be a regex string")
        if need_path and path is None:
            raise ValueError(f"[[{section}]] #{index} ({name}): a per-repo entry needs 'path'")
        if need_path and (pattern is not None or module is not None):
            raise ValueError(f"[[{section}]] #{index} ({name}): a per-repo entry takes only "
                             f"'path' and 'owner' (pass 1 resolves it into keep_owners)")
        if pattern is None and owner is None and module is None and path is None:
            raise ValueError(f"[[{section}]] #{index} ({name}): no matching field at all")
        flags = re.IGNORECASE if ignore_case else 0
        return cls(
            name=name, section=section, pattern=pattern, kind=kind, ignore_case=ignore_case,
            owner=owner, module=module, path=path,
            _pattern_re=re.compile(pattern, flags) if (pattern is not None and kind == "regex") else None,
            _owner_re=re.compile(owner) if owner is not None else None,
            _module_re=re.compile(module) if module is not None else None,
            _path_re=re.compile(path) if path is not None else None,
        )

    def matches_path(self, path: str | None) -> bool:
        if self._path_re is None:
            return True
        return path is not None and self._path_re.fullmatch(path) is not None

    def matches(self, value: str, owner: str, module_text: str | None) -> bool:
        if self.pattern is not None:
            if self.kind == "regex":
                if self._pattern_re.search(value) is None:
                    return False
            else:
                hay = value.lower() if self.ignore_case else value
                needle = self.pattern.lower() if self.ignore_case else self.pattern
                if self.kind == "contains" and needle not in hay:
                    return False
                if self.kind == "prefix" and not hay.lstrip().startswith(needle):
                    return False
        if self._owner_re is not None and self._owner_re.fullmatch(owner) is None:
            return False
        if self._module_re is not None:
            if module_text is None or self._module_re.search(module_text) is None:
                return False
        return True


class Directives:
    """Ordered rule lists loaded from directives.toml."""

    __slots__ = ("keep", "human", "watch", "docstrings", "repos", "consumption",
                 "version", "source")

    def __init__(self, keep, human=(), watch=(), version=None, source=None,
                 docstrings=(), repos=None, consumption=None):
        self.keep = tuple(keep)
        self.human = tuple(human)
        self.watch = tuple(watch)
        self.docstrings = tuple(docstrings)
        self.repos = dict(repos or {})
        self.consumption = dict(consumption or {})
        self.version = version
        self.source = source

    @classmethod
    def from_dict(cls, data: dict, source=None) -> "Directives":
        def rules(section):
            entries = data.get(section) or []
            return [Rule.from_entry(e, section, i) for i, e in enumerate(entries)]

        doc_rules = [DocRule.from_entry(e, "docstrings", i)
                     for i, e in enumerate(data.get("docstrings") or [])]
        repos: dict[str, tuple[DocRule, ...]] = {}
        for i, entry in enumerate(data.get("repo") or []):
            repo = entry.get("repo")
            if not isinstance(repo, str) or "/" not in repo:
                raise ValueError(f"[[repo]] #{i}: 'repo' must be an \"owner/name\" string")
            if repo in repos:
                raise ValueError(f"[[repo]] #{i}: duplicate entry for {repo!r}")
            section = f"repo:{repo}"
            repos[repo] = tuple(DocRule.from_entry(e, section, j, need_path=True)
                                for j, e in enumerate(entry.get("docstrings") or []))
        consumption = dict(data.get("consumption") or {})
        consumption.setdefault("enabled", True)
        consumption.setdefault("getdoc", ["inspect.getdoc", "pydoc.getdoc"])
        if not isinstance(consumption["getdoc"], list) or not all(
                isinstance(x, str) for x in consumption["getdoc"]):
            raise ValueError("[consumption] getdoc must be a list of dotted names")

        return cls(
            keep=rules("keep"),
            human=rules("human"),
            watch=rules("watch"),
            version=data.get("version"),
            source=source,
            docstrings=doc_rules,
            repos=repos,
            consumption=consumption,
        )

    def classify_docstring(self, value: str, owner: str, module_text: str | None) -> str | None:
        """The name of the first general ``[[docstrings]]`` rule keeping this docstring, or None."""
        for rule in self.docstrings:
            if rule.matches(value, owner, module_text):
                return rule.name
        return None

    def repo_docstring_rules(self, repo: str | None, path: str | None) -> list[DocRule]:
        """The per-repo rules that apply to ``path`` in ``repo`` (usually none)."""
        if not repo or repo not in self.repos:
            return []
        return [r for r in self.repos[repo] if r.matches_path(path)]

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
                f"watch={len(self.watch)}, docstrings={len(self.docstrings)}, "
                f"repos={len(self.repos)}, source={self.source!r})")


def load(path=DEFAULT_PATH) -> Directives:
    """Read a directives TOML file (tomllib) and return a Directives object."""
    p = Path(path)
    with open(p, "rb") as fh:
        data = tomllib.load(fh)
    return Directives.from_dict(data, source=str(p))


def loads(text: str) -> Directives:
    """Parse directives from a TOML string (tests)."""
    return Directives.from_dict(tomllib.loads(text), source="<string>")
