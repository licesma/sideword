"""AST equality gate for the stripper (harness/CONTRACT.md).

``equal(orig, stripped) -> (ok, detail)`` requires:

  1. ``stripped`` parses (or ``orig`` does not parse and ``stripped == orig``);
  2. ``ast.dump(norm(parse(orig)), include_attributes=False)``
     ``== ast.dump(parse(stripped), include_attributes=False)`` where ``norm`` drops exactly
     the docstring nodes the stripper may drop (leading non-doctest string statements of
     Module / ClassDef / FunctionDef / AsyncFunctionDef bodies) and inserts ``Pass`` when
     that empties a class/function body;
  3. no non-doctest docstring remains in ``stripped``;
  4. every COMMENT token remaining in ``stripped`` classifies as keep (or human).

CLI: ``astcheck.py [--directives PATH] ORIG STRIPPED`` -> exit 0 if equal.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import io
import sys
import tokenize
import warnings
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from harness import directives as _directives_mod
else:
    from . import directives as _directives_mod

DOC_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
_default_directives = None


def _directives(d):
    global _default_directives
    if d is not None:
        return d
    if _default_directives is None:
        _default_directives = _directives_mod.load()
    return _default_directives


def _is_str_expr(stmt) -> bool:
    return (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str))


def _is_doctest(value: str) -> bool:
    return any(l.lstrip().startswith(">>>") for l in value.splitlines())


def _parse(data: bytes):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(data)


def norm(tree: ast.AST) -> ast.AST:
    """Drop leading non-doctest string statements from doc-owner bodies (in place);
    insert Pass when a class/function body empties."""
    for node in ast.walk(tree):
        if not isinstance(node, DOC_OWNERS):
            continue
        body = node.body
        i = 0
        while i < len(body) and _is_str_expr(body[i]) and not _is_doctest(body[i].value.value):
            i += 1
        if i:
            del body[:i]
            if not body and not isinstance(node, ast.Module):
                body.append(ast.Pass())
    return tree


def remaining_docstrings(tree: ast.AST) -> list[tuple[int, str]]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, DOC_OWNERS) and node.body and _is_str_expr(node.body[0]) \
                and not _is_doctest(node.body[0].value.value):
            name = getattr(node, "name", "<module>")
            out.append((node.body[0].lineno, name))
    return out


def offending_comments(stripped: bytes, directives) -> list[tuple[int, int, str, str]]:
    out = []
    try:
        toks = tokenize.tokenize(io.BytesIO(stripped).readline)
        for tok in toks:
            if tok.type == tokenize.COMMENT:
                cls, name = directives.classify(tok.string, tok.start[0])
                if cls not in (_directives_mod.KEEP, _directives_mod.HUMAN):
                    out.append((tok.start[0], tok.start[1], tok.string, cls))
    except (tokenize.TokenError, SyntaxError) as e:  # pragma: no cover
        out.append((0, 0, f"<tokenize failed: {e}>", "error"))
    return out


def _dump_diff(a: str, b: str, limit: int = 12) -> str:
    al = a.split(", ")
    bl = b.split(", ")
    lines = []
    for line in difflib.unified_diff(al, bl, "orig(norm)", "stripped", n=1, lineterm=""):
        lines.append(line)
        if len(lines) >= limit:
            lines.append("...")
            break
    return "\n".join(lines)


def equal(orig: bytes, stripped: bytes, directives=None) -> tuple[bool, str]:
    """Return (ok, detail).  See module docstring for the exact conditions."""
    directives = _directives(directives)
    try:
        otree = _parse(orig)
    except (SyntaxError, ValueError) as e:
        if stripped == orig:
            return True, f"orig does not parse ({type(e).__name__}); stripped is byte-identical"
        return False, f"orig does not parse ({type(e).__name__}: {e}) but stripped differs"
    try:
        stree = _parse(stripped)
    except (SyntaxError, ValueError) as e:
        return False, f"stripped does not parse: {type(e).__name__}: {e}"

    problems = []
    a = ast.dump(norm(otree), include_attributes=False)
    b = ast.dump(stree, include_attributes=False)
    if a != b:
        problems.append("AST differs:\n" + _dump_diff(a, b))
    left = remaining_docstrings(stree)
    if left:
        problems.append("non-doctest docstrings remain in stripped: "
                        + ", ".join(f"line {ln} ({name})" for ln, name in left[:10]))
    bad = offending_comments(stripped, directives)
    if bad:
        problems.append("comments remaining in stripped that do not classify keep/human: "
                        + "; ".join(f"line {ln} col {c} {cls}: {txt!r}" for ln, c, txt, cls in bad[:10]))
    if problems:
        return False, "\n".join(problems)
    return True, "ok"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check that STRIPPED is AST-equal to ORIG.")
    ap.add_argument("orig")
    ap.add_argument("stripped")
    ap.add_argument("--directives", default=None)
    args = ap.parse_args(argv)
    d = _directives_mod.load(args.directives) if args.directives else None
    ok, detail = equal(Path(args.orig).read_bytes(), Path(args.stripped).read_bytes(), d)
    print(("OK: " if ok else "FAIL: ") + detail)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
