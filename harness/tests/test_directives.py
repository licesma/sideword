import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness import directives  # noqa: E402

D = directives.load()


class TestCorpusDirectives(unittest.TestCase):
    """Pins the behaviour of the checked-in corpus/directives.toml (EST-106 final list)."""

    def test_load(self):
        self.assertEqual(D.version, 2)
        self.assertGreaterEqual(len(D.keep), 25)
        self.assertGreaterEqual(len(D.human), 17)
        self.assertGreaterEqual(len(D.watch), 4)

    def test_keep_rules(self):
        cases = {
            ("#!/usr/bin/env python", 1): ("keep", "shebang"),
            ("#!/usr/bin/env python", 2): ("unresolved", "shebang-off-line-1"),
            ("# -*- coding: utf-8 -*-", 1): ("keep", "coding"),
            ("# -*- coding: utf-8 -*-", 2): ("keep", "coding"),
            ("# -*- coding: utf-8 -*-", 3): ("unresolved", "coding-declaration-off-line-1-2"),
            ("# coding: utf-8", 3): ("unresolved", "colon-token-lower"),
            ("# -*- mode: python -*-", 2): ("keep", "emacs-modeline"),
            ("# vim: set fileencoding=utf-8 :", 1): ("keep", "coding"),
            ("# type: ignore", 7): ("keep", "type-comment"),
            ("#type: List[int]", 7): ("keep", "type-comment"),
            ("# NOQA", 7): ("keep", "noqa"),
            ("# some text ... noqa:E501", 7): ("keep", "noqa"),
            ("# pragma: no cover", 7): ("keep", "pragma"),
            ("# x  # pragma: no cover", 7): ("keep", "pragma"),
            ("# #pragma: NO COVER", 7): ("keep", "pragma"),
            ("# fmt: off", 7): ("keep", "fmt"),
            ("# isort:skip", 7): ("keep", "isort"),
            ("# pylint: disable=foo", 7): ("keep", "pylint"),
            ("# flake8: noqa", 7): ("keep", "noqa"),  # noqa entry precedes flake8
            ("# nosec", 7): ("keep", "nosec"),
            ("# mypy: ignore-errors", 7): ("keep", "mypy"),
            ("# pyright: basic", 7): ("keep", "pyright"),
            ("# ruff: noqa", 7): ("keep", "noqa"),  # keep order: noqa entry precedes ruff
            ("# %%", 3): ("keep", "cell-marker"),
            ("# Translators: keep this", 3): ("keep", "translators"),
            ("# just prose", 7): ("remove", None),
            ("# mypy is unhappy", 7): ("human", "mypy-prose"),
            ("# Black square", 7): ("human", "black-prose"),
            ("# PyLint", 7): ("human", "pylint-prose"),
            ("# see coverage docs", 7): ("human", "coverage-prose"),
            ("# region: foo", 7): ("unresolved", "colon-token-lower"),
            ("# pytype: disable=x", 7): ("unresolved", "tool-words"),
            ("#", 7): ("remove", None),
        }
        for (text, line), want in cases.items():
            with self.subTest(text=text, line=line):
                self.assertEqual(D.classify(text, line), want)


class TestCorpusDocstringTiers(unittest.TestCase):
    """The three docstring tiers of the checked-in file."""

    def test_general_tier(self):
        self.assertEqual([r.name for r in D.docstrings], ["pytest-dont-rewrite", "ply-grammar"])
        c = D.classify_docstring
        self.assertEqual(c("Config. PYTEST_DONT_REWRITE", "<module>", "x = 1\n"), "pytest-dont-rewrite")
        self.assertIsNone(c("Config. pytest_dont_rewrite", "<module>", "x = 1\n"))
        ply = "from astropy.extern.ply import lex, yacc\n"
        self.assertEqual(c("[0-9]+", "Parser._make_lexer.t_UINT", ply), "ply-grammar")
        self.assertEqual(c("main : UINT", "p_main", "x = parsing.yacc(tabmodule='t')\n"), "ply-grammar")
        self.assertEqual(c("x", "t_A", "import ply.lex\n"), "ply-grammar")
        self.assertIsNone(c("[0-9]+", "t_UINT", "import numpy\n"))
        self.assertIsNone(c("[0-9]+", "Parser.make_lexer", ply))
        self.assertIsNone(c("[0-9]+", "not_t_UINT", ply))
        self.assertIsNone(c("x", "p_value", "def p_value():\n    pass\n"))

    def test_consumption_config(self):
        self.assertEqual(D.consumption, {"enabled": True, "getdoc": ["inspect.getdoc", "pydoc.getdoc"]})

    def test_per_repo_tier_is_the_one_disclosed_deviation(self):
        self.assertEqual(sorted(D.repos), ["pylint-dev/pylint"])
        rules = D.repo_docstring_rules("pylint-dev/pylint", "pylint/__pkginfo__.py")
        self.assertEqual([(r.name, r.owner) for r in rules], [("pylint-self-lint", None)])
        self.assertEqual(D.repo_docstring_rules("pylint-dev/pylint", "pylint/lint/run.py"), [])
        self.assertEqual(D.repo_docstring_rules("pytest-dev/pytest", "pylint/__pkginfo__.py"), [])
        self.assertEqual(D.repo_docstring_rules(None, "pylint/__pkginfo__.py"), [])


class TestDocstringSchema(unittest.TestCase):
    def test_fields_and_first_match(self):
        d = directives.loads(
            '[[docstrings]]\nname="a"\npattern="TOKEN"\n'
            "[[docstrings]]\nname='b'\nowner='(.*\\.)?t_\\w+'\nmodule='import ply'\n"
            '[[docstrings]]\nname="c"\npattern="^x"\nkind="regex"\nowner="<module>"\n'
            '[[docstrings]]\nname="d"\npattern="pre"\nkind="prefix"\nignore_case=true\n')
        c = d.classify_docstring
        self.assertEqual(c("a TOKEN b", "f", ""), "a")
        self.assertEqual(c("TOKEN", "t_x", "import ply"), "a")          # first match wins
        self.assertEqual(c("re", "C.t_x", "import ply\n"), "b")
        self.assertIsNone(c("re", "C.t_x", "import re\n"))
        self.assertIsNone(c("re", "t_x", None))                          # module unknown
        self.assertEqual(c("xylophone", "<module>", ""), "c")
        self.assertIsNone(c("xylophone", "f", ""))
        self.assertEqual(c("  PREfix", "f", ""), "d")

    def test_schema_errors(self):
        with self.assertRaises(ValueError):
            directives.loads('[[docstrings]]\nname="empty"\n')
        with self.assertRaises(ValueError):
            directives.loads('[[docstrings]]\nname="k"\npattern="x"\nkind="glob"\n')
        with self.assertRaises(ValueError):
            directives.loads('[[repo]]\nrepo="noslash"\n')
        with self.assertRaises(ValueError):
            directives.loads('[[repo]]\nrepo="o/n"\n[[repo.docstrings]]\nname="x"\nowner="f"\n')
        with self.assertRaises(ValueError):
            directives.loads('[[repo]]\nrepo="o/n"\n[[repo.docstrings]]\nname="x"\npath="a"\npattern="p"\n')
        with self.assertRaises(ValueError):
            directives.loads('[[repo]]\nrepo="o/n"\n[[repo]]\nrepo="o/n"\n')
        with self.assertRaises(ValueError):
            directives.loads('[consumption]\ngetdoc="inspect.getdoc"\n')

    def test_repo_tier_paths_fullmatch(self):
        d = directives.loads('[[repo]]\nrepo="o/n"\n[[repo.docstrings]]\nname="x"\n'
                             "path='pkg/(a|b)\\.py'\nowner='f'\n")
        self.assertEqual([r.name for r in d.repo_docstring_rules("o/n", "pkg/a.py")], ["x"])
        self.assertEqual(d.repo_docstring_rules("o/n", "pkg/ab.py"), [])
        self.assertEqual(d.repo_docstring_rules("o/n", "x/pkg/a.py"), [])
        self.assertEqual(d.consumption["enabled"], True)
        off = directives.loads('[consumption]\nenabled=false\n')
        self.assertFalse(off.consumption["enabled"])


class TestSemantics(unittest.TestCase):
    def test_prefix_contains_regex_case(self):
        d = directives.loads(
            'version = 1\n'
            '[[keep]]\nname="p"\npattern="Foo:"\nkind="prefix"\n'
            '[[keep]]\nname="pi"\npattern="bar:"\nkind="prefix"\nignore_case=true\n'
            '[[keep]]\nname="c"\npattern="#x"\nkind="contains"\n'
            '[[keep]]\nname="r"\npattern="z{2}$"\nkind="regex"\nline="3-4"\n'
            '[[human]]\nname="h"\npattern="talks about"\nkind="contains"\n'
            '[[watch]]\nname="w"\npattern="tool"\nkind="regex"\n')
        c = d.classify
        self.assertEqual(c("#   Foo: 1", 1), ("keep", "p"))
        self.assertEqual(c("# foo: 1", 1), ("remove", None))
        self.assertEqual(c("# BAR: 1", 1), ("keep", "pi"))
        self.assertEqual(c("## x", 1), ("remove", None))
        self.assertEqual(c("# a #x b", 1), ("keep", "c"))
        self.assertEqual(c("# zz", 3), ("keep", "r"))
        self.assertEqual(c("# zz", 4), ("keep", "r"))
        self.assertEqual(c("# zz", 5), ("remove", None))
        self.assertEqual(c("# talks about the tool", 1), ("human", "h"))
        self.assertEqual(c("# the tool", 1), ("unresolved", "w"))
        # keep wins over human wins over watch
        self.assertEqual(c("# Foo: talks about the tool", 1), ("keep", "p"))

    def test_missing_sections_and_bad_kind(self):
        d = directives.loads("version = 1\n")
        self.assertEqual(d.classify("# anything", 1), ("remove", None))
        with self.assertRaises(ValueError):
            directives.loads('[[keep]]\nname="x"\npattern="y"\nkind="glob"\n')

    def test_line_spec_int(self):
        d = directives.loads('[[keep]]\nname="x"\npattern="!"\nkind="prefix"\nline=1\n')
        self.assertEqual(d.classify("#!x", 1), ("keep", "x"))
        self.assertEqual(d.classify("#!x", 2), ("remove", None))


if __name__ == "__main__":
    unittest.main()
