"""Sideword stripper: remove comments and docstrings from Python source (harness/CONTRACT.md).

Public API::

    from harness.strip import strip_source
    out_bytes, records = strip_source(src_bytes, directives, keep_owners=None)

``records`` is the sidecar: one dict per removal / keep, ordered by original position, with
the ``stats`` record last.  Edits are span deletions/replacements on the ORIGINAL bytes, so
encoding, BOM, per-line line endings, tabs and every untouched byte stay identical.

A docstring survives when (in this order) it holds a doctest, a general ``[[docstrings]]``
rule in directives.toml matches it, or its owner matches ``keep_owners`` -- a list of
``(owner_regex, rule_name)`` pairs the caller derives from context the blob alone cannot
carry: the consumption analysis (harness/docuse.py) and the per-repo tier of
directives.toml, both resolved by pass 1. Kept docstrings are recorded as
``{"kind": "docstring", "action": "kept", "rule": ...}`` and counted in
``stats.docstrings_kept``; a non-empty ``keep_owners`` is echoed in ``stats.keep_owners``
so a cache entry says what context it was written under.

CLI::

    strip.py [--directives corpus/directives.toml] [--sidecar OUT.jsonl] [-o OUT.py] [--check] IN.py
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
import warnings
from pathlib import Path

if __package__ in (None, ""):  # run as a script: make sibling modules importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from harness import directives as _directives_mod
else:
    from . import directives as _directives_mod

DOC_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
_LINE_RE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n|\Z)")
_PARSE_ERRORS = (SyntaxError, ValueError, UnicodeDecodeError, LookupError, RecursionError,
                 tokenize.TokenError, MemoryError)


class ParseFailure(Exception):
    pass


def split_lines(text: str) -> list[str]:
    """Physical lines with their own terminators; only \\r\\n, \\r, \\n terminate a line
    (unlike str.splitlines, which also splits on \\f, \\v, \\x1c.., \\u2028..)."""
    out = []
    pos = 0
    n = len(text)
    while pos < n:
        m = _LINE_RE.match(text, pos)
        out.append(m.group())
        pos = m.end()
    return out


def count_lines(data: bytes) -> int:
    """Number of physical lines (a final unterminated line counts)."""
    if not data:
        return 0
    n = data.count(b"\n") + data.count(b"\r") - data.count(b"\r\n")
    if not data.endswith((b"\n", b"\r")):
        n += 1
    return n


def is_doctest(value: str) -> bool:
    for line in value.splitlines():
        if line.lstrip().startswith(">>>"):
            return True
    return False


def is_str_expr(stmt) -> bool:
    return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str))


def iter_doc_owners(tree):
    """Yield ``(node, qualname)`` for every docstring owner, in source order.

    ``<module>`` for the module, ``Cls``, ``Cls.meth``, ``f.inner`` otherwise -- the same
    names the sidecar's ``owner`` field carries. Statement lists only: an expression never
    contains a statement, so lambdas and comprehensions are never descended into.
    """
    def walk(node, qual):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = qual + [node.name]
            yield node, ".".join(qual)
        elif isinstance(node, ast.Module):
            yield node, "<module>"
        for _field, value in ast.iter_fields(node):
            if type(value) is list and value and isinstance(
                    value[0], (ast.stmt, ast.excepthandler, ast.match_case)):
                for item in value:
                    yield from walk(item, qual)
    yield from walk(tree, [])


class KeepOwners:
    """``[(owner_regex, rule_name), ...]`` compiled once; ``match(owner) -> rule | None``."""

    __slots__ = ("pairs", "_compiled")

    def __init__(self, pairs=None):
        self.pairs = sorted({(str(p), str(r)) for p, r in (pairs or ())})
        self._compiled = [(re.compile(p), r) for p, r in self.pairs]

    def __bool__(self):
        return bool(self.pairs)

    def match(self, owner: str) -> str | None:
        for rx, rule in self._compiled:
            if rx.fullmatch(owner):
                return rule
        return None

    def as_list(self) -> list[list[str]]:
        return [[p, r] for p, r in self.pairs]


def keep_owners_from_sidecar(records) -> list[tuple[str, str]]:
    """The ``keep_owners`` a sidecar was written under (empty for the ordinary blob)."""
    for rec in reversed(list(records)):
        if rec.get("kind") == "stats":
            return [(p, r) for p, r in rec.get("keep_owners") or []]
    return []


def _empty_stats(src: bytes, keep_owners=None) -> dict:
    n = count_lines(src)
    st = {"kind": "stats", "comments_removed": 0, "docstrings_removed": 0,
          "doctest_docstrings_kept": 0, "docstrings_kept": 0, "directives_kept": 0,
          "stray_strings_kept": 0, "unresolved": 0, "lines_before": n, "lines_after": n,
          "bytes_before": len(src), "bytes_after": len(src)}
    if keep_owners:
        st["keep_owners"] = keep_owners.as_list()
    return st


class _Stripper:
    """One-shot worker; ``run()`` returns (out_bytes, records)."""

    def __init__(self, src: bytes, directives, keep_owners=None):
        self.src = src
        self.directives = directives
        self.keep_owners = keep_owners if isinstance(keep_owners, KeepOwners) else KeepOwners(keep_owners)
        self.records: list[tuple[tuple[int, int], dict]] = []
        # spans: (start, end, replacement) in char offsets of self.text
        self.spans: list[tuple[int, int, str]] = []
        self.stats = {"comments_removed": 0, "docstrings_removed": 0,
                      "doctest_docstrings_kept": 0, "docstrings_kept": 0,
                      "directives_kept": 0, "stray_strings_kept": 0, "unresolved": 0}

    # ---- setup -----------------------------------------------------------------------
    def decode(self):
        try:
            encoding, _ = tokenize.detect_encoding(io.BytesIO(self.src).readline)
            self.encoding = encoding
            text = self.src.decode(encoding)
        except _PARSE_ERRORS as e:
            raise ParseFailure(f"decode {type(e).__name__}: {e}") from None
        if text.encode(encoding) != self.src:
            raise ParseFailure(f"encoding {encoding!r} does not round-trip byte-identically")
        self.text = text
        self.lines = split_lines(text)
        starts = []
        pos = 0
        for line in self.lines:
            starts.append(pos)
            pos += len(line)
        starts.append(pos)  # sentinel: EOF
        self.line_starts = starts
        # normalized copy for tokenize/ast (line numbers agree; columns agree per line)
        self.ntext = text.replace("\r\n", "\n").replace("\r", "\n")
        self.nlines = None

    def parse(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                self.tree = ast.parse(self.ntext)
            except _PARSE_ERRORS as e:
                raise ParseFailure(f"{type(e).__name__}: {e}") from None
            try:
                self.tokens = list(tokenize.generate_tokens(io.StringIO(self.ntext).readline))
            except _PARSE_ERRORS as e:
                raise ParseFailure(f"tokenize {type(e).__name__}: {e}") from None
        self.comments_by_line = {}
        for tok in self.tokens:
            if tok.type == tokenize.COMMENT:
                self.comments_by_line[tok.start[0]] = tok

    # ---- coordinates -----------------------------------------------------------------
    def line_span(self, row: int) -> tuple[int, int, int]:
        """(start, content_end, end) char offsets of physical line ``row`` (1-based)."""
        start = self.line_starts[row - 1]
        end = self.line_starts[row]
        line = self.lines[row - 1]
        if line.endswith("\r\n"):
            content_end = end - 2
        elif line.endswith(("\n", "\r")):
            content_end = end - 1
        else:
            content_end = end
        return start, content_end, end

    def ast_col_to_char(self, row: int, col: int) -> int:
        line = self.lines[row - 1]
        if line.isascii():
            return col
        return len(line.encode("utf-8")[:col].decode("utf-8", errors="replace"))

    # ---- comments --------------------------------------------------------------------
    def do_comments(self):
        classify = self.directives.classify
        for tok in self.tokens:
            if tok.type != tokenize.COMMENT:
                continue
            row, col = tok.start
            text = tok.string
            cls, name = classify(text, row)
            if cls == _directives_mod.KEEP:
                self.stats["directives_kept"] += 1
                self.records.append(((row, col), {"kind": "directive", "action": "kept",
                                                  "line": row, "col": col, "text": text,
                                                  "rule": name}))
                continue
            rec = {"kind": "comment", "action": "removed", "line": row, "col": col,
                   "text": text, "unresolved": False}
            if cls == _directives_mod.UNRESOLVED:
                rec["unresolved"] = True
                rec["watch"] = name
                self.stats["unresolved"] += 1
            self.stats["comments_removed"] += 1
            self.records.append(((row, col), rec))
            ls, ce, le = self.line_span(row)
            prefix = self.lines[row - 1][:col]
            if prefix.strip() == "":
                # full-line comment: delete the physical line incl. its newline
                self.spans.append((ls, le, ""))
            else:
                j = len(prefix.rstrip())
                self.spans.append((ls + j, ce, ""))

    # ---- docstrings ------------------------------------------------------------------
    def do_docstrings(self):
        self._visit(self.tree, [])

    def docstring_keep_rule(self, value: str, owner: str) -> str | None:
        """Why this (non-doctest) docstring stays, or None: general tier first, then context."""
        classify = getattr(self.directives, "classify_docstring", None)
        if classify is not None:
            rule = classify(value, owner, self.ntext)
            if rule is not None:
                return rule
        return self.keep_owners.match(owner)

    def _visit(self, node, qual: list[str]):
        # Statements only: expressions never contain statements, so skip them entirely.
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = qual + [node.name]
        for field, value in ast.iter_fields(node):
            if type(value) is list and value and isinstance(value[0], ast.stmt):
                self._visit_body(node, field, value, qual)
                for item in value:
                    self._visit(item, qual)
            elif type(value) is list and value and isinstance(value[0], (ast.excepthandler, ast.match_case)):
                for item in value:
                    self._visit(item, qual)

    def _visit_body(self, parent, field, body, qual):
        owner = ".".join(qual) if qual else "<module>"
        i = 0
        if field == "body" and isinstance(parent, DOC_OWNERS):
            removed = []
            while i < len(body) and is_str_expr(body[i]):
                stmt = body[i]
                if is_doctest(stmt.value.value):
                    self.stats["doctest_docstrings_kept"] += 1
                    self.records.append(((stmt.lineno, stmt.col_offset),
                                         {"kind": "doctest_docstring", "action": "kept",
                                          "line": stmt.lineno, "end_line": stmt.end_lineno,
                                          "owner": owner}))
                    i += 1
                    break
                rule = self.docstring_keep_rule(stmt.value.value, owner)
                if rule is not None:
                    self.stats["docstrings_kept"] += 1
                    self.records.append(((stmt.lineno, stmt.col_offset),
                                         {"kind": "docstring", "action": "kept",
                                          "line": stmt.lineno, "end_line": stmt.end_lineno,
                                          "owner": owner, "rule": rule}))
                    i += 1
                    break
                removed.append(stmt)
                i += 1
            empties = (len(removed) == len(body)
                       and not isinstance(parent, ast.Module))
            for k, stmt in enumerate(removed):
                self._remove_docstring(stmt, owner,
                                       need_pass=empties and k == len(removed) - 1)
        for stmt in body[i:]:
            if is_str_expr(stmt):
                self.stats["stray_strings_kept"] += 1
                self.records.append(((stmt.lineno, stmt.col_offset),
                                     {"kind": "stray_string", "action": "kept",
                                      "line": stmt.lineno, "end_line": stmt.end_lineno}))

    def _remove_docstring(self, stmt, owner: str, need_pass: bool):
        sl, el = stmt.lineno, stmt.end_lineno
        sc = self.ast_col_to_char(sl, stmt.col_offset)
        ec = self.ast_col_to_char(el, stmt.end_col_offset)
        ls_s, _, _ = self.line_span(sl)
        ls_e, ce_e, le_e = self.line_span(el)
        ss = ls_s + sc          # docstring start (char offset)
        se = ls_e + ec          # docstring end
        text = self.text[ss:se]
        self.stats["docstrings_removed"] += 1
        self.records.append(((sl, stmt.col_offset),
                             {"kind": "docstring", "action": "removed", "line": sl,
                              "end_line": el, "text": text, "owner": owner}))

        starts_line = self.lines[sl - 1][:sc].strip() == ""
        rest = self.text[se:ce_e]           # remainder of the physical line, no terminator
        del_end = se                        # end of the deletion when not whole-line
        stripped = rest.lstrip()
        if stripped.startswith(";"):
            semi = se + (len(rest) - len(stripped)) + 1
            after = self.text[semi:ce_e]
            after_stripped = after.lstrip()
            if after_stripped and not after_stripped.startswith("#"):
                # code follows on the same line: delete through the whitespace after ';'
                self.spans.append((ss, semi + (len(after) - len(after_stripped)), ""))
                return
            del_end = semi
            rest = after
            stripped = after_stripped
        # now the remainder is whitespace-only or a comment
        if need_pass:
            repl = "pass"
            if not starts_line and ss > 0 and self.text[ss - 1] not in " \t":
                repl = " pass"
            if stripped == "":
                self.spans.append((ss, ce_e, repl))
            else:
                self.spans.append((ss, del_end, repl))
            return
        if stripped.startswith("#"):
            tok = self.comments_by_line.get(el)
            kept = (tok is not None
                    and self.directives.classify(tok.string, el)[0] == _directives_mod.KEEP)
            if kept:
                # keep the directive; it becomes a full-line comment at the docstring's indent
                comment_start = del_end + (len(rest) - len(stripped))
                self.spans.append((ss, comment_start, ""))
                return
        if starts_line:
            self.spans.append((ls_s, le_e, ""))     # whole physical line(s)
        else:
            self.spans.append((ss, ce_e, ""))

    # ---- apply -----------------------------------------------------------------------
    def apply(self) -> bytes:
        if not self.spans:
            return self.src
        spans = sorted(self.spans, key=lambda s: (s[0], s[1]))
        merged: list[list] = []
        for s, e, r in spans:
            if merged and s < merged[-1][1]:
                prev = merged[-1]
                if prev[2] != "" or r != "":
                    raise AssertionError(f"overlapping replacement spans {prev} / {(s, e, r)}")
                prev[1] = max(prev[1], e)
                continue
            merged.append([s, e, r])
        pieces = []
        pos = 0
        text = self.text
        for s, e, r in merged:
            pieces.append(text[pos:s])
            if r:
                pieces.append(r)
            pos = e
        pieces.append(text[pos:])
        return "".join(pieces).encode(self.encoding)

    def run(self):
        try:
            self.decode()
            self.parse()
        except ParseFailure as e:
            return self.src, [{"kind": "parse_error", "error": str(e)},
                              _empty_stats(self.src, self.keep_owners)]
        self.do_comments()
        self.do_docstrings()
        out = self.apply()
        self.records.sort(key=lambda r: r[0])
        recs = [r for _, r in self.records]
        stats = {"kind": "stats", **self.stats,
                 "lines_before": len(self.lines), "lines_after": count_lines(out),
                 "bytes_before": len(self.src), "bytes_after": len(out)}
        if self.keep_owners:
            stats["keep_owners"] = self.keep_owners.as_list()
        recs.append(stats)
        return out, recs


def group_comment_blocks(records: list[dict], lines: list[str]) -> list[dict]:
    """Merge runs of consecutive full-line comment records into one record each.

    The sidecar is deliberately per-token: it is a faithful account of what was
    removed, and ``comments_removed`` counts comments. A *documentation* record
    is a block (``FORMAT.md`` §3), because an anchor is semantic — two records
    on one anchor with one kind have nothing to tell them apart.

    A block ends at a blank line, a line of code, a change of indent, a tool
    directive, or a trailing comment; those all show up here as a break in the
    run of consecutive line numbers at one column. A trailing comment (one
    sharing its line with code) is never merged.

    The merged record keeps the first line's ``col`` and carries ``end_line``;
    its text is the lines joined with newlines. Callers that classify a record
    read the first line, since a kind is a property of the block.
    """
    def full_line(rec: dict) -> bool:
        row, col = rec["line"], rec.get("col", 0)
        if not 0 < row <= len(lines):
            return False
        return lines[row - 1][:col].strip() == ""

    out: list[dict] = []
    for rec in records:
        mergeable = rec.get("kind") == "comment" and rec.get("action") == "removed" and full_line(rec)
        if mergeable and out:
            last = out[-1]
            joins = (last.get("kind") == "comment" and last.get("action") == "removed"
                     and last.get("_block")
                     and last.get("col") == rec.get("col")
                     and last["end_line"] + 1 == rec["line"])
            if joins:
                last["end_line"] = rec["line"]
                last["text"] = last["text"] + "\n" + rec["text"]
                last["lines_in_block"] += 1
                last["unresolved"] = last.get("unresolved") or rec.get("unresolved", False)
                continue
        rec = dict(rec)
        if mergeable:
            rec["_block"] = True
            rec["end_line"] = rec["line"]
            rec["lines_in_block"] = 1
        out.append(rec)

    for rec in out:
        rec.pop("_block", None)
    return out


def strip_source(src: bytes, directives, keep_owners=None) -> tuple[bytes, list[dict]]:
    """Strip comments/docstrings from ``src``; return (stripped_bytes, sidecar_records).

    ``keep_owners``: ``[(owner_regex, rule_name), ...]`` (or a ``KeepOwners``) naming
    docstrings that must survive for reasons outside this file -- see the module docstring.
    """
    if isinstance(src, str):
        raise TypeError("strip_source expects bytes")
    return _Stripper(src, directives, keep_owners).run()


# ---- CLI --------------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("input", help="input .py file")
    ap.add_argument("--directives", default=str(_directives_mod.DEFAULT_PATH))
    ap.add_argument("--sidecar", help="write JSONL sidecar here")
    ap.add_argument("-o", "--output", help="write stripped source here (default: stdout)")
    ap.add_argument("--check", action="store_true",
                    help="run astcheck.equal on the result; exit nonzero on failure")
    ap.add_argument("--keep-owner", action="append", default=[], metavar="REGEX[=RULE]",
                    help="keep the docstring of every owner whose qualified name fullmatches "
                         "REGEX (repeatable); RULE defaults to 'cli'")
    args = ap.parse_args(argv)

    directives = _directives_mod.load(args.directives)
    src = Path(args.input).read_bytes()
    keep_owners = []
    for spec in args.keep_owner:
        pattern, _, rule = spec.partition("=")
        keep_owners.append((pattern, rule or "cli"))
    out, records = strip_source(src, directives, keep_owners)

    if args.sidecar:
        with open(args.sidecar, "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if args.output:
        Path(args.output).write_bytes(out)
    else:
        sys.stdout.buffer.write(out)
        sys.stdout.buffer.flush()

    rc = 0
    if args.check:
        if __package__ in (None, ""):
            from harness import astcheck
        else:
            from . import astcheck
        ok, detail = astcheck.equal(src, out, directives, keep_owners)
        if not ok:
            print(f"astcheck FAILED: {detail}", file=sys.stderr)
            rc = 1
        else:
            print("astcheck ok", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
