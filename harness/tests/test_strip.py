"""Sharp-edge unit tests for harness/strip.py."""

import io
import json
import os
import subprocess
import sys
import tempfile
import tokenize
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness import astcheck, directives, strip  # noqa: E402

D = directives.load()
PY = sys.executable


def run(src, d=D):
    if isinstance(src, str):
        src = src.encode("utf-8")
    out, recs = strip.strip_source(src, d)
    ok, detail = astcheck.equal(src, out, d)
    if not ok:
        raise AssertionError(f"astcheck failed:\n{detail}\n--- out ---\n{out!r}")
    assert recs[-1]["kind"] == "stats"
    # idempotence
    out2, _ = strip.strip_source(out, d)
    if out2 != out:
        raise AssertionError(f"not idempotent:\n{out!r}\n->\n{out2!r}")
    return out, recs


def kinds(recs):
    return [r["kind"] for r in recs[:-1]]


class TestComments(unittest.TestCase):
    def test_full_line_and_trailing(self):
        out, recs = run("# top\nx = 1  # trailing\n# full\ny = 2\n")
        self.assertEqual(out, b"x = 1\ny = 2\n")
        st = recs[-1]
        self.assertEqual(st["comments_removed"], 3)
        self.assertEqual(st["lines_before"], 4)
        self.assertEqual(st["lines_after"], 2)
        self.assertEqual(recs[0], {"kind": "comment", "action": "removed", "line": 1, "col": 0,
                                   "text": "# top", "unresolved": False})
        self.assertEqual(recs[1]["line"], 2)
        self.assertEqual(recs[1]["col"], 7)

    def test_never_leaves_trailing_whitespace(self):
        out, _ = run("x = 1    \t # c\n")
        self.assertEqual(out, b"x = 1\n")

    def test_comment_inside_brackets_own_line(self):
        src = "x = [\n    1,  # one\n    # two\n    2,\n]\n"
        out, _ = run(src)
        self.assertEqual(out, b"x = [\n    1,\n    2,\n]\n")

    def test_lambda_default_with_comment_inside_call_parens(self):
        src = "f(lambda x=1: x,  # default\n  # own line\n  2)\n"
        out, _ = run(src)
        self.assertEqual(out, b"f(lambda x=1: x,\n  2)\n")

    def test_comment_last_line_no_trailing_newline(self):
        out, _ = run("x = 1\n# last")
        self.assertEqual(out, b"x = 1\n")
        out, _ = run("x = 1  # last")
        self.assertEqual(out, b"x = 1")

    def test_file_without_trailing_newline(self):
        out, recs = run("x = 1\ny = 2")
        self.assertEqual(out, b"x = 1\ny = 2")
        self.assertEqual(recs[-1]["lines_before"], 2)

    def test_empty_file(self):
        out, recs = run(b"")
        self.assertEqual(out, b"")
        self.assertEqual(recs, [{"kind": "stats", "comments_removed": 0, "docstrings_removed": 0,
                                 "doctest_docstrings_kept": 0, "docstrings_kept": 0,
                                 "directives_kept": 0,
                                 "stray_strings_kept": 0, "unresolved": 0, "lines_before": 0,
                                 "lines_after": 0, "bytes_before": 0, "bytes_after": 0}])

    def test_file_with_only_comments(self):
        out, recs = run("# a\n# b\n\n# c\n")
        self.assertEqual(out, b"\n")
        self.assertEqual(recs[-1]["comments_removed"], 3)

    def test_tabs_preserved(self):
        src = "if x:\n\ty = 1\t# tab comment\n\t# full\n\tz = 2\n"
        out, _ = run(src)
        self.assertEqual(out, b"if x:\n\ty = 1\n\tz = 2\n")

    def test_form_feed_line_is_not_a_line_break(self):
        src = "x = 1\n\x0c\n# comment after ff\ny = 2\n"
        out, _ = run(src)
        self.assertEqual(out, b"x = 1\n\x0c\ny = 2\n")


class TestDirectives(unittest.TestCase):
    def test_type_ignore_kept(self):
        out, recs = run("x = f()  # type: ignore\ny = 1  # plain\n")
        self.assertEqual(out, b"x = f()  # type: ignore\ny = 1\n")
        self.assertEqual(recs[0], {"kind": "directive", "action": "kept", "line": 1, "col": 9,
                                   "text": "# type: ignore", "rule": "type-comment"})
        self.assertEqual(recs[-1]["directives_kept"], 1)

    def test_noqa_inside_human_comment_kept(self):
        src = "import os  # we need os here, noqa: F401 says flake8\n"
        out, recs = run(src)
        self.assertEqual(out, src.encode())
        self.assertEqual(recs[0]["rule"], "noqa")

    def test_shebang_line1_kept_line5_removed(self):
        src = "#!/usr/bin/env python\nx = 1\ny = 2\nz = 3\n#!/not/a/shebang\n"
        out, recs = run(src)
        self.assertEqual(out, b"#!/usr/bin/env python\nx = 1\ny = 2\nz = 3\n")
        self.assertEqual(recs[0]["rule"], "shebang")
        self.assertEqual(recs[1]["kind"], "comment")
        self.assertEqual(recs[1]["line"], 5)

    def test_coding_cookie_kept(self):
        src = "#!/usr/bin/python\n# -*- coding: latin-1 -*-\n# human\nx = 1\n"
        out, recs = run(src)
        self.assertEqual(out, b"#!/usr/bin/python\n# -*- coding: latin-1 -*-\nx = 1\n")
        self.assertEqual([r.get("rule") for r in recs[:2]], ["shebang", "coding"])

    def test_fmt_off_kept(self):
        src = "# fmt: off\nx = [1,2]\n# fmt: on\n"
        out, _ = run(src)
        self.assertEqual(out, src.encode())

    def test_unresolved_tool_mention(self):
        # pytype is in the watch vocabulary but has no keep/human rule in the corpus list
        src = "x = 1  # pytype complains about this\n"
        out, recs = run(src)
        self.assertEqual(out, b"x = 1\n")
        self.assertEqual(recs[0]["unresolved"], True)
        self.assertEqual(recs[0]["watch"], "tool-words")
        self.assertEqual(recs[-1]["unresolved"], 1)
        self.assertEqual(recs[-1]["comments_removed"], 1)

    def test_human_entry_whitelists(self):
        d = directives.loads(
            'version = 1\n[[keep]]\nname="noqa"\npattern="noqa"\nkind="contains"\n'
            '[[human]]\nname="mypy-prose"\npattern="mypy complains"\nkind="contains"\n'
            '[[watch]]\nname="tool-words"\npattern="(?i)\\\\bmypy\\\\b"\nkind="regex"\n')
        out, recs = run("x = 1  # mypy complains\ny = 2  # mypy hates this\n", d)
        self.assertEqual(out, b"x = 1\ny = 2\n")
        self.assertFalse(recs[0]["unresolved"])
        self.assertTrue(recs[1]["unresolved"])


class TestDocstrings(unittest.TestCase):
    def test_module_docstring_and_function(self):
        src = '"""Module doc."""\n\ndef f(x):\n    """Doc."""\n    return x\n'
        out, recs = run(src)
        self.assertEqual(out, b"\ndef f(x):\n    return x\n")
        self.assertEqual(recs[0], {"kind": "docstring", "action": "removed", "line": 1,
                                   "end_line": 1, "text": '"""Module doc."""',
                                   "owner": "<module>"})
        self.assertEqual(recs[1]["owner"], "f")
        self.assertEqual(recs[-1]["docstrings_removed"], 2)

    def test_one_liner_def(self):
        out, _ = run('def f(): "doc"\n')
        self.assertEqual(out, b"def f(): pass\n")
        out, _ = run('def f():"doc"\n')
        self.assertEqual(out, b"def f(): pass\n")
        out, _ = run('class C: "doc"\n')
        self.assertEqual(out, b"class C: pass\n")

    def test_one_liner_with_more_statements(self):
        out, _ = run('def f(): "doc"; return 1\n')
        self.assertEqual(out, b"def f(): return 1\n")

    def test_class_with_only_docstring(self):
        out, _ = run('class C:\n    """Only doc."""\n')
        self.assertEqual(out, b"class C:\n    pass\n")

    def test_class_with_only_docstring_tabs(self):
        out, _ = run('class C:\n\t"""Only doc."""\nx = 1\n')
        self.assertEqual(out, b"class C:\n\tpass\nx = 1\n")

    def test_nested_def_body_is_docstring(self):
        src = "def outer():\n    def inner():\n        '''doc'''\n    return inner\n"
        out, recs = run(src)
        self.assertEqual(out, b"def outer():\n    def inner():\n        pass\n    return inner\n")
        self.assertEqual(recs[0]["owner"], "outer.inner")

    def test_method_owner(self):
        src = 'class Cart:\n    def add(self):\n        """Add."""\n        return 1\n'
        out, recs = run(src)
        self.assertEqual(recs[0]["owner"], "Cart.add")
        self.assertEqual(out, b"class Cart:\n    def add(self):\n        return 1\n")

    def test_multiline_docstring(self):
        src = 'def f():\n    """Line one.\n\n    Line three.\n    """\n    return 1\n'
        out, recs = run(src)
        self.assertEqual(out, b"def f():\n    return 1\n")
        self.assertEqual((recs[0]["line"], recs[0]["end_line"]), (2, 5))

    def test_multiline_docstring_empties_body(self):
        src = 'def f():\n    """Line one.\n    Line two.\n    """\n'
        out, _ = run(src)
        self.assertEqual(out, b"def f():\n    pass\n")

    def test_docstring_trailing_noqa_kept(self):
        src = 'def f():\n    """doc"""  # noqa\n    return 1\n'
        out, _ = run(src)
        self.assertEqual(out, b"def f():\n    # noqa\n    return 1\n")
        src = 'def f():\n    """doc"""  # noqa\n'
        out, _ = run(src)
        self.assertEqual(out, b"def f():\n    pass  # noqa\n")

    def test_docstring_trailing_plain_comment(self):
        src = 'def f():\n    """doc"""  # human\n    return 1\n'
        out, _ = run(src)
        self.assertEqual(out, b"def f():\n    return 1\n")
        src = 'def f():\n    """doc"""  # human\n'
        out, _ = run(src)
        self.assertEqual(out, b"def f():\n    pass\n")

    def test_docstring_followed_by_comment_next_line(self):
        src = 'def f():\n    """doc"""\n    # comment\n    return 1\n'
        out, _ = run(src)
        self.assertEqual(out, b"def f():\n    return 1\n")
        src = 'def f():\n    """doc"""\n    # comment\n'
        out, _ = run(src)
        self.assertEqual(out, b"def f():\n    pass\n")

    def test_decorator_plus_docstring(self):
        src = '@dec\n@other(1)  # c\ndef f():\n    """doc"""\n    pass\n'
        out, _ = run(src)
        self.assertEqual(out, b"@dec\n@other(1)\ndef f():\n    pass\n")

    def test_doctest_kept(self):
        src = 'def f():\n    """Doc.\n\n    >>> f()\n    1\n    """\n    return 1\n'
        out, recs = run(src)
        self.assertEqual(out, src.encode())
        self.assertEqual(recs[0], {"kind": "doctest_docstring", "action": "kept", "line": 2,
                                   "end_line": 6, "owner": "f"})
        self.assertEqual(recs[-1]["doctest_docstrings_kept"], 1)

    def test_module_only_docstring_becomes_empty(self):
        out, _ = run('"""Just a docstring."""\n')
        self.assertEqual(out, b"")

    def test_future_import_stays_first(self):
        src = '"""Doc."""\nfrom __future__ import annotations\nx: "int" = 1\n'
        out, _ = run(src)
        self.assertEqual(out, b'from __future__ import annotations\nx: "int" = 1\n')
        compile(out, "<t>", "exec")

    def test_async_def(self):
        src = 'async def f():\n    """doc"""\n    await g()\n\nasync def h():\n    """only"""\n'
        out, recs = run(src)
        self.assertEqual(out, b"async def f():\n    await g()\n\nasync def h():\n    pass\n")
        self.assertEqual([r["owner"] for r in recs[:2]], ["f", "h"])

    def test_stray_string_kept(self):
        src = 'x = 1\n"""attribute doc"""\ndef f():\n    y = 2\n    "not a docstring"\n'
        out, recs = run(src)
        self.assertEqual(out, src.encode())
        self.assertEqual(kinds(recs), ["stray_string", "stray_string"])
        self.assertEqual(recs[0], {"kind": "stray_string", "action": "kept", "line": 2,
                                   "end_line": 2})
        self.assertEqual(recs[-1]["stray_strings_kept"], 2)

    def test_string_in_if_body_is_stray_not_docstring(self):
        src = 'if x:\n    "s"\n    y = 1\n'
        out, recs = run(src)
        self.assertEqual(out, src.encode())
        self.assertEqual(kinds(recs), ["stray_string"])

    def test_bytes_expr_is_not_a_docstring(self):
        src = 'def f():\n    b"bytes"\n'
        out, recs = run(src)
        self.assertEqual(out, src.encode())
        self.assertEqual(kinds(recs), [])

    def test_implicit_concatenation(self):
        src = 'def f():\n    ("a"\n     "b")\n    return 1\n'
        out, recs = run(src)
        self.assertEqual(out, b"def f():\n    return 1\n")
        self.assertEqual(recs[0]["text"], '("a"\n     "b")')
        src = 'def f():\n    "a" \\\n    "b"\n'
        out, _ = run(src)
        self.assertEqual(out, b"def f():\n    pass\n")

    def test_parenthesized_one_liner(self):
        out, _ = run('class C: ("d")\n')
        self.assertEqual(out, b"class C: pass\n")

    def test_semicolon_after_docstring(self):
        out, _ = run('def f():\n    "doc"; x = 1\n')
        self.assertEqual(out, b"def f():\n    x = 1\n")
        out, _ = run('def f():\n    "doc";\n')
        self.assertEqual(out, b"def f():\n    pass\n")
        out, _ = run('def f():\n    "doc";  # c\n    return 1\n')
        self.assertEqual(out, b"def f():\n    return 1\n")

    def test_consecutive_leading_strings_cascade(self):
        # after the docstring goes, the next bare string would become the docstring;
        # the stripper removes the whole leading run (astcheck.norm mirrors this).
        src = 'def f():\n    "a"\n    "b"\n    return 1\n'
        out, recs = run(src)
        self.assertEqual(out, b"def f():\n    return 1\n")
        self.assertEqual(kinds(recs), ["docstring", "docstring"])
        src = 'def f():\n    "a"\n    "b"\n'
        out, _ = run(src)
        self.assertEqual(out, b"def f():\n    pass\n")
        src = 'def f(): "a"; "b"\n'
        out, _ = run(src)
        self.assertEqual(out, b"def f(): pass\n")
        # doctest second string stops the cascade and is kept as the docstring
        src = 'def f():\n    "a"\n    """>>> f()"""\n    "c"\n'
        out, recs = run(src)
        self.assertEqual(out, b'def f():\n    """>>> f()"""\n    "c"\n')
        self.assertEqual(kinds(recs), ["docstring", "doctest_docstring", "stray_string"])

    def test_u_prefix_and_raw(self):
        out, _ = run('def f():\n    u"doc"\n    return r"x"\n')
        self.assertEqual(out, b'def f():\n    return r"x"\n')

    def test_invalid_escape_syntaxwarning_silent(self):
        import warnings
        src = 'def f():\n    "\\d"\n    return "\\d"\n'
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            out, _ = run(src)
        self.assertEqual(out, b'def f():\n    return "\\d"\n')

    def test_class_docstring_then_method_docstring(self):
        src = ('class C:\n    """C doc."""\n\n    def m(self):\n        """m doc."""\n'
               '        # note\n        return 1  # ok\n')
        out, _ = run(src)
        self.assertEqual(out, b"class C:\n\n    def m(self):\n        return 1\n")

    def test_non_ascii_columns(self):
        src = 'é = "ü"  # ç comment\ndef f():\n    """dé"""  # ü\n    return "ñ"  # ö\n'
        out, _ = run(src)
        self.assertEqual(out, 'é = "ü"\ndef f():\n    return "ñ"\n'.encode())


class TestEncodingsAndNewlines(unittest.TestCase):
    def test_bom(self):
        src = b'\xef\xbb\xbf"""doc"""\nx = 1  # c\n'
        out, _ = run(src)
        self.assertEqual(out, b"\xef\xbb\xbfx = 1\n")
        src = b'\xef\xbb\xbfx = 1\n'
        out, _ = run(src)
        self.assertEqual(out, src)

    def test_latin1(self):
        src = ("# -*- coding: latin-1 -*-\n# caf\xe9\nx = '\xe9'  # \xe9\xe8\n"
               "def f():\n    '''d\xe9'''\n    return '\xe9'\n").encode("latin-1")
        out, _ = run(src)
        self.assertEqual(out, ("# -*- coding: latin-1 -*-\nx = '\xe9'\n"
                               "def f():\n    return '\xe9'\n").encode("latin-1"))
        self.assertIsNone(out.decode("latin-1").find("\ufffd") + 1 or None)

    def test_crlf(self):
        src = b'"""doc"""\r\n# c\r\nx = 1  # t\r\ndef f():\r\n    """d"""\r\n    return 1\r\n'
        out, _ = run(src)
        self.assertEqual(out, b"x = 1\r\ndef f():\r\n    return 1\r\n")

    def test_lone_cr(self):
        src = b'x = 1  # a\r# b\ry = 2\r'
        out, recs = run(src)
        self.assertEqual(out, b"x = 1\ry = 2\r")
        self.assertEqual(recs[-1]["lines_before"], 3)

    def test_mixed_endings(self):
        src = (b'"""doc"""\r\nx = 1  # a\n# b\r\ny = 2\rz = 3  # c\r\n'
               b'def f():\n    """d"""\r\n    return 1\r\n')
        out, _ = run(src)
        self.assertEqual(out, b"x = 1\ny = 2\rz = 3\r\ndef f():\n    return 1\r\n")

    def test_multiline_docstring_crlf_empties(self):
        src = b'def f():\r\n    """a\r\n    b"""\r\n'
        out, _ = run(src)
        self.assertEqual(out, b"def f():\r\n    pass\r\n")

    def test_utf8_cookie_without_bom(self):
        src = "# coding: utf-8\nx = 'ü'  # ü\n".encode()
        out, _ = run(src)
        self.assertEqual(out, "# coding: utf-8\nx = 'ü'\n".encode())


class TestParseErrors(unittest.TestCase):
    def test_syntax_error_passthrough(self):
        src = b"def f(:\n    pass  # c\n"
        out, recs = strip.strip_source(src, D)
        self.assertEqual(out, src)
        self.assertEqual(recs[0]["kind"], "parse_error")
        self.assertIn("SyntaxError", recs[0]["error"])
        self.assertEqual(recs[1]["kind"], "stats")
        self.assertEqual(recs[1]["comments_removed"], 0)
        self.assertEqual(recs[1]["bytes_before"], len(src))
        ok, detail = astcheck.equal(src, out, D)
        self.assertTrue(ok, detail)

    def test_bad_encoding_passthrough(self):
        src = b"# -*- coding: no-such-codec -*-\nx = 1\n"
        out, recs = strip.strip_source(src, D)
        self.assertEqual(out, src)
        self.assertEqual(recs[0]["kind"], "parse_error")

    def test_python2_print(self):
        src = b'print "hi"  # c\n'
        out, recs = strip.strip_source(src, D)
        self.assertEqual(out, src)
        self.assertEqual(recs[0]["kind"], "parse_error")

    def test_undecodable_utf8(self):
        src = b'x = "\xff"  # c\n'
        out, recs = strip.strip_source(src, D)
        self.assertEqual(out, src)
        self.assertEqual(recs[0]["kind"], "parse_error")

    def test_str_input_rejected(self):
        with self.assertRaises(TypeError):
            strip.strip_source("x = 1\n", D)


class TestCLI(unittest.TestCase):
    def test_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td, "in.py")
            inp.write_bytes(b'"""doc"""\nx = 1  # c\ny = 2  # noqa\n')
            outp = Path(td, "out.py")
            side = Path(td, "out.jsonl")
            r = subprocess.run([PY, str(ROOT / "harness" / "strip.py"), "--check", "-o", str(outp),
                                "--sidecar", str(side), str(inp)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(outp.read_bytes(), b"x = 1\ny = 2  # noqa\n")
            lines = side.read_text().splitlines()
            recs = [json.loads(l) for l in lines]
            self.assertEqual([r["kind"] for r in recs], ["docstring", "comment", "directive", "stats"])
            # stdout mode
            r = subprocess.run([PY, str(ROOT / "harness" / "strip.py"), str(inp)],
                               capture_output=True)
            self.assertEqual(r.stdout, b"x = 1\ny = 2  # noqa\n")
            # astcheck CLI
            r = subprocess.run([PY, str(ROOT / "harness" / "astcheck.py"), str(inp), str(outp)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            outp.write_bytes(b"x = 1\n")
            r = subprocess.run([PY, str(ROOT / "harness" / "astcheck.py"), str(inp), str(outp)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("AST differs", r.stdout)


class TestDocstringRules(unittest.TestCase):
    """The docstring tiers of directives.toml and the ``keep_owners`` context."""

    PLY = ('import ply.lex as lex\n\n\ndef t_UINT(t):\n    r"[0-9]+"\n    return t\n\n\n'
           'def p_main(p):\n    "main : UINT"\n    p[0] = p[1]\n\n\ndef helper():\n'
           '    "prose"\n    return lex.lex()\n')

    def test_pytest_token_is_kept_by_the_general_tier(self):
        src = '"""Module. PYTEST_DONT_REWRITE"""\n\n\ndef f():\n    """gone"""\n    return 1\n'
        out, recs = run(src)
        self.assertEqual(out, b'"""Module. PYTEST_DONT_REWRITE"""\n\n\ndef f():\n    return 1\n')
        self.assertEqual(recs[0], {"kind": "docstring", "action": "kept", "line": 1, "end_line": 1,
                                   "owner": "<module>", "rule": "pytest-dont-rewrite"})
        self.assertEqual(recs[-1]["docstrings_kept"], 1)
        self.assertEqual(recs[-1]["docstrings_removed"], 1)
        self.assertNotIn("keep_owners", recs[-1])

    def test_ply_grammar_docstrings_are_kept_only_in_ply_modules(self):
        out, recs = run(self.PLY)
        self.assertIn(b'r"[0-9]+"', out)
        self.assertIn(b'"main : UINT"', out)
        self.assertNotIn(b"prose", out)
        self.assertEqual([(r["owner"], r["rule"]) for r in recs if r.get("action") == "kept"],
                         [("t_UINT", "ply-grammar"), ("p_main", "ply-grammar")])
        # same functions, no PLY in sight: ordinary docstrings
        plain = self.PLY.replace("import ply.lex as lex\n", "").replace("lex.lex()", "1")
        out, recs = run(plain)
        self.assertNotIn(b"[0-9]+", out)
        self.assertEqual(recs[-1]["docstrings_kept"], 0)
        # the wrapper-call form (`parsing.lex(...)`) counts too, and nesting keeps the name
        nested = ('from x import parsing\n\n\nclass P:\n    def _make(cls):\n'
                  '        def t_A(t):\n            r"a"\n            return t\n'
                  '        return parsing.lex(lextab="t")\n')
        out, recs = run(nested)
        self.assertIn(b'r"a"', out)
        self.assertEqual(recs[0]["owner"], "P._make.t_A")

    def test_p_value_is_not_a_grammar_rule(self):
        out, _ = run('import ply\n\n\ndef p_value(x):\n    "statistics"\n    return x\n\n\n'
                     'def pvalue(x):\n    "no"\n    return x\n')
        self.assertIn(b'"statistics"', out)      # named like PLY, in a PLY module: kept
        self.assertNotIn(b'"no"', out)

    def test_keep_owners_keeps_exactly_the_named_owners(self):
        src = ('"""mod"""\n\n\nclass Foo:\n    """Foo"""\n\n    def bar(self):\n'
               '        """bar"""\n        return 1\n\n    def baz(self):\n'
               '        """baz"""\n        return 2\n')
        out, recs = strip.strip_source(src.encode(), D, [("Foo\\.bar", "consumed")])
        self.assertEqual(out.decode(), '\n\nclass Foo:\n\n    def bar(self):\n        """bar"""\n'
                                       '        return 1\n\n    def baz(self):\n        return 2\n')
        kept = [r for r in recs if r.get("action") == "kept"]
        self.assertEqual(kept, [{"kind": "docstring", "action": "kept", "line": 8, "end_line": 8,
                                 "owner": "Foo.bar", "rule": "consumed"}])
        self.assertEqual(recs[-1]["docstrings_kept"], 1)
        self.assertEqual(recs[-1]["docstrings_removed"], 3)
        self.assertEqual(recs[-1]["keep_owners"], [["Foo\\.bar", "consumed"]])
        self.assertEqual(strip.keep_owners_from_sidecar(recs), [("Foo\\.bar", "consumed")])
        # the gate knows the context, and only the context
        ok, _ = astcheck.equal(src.encode(), out, D, [("Foo\\.bar", "consumed")])
        self.assertTrue(ok)
        ok, detail = astcheck.equal(src.encode(), out, D)
        self.assertFalse(ok)
        self.assertIn("Foo.bar", detail)
        # idempotent under the same context
        out2, _ = strip.strip_source(out, D, [("Foo\\.bar", "consumed")])
        self.assertEqual(out2, out)

    def test_keep_owners_is_a_fullmatch(self):
        src = 'def f():\n    "f"\n\n\ndef ff():\n    "ff"\n'
        out, _ = strip.strip_source(src.encode(), D, [("f", "x")])
        self.assertEqual(out.decode(), 'def f():\n    "f"\n\n\ndef ff():\n    pass\n')

    def test_keep_owners_context_is_echoed_even_for_a_parse_error(self):
        out, recs = strip.strip_source(b"def f(:\n", D, [("f", "x")])
        self.assertEqual(recs[0]["kind"], "parse_error")
        self.assertEqual(recs[-1]["keep_owners"], [["f", "x"]])
        self.assertEqual(recs[-1]["docstrings_kept"], 0)

    def test_iter_doc_owners_names(self):
        import ast
        tree = ast.parse("class C:\n    def m(self):\n        def inner():\n            pass\n"
                         "async def a():\n    pass\n")
        self.assertEqual([q for _, q in strip.iter_doc_owners(tree)],
                         ["<module>", "C", "C.m", "C.m.inner", "a"])

    def test_cli_keep_owner(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td, "in.py")
            inp.write_bytes(b'def f():\n    """d"""\n    return 1\n')
            r = subprocess.run([PY, str(ROOT / "harness" / "strip.py"), "--check",
                                "--keep-owner", "f=why", str(inp)], capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, b'def f():\n    """d"""\n    return 1\n')


if __name__ == "__main__":
    unittest.main()
