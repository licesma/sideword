import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from harness.paths import is_test_path  # noqa: E402


class TestIsTestPath(unittest.TestCase):
    def test_segments(self):
        for p in ["tests/x.py", "a/tests/x.py", "a/test/b/x.py", "testing/x.py", "test/__init__.py",
                  "sympy/core/tests/test_x.py", "./tests/x.py", "a\\tests\\x.py"]:
            self.assertTrue(is_test_path(p), p)

    def test_basenames(self):
        for p in ["conftest.py", "a/conftest.py", "a/tests.py", "a/test_x.py", "test_x.py",
                  "a/x_test.py"]:
            self.assertTrue(is_test_path(p), p)

    def test_not_tests(self):
        for p in ["doc/conf.py", "docs/x.py", "examples/x.py", "benchmarks/b.py", "setup.py",
                  "a/testx.py", "a/xtest.py", "a/testing_utils.py", "a/tester/x.py",
                  "a/pytest.py", "a/contest.py", "a/tests_helper.py", "src/x.py", "a/latest/x.py"]:
            self.assertFalse(is_test_path(p), p)

    def test_extra(self):
        extra = {"sympy/core/foo.py"}
        self.assertTrue(is_test_path("sympy/core/foo.py", extra))
        self.assertTrue(is_test_path("./sympy/core/foo.py", extra))
        self.assertFalse(is_test_path("sympy/core/bar.py", extra))
        self.assertFalse(is_test_path("sympy/core/bar.py"))


if __name__ == "__main__":
    unittest.main()
