import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness import astcheck, directives  # noqa: E402

D = directives.load()


class TestEqual(unittest.TestCase):
    def ok(self, a, b):
        ok, detail = astcheck.equal(a.encode(), b.encode(), D)
        self.assertTrue(ok, detail)

    def bad(self, a, b, needle):
        ok, detail = astcheck.equal(a.encode(), b.encode(), D)
        self.assertFalse(ok)
        self.assertIn(needle, detail)

    def test_ok_cases(self):
        self.ok('"""d"""\nx = 1  # c\n', "x = 1\n")
        self.ok('def f():\n    """d"""\n', "def f():\n    pass\n")
        self.ok('def f():\n    """>>> d"""\n', 'def f():\n    """>>> d"""\n')
        self.ok('def f():\n    "a"\n    "b"\n', "def f():\n    pass\n")
        self.ok('x = 1  # noqa\n', 'x = 1  # noqa\n')
        self.ok('"""only"""\n', '')

    def test_failures(self):
        self.bad("x = 1\n", "x = 2\n", "AST differs")
        self.bad("x = 1\n", "x = (\n", "does not parse")
        self.bad('def f():\n    """d"""\n', 'def f():\n    """d"""\n', "docstrings remain")
        self.bad('def f():\n    """>>> d"""\n', 'def f():\n    pass\n', "AST differs")
        self.bad("x = 1  # c\n", "x = 1  # c\n", "do not classify keep/human")
        # removing a directive is not AST-visible: astcheck reports ok
        ok, _ = astcheck.equal(b"x = 1  # noqa\n", b"x = 1\n", D)
        self.assertTrue(ok)

    def test_orig_unparseable(self):
        ok, d = astcheck.equal(b"def f(:\n", b"def f(:\n", D)
        self.assertTrue(ok)
        ok, d = astcheck.equal(b"def f(:\n", b"x = 1\n", D)
        self.assertFalse(ok)


class TestKeptDocstrings(unittest.TestCase):
    """Rule 3: a docstring may remain only when a rule or the context allows it, and only
    if it is the original's."""

    def test_general_rule_needs_no_context(self):
        src = '"""x PYTEST_DONT_REWRITE"""\nx = 1\n'
        ok, detail = astcheck.equal(src.encode(), src.encode(), D)
        self.assertTrue(ok, detail)

    def test_context_allows_and_its_absence_refuses(self):
        src = 'class C:\n    """c"""\n    def m(self):\n        """m"""\n'
        kept = 'class C:\n    def m(self):\n        """m"""\n'
        ok, _ = astcheck.equal(src.encode(), kept.encode(), D, [("C\\.m", "consumed")])
        self.assertTrue(ok)
        ok, detail = astcheck.equal(src.encode(), kept.encode(), D, [("C", "consumed")])
        self.assertFalse(ok)
        self.assertIn("line 3 (C.m)", detail)

    def test_a_kept_docstring_must_be_the_original(self):
        src = 'def f():\n    """one"""\n'
        forged = 'def f():\n    """two"""\n'
        ok, detail = astcheck.equal(src.encode(), forged.encode(), D, [("f", "x")])
        self.assertFalse(ok)
        self.assertIn("not the original's docstring", detail)

    def test_remaining_docstrings_reports_owner_and_value(self):
        import ast
        tree = ast.parse('"""m"""\nclass C:\n    def f(self):\n        """f"""\n')
        self.assertEqual(astcheck.remaining_docstrings(tree), [(1, "<module>", "m"), (4, "C.f", "f")])


if __name__ == "__main__":
    unittest.main()
