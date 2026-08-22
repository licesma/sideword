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


if __name__ == "__main__":
    unittest.main()
