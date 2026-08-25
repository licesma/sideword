"""Tests for harness/docuse.py: the consumption analysis behind the ``consumed`` rule.

Every case is a small tree, ``{path: source}``, shaped after something in the corpus:
astropy's metaclass reading ``cls.__doc__`` over every reader class, seaborn's
``pydoc.getdoc(func)`` fed through a classmethod, matplotlib's guarded reads that must
*not* keep anything.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness import directives, docuse  # noqa: E402

D = directives.load()


def analyze(tree: dict) -> docuse.Result:
    return docuse.analyze({p: s.encode() for p, s in tree.items()}, D)


class TestModuleNames(unittest.TestCase):
    def test_layouts(self):
        self.assertEqual(docuse.module_name("seaborn/_statistics.py"), "seaborn._statistics")
        self.assertEqual(docuse.module_name("astropy/io/ascii/__init__.py"), "astropy.io.ascii")
        self.assertEqual(docuse.module_name("src/_pytest/pytester.py"), "_pytest.pytester")
        self.assertEqual(docuse.module_name("lib/matplotlib/axes/_base.py"), "matplotlib.axes._base")
        self.assertEqual(docuse.module_name("setup.py"), "setup")


class TestDirectTargets(unittest.TestCase):
    def test_getdoc_of_an_imported_class_method(self):
        r = analyze({
            "pkg/__init__.py": "",
            "pkg/a.py": "import pydoc\nfrom .b import Thing\n\nDOC = pydoc.getdoc(Thing.__init__)\n",
            "pkg/b.py": 'class Thing:\n    """T"""\n    def __init__(self):\n        """init"""\n',
        })
        self.assertEqual(r.keep, {"pkg/b.py": {"Thing.__init__": "consumed"}})
        self.assertEqual(r.keep_owners("pkg/b.py"), [("Thing\\.__init__", "consumed")])
        self.assertEqual(r.keep_owners("pkg/a.py"), [])
        self.assertEqual(docuse.summarize(r)["resolved"], 1)

    def test_inherited_method_walks_up_the_tree(self):
        r = analyze({
            "p/__init__.py": "",
            "p/base.py": 'class Base:\n    def run(self):\n        """run"""\n',
            "p/sub.py": "from p.base import Base\n\nclass Sub(Base):\n    pass\n",
            "p/use.py": "import inspect\nfrom p.sub import Sub\nx = inspect.cleandoc(Sub.run.__doc__)\n",
        })
        self.assertEqual(r.keep, {"p/base.py": {"Base.run": "consumed"}})

    def test_the_module_reads_its_own_docstring(self):
        r = analyze({"m.py": '"""Hello {x}"""\n\n__doc__ = __doc__.format(x=1)\n'})
        self.assertEqual(r.keep, {"m.py": {"<module>": "consumed"}})

    def test_owners_without_a_docstring_are_not_named(self):
        r = analyze({"m.py": "import inspect\n\ndef f():\n    pass\n\nx = inspect.getdoc(f)\n"})
        self.assertEqual(r.keep, {})
        self.assertEqual(r.sites[0]["kept"], [])

    def test_only_the_configured_getdoc_functions_count(self):
        r = analyze({"m.py": 'from foo import getdoc\n\ndef f():\n    """d"""\n\nx = getdoc(f)\n'})
        self.assertEqual(r.keep, {})
        r = analyze({"m.py": 'from inspect import getdoc\n\ndef f():\n    """d"""\n\nx = getdoc(f)\n'})
        self.assertEqual(r.keep, {"m.py": {"f": "consumed"}})


class TestParameters(unittest.TestCase):
    SEABORN = {
        "sb/__init__.py": "",
        "sb/_docstrings.py": (
            "import pydoc\n\nclass Components:\n    @classmethod\n"
            "    def from_function_params(cls, func):\n"
            "        params = parse(pydoc.getdoc(func))\n        return cls(params)\n"),
        "sb/_statistics.py": (
            'class Agg:\n    """Agg"""\n    def __init__(self, estimator, errorbar=None):\n'
            '        """Parameters\n        ----------\n        errorbar : ...\n        """\n'
            'class Other:\n    def __init__(self):\n        """other"""\n'),
        "sb/relational.py": (
            "from ._docstrings import Components\nfrom ._statistics import Agg\n\n"
            "_docs = Components.from_function_params(Agg.__init__)\n"),
    }

    def test_classmethod_argument_follows_the_parameter(self):
        r = analyze(self.SEABORN)
        self.assertEqual(r.keep, {"sb/_statistics.py": {"Agg.__init__": "consumed"}})

    def test_decorator_application_is_a_call(self):
        r = analyze({
            "m.py": ('def document(func):\n    lines = func.__doc__.split("\\n")\n    return func\n\n'
                     '@document\ndef f():\n    """f"""\n\n@document\nclass K:\n    """K"""\n\n'
                     'def g():\n    """g"""\n'),
        })
        self.assertEqual(r.keep, {"m.py": {"f": "consumed", "K": "consumed"}})

    def test_a_parameter_nobody_calls_is_reported_unresolved(self):
        r = analyze({"m.py": "import inspect\n\ndef doc_of(obj):\n    return inspect.getdoc(obj).strip()\n"})
        self.assertEqual(r.keep, {})
        self.assertEqual(len(r.sites), 1)
        self.assertIn("no in-tree call found", r.sites[0]["unresolved"][0])
        self.assertEqual(docuse.summarize(r)["unresolved"], 1)


class TestClassSets(unittest.TestCase):
    ASTROPY = {
        "io/__init__.py": "",
        "io/core.py": (
            "import inspect\n\nclass MetaBaseReader(type):\n"
            "    def __init__(cls, name, bases, dct):\n        super().__init__(name, bases, dct)\n"
            "        if dct.get('_format_name') is None:\n            return\n"
            "        func = make()\n        func.__doc__ += inspect.cleandoc(cls.__doc__).strip()\n\n"
            'class BaseReader(metaclass=MetaBaseReader):\n    """Base"""\n'),
        "io/basic.py": (
            'from . import core\n\nclass Basic(core.BaseReader):\n    """Basic"""\n    _format_name = "basic"\n\n'
            'class Csv(Basic):\n    """Csv"""\n\nclass Helper:\n    """not a reader"""\n'),
        "io/fast.py": 'from .basic import Basic\n\nclass FastBasic(Basic):\n    """Fast"""\n',
    }

    def test_metaclass_keeps_every_class_it_builds(self):
        r = analyze(self.ASTROPY)
        self.assertEqual(r.keep, {
            "io/core.py": {"BaseReader": "consumed"},
            "io/basic.py": {"Basic": "consumed", "Csv": "consumed"},
            "io/fast.py": {"FastBasic": "consumed"},
        })

    def test_self_keeps_the_class_and_its_subclasses(self):
        r = analyze({
            "m.py": ('class K:\n    """K"""\n    def describe(self):\n        return self.__doc__.strip()\n\n'
                     'class S(K):\n    """S"""\n\nclass T:\n    """T"""\n'),
        })
        self.assertEqual(r.keep, {"m.py": {"K": "consumed", "S": "consumed"}})

    def test_init_subclass_keeps_the_subclasses_only(self):
        r = analyze({
            "m.py": ('class Plugin:\n    """P"""\n    def __init_subclass__(cls, **kw):\n'
                     '        REG[cls.__doc__.splitlines()[0]] = cls\n\n'
                     'class A(Plugin):\n    """A"""\n\nclass B(A):\n    """B"""\n'),
        })
        self.assertEqual(r.keep, {"m.py": {"A": "consumed", "B": "consumed"}})

    def test_self_attribute_resolves_the_method_on_each_class(self):
        r = analyze({
            "m.py": ('class K:\n    def m(self):\n        """Km"""\n    def show(self):\n'
                     '        return self.m.__doc__.upper()\n\nclass S(K):\n    def m(self):\n        """Sm"""\n'),
        })
        self.assertEqual(r.keep, {"m.py": {"K.m": "consumed", "S.m": "consumed"}})


class TestTolerance(unittest.TestCase):
    def check_nothing_kept(self, body: str):
        src = 'def f():\n    """f"""\n\n' + body
        r = analyze({"m.py": src})
        self.assertEqual(r.keep, {}, src)
        self.assertTrue(all(s.get("tolerant") for s in r.sites), r.sites)

    def test_copies_tests_and_guards(self):
        self.check_nothing_kept("g.__doc__ = f.__doc__\n")
        self.check_nothing_kept("if f.__doc__:\n    f.__doc__ = f.__doc__.format(x=1)\n")
        self.check_nothing_kept("if f.__doc__ is not None:\n    x = f.__doc__.strip()\n")
        self.check_nothing_kept("if f.__doc__ is None:\n    pass\nelse:\n    x = f.__doc__.strip()\n")
        self.check_nothing_kept("x = f.__doc__ or ''\n")
        self.check_nothing_kept("x = not f.__doc__\n")
        self.check_nothing_kept("try:\n    x = f.__doc__.strip()\nexcept AttributeError:\n    x = ''\n")
        self.check_nothing_kept("import inspect\nf.__doc__ = inspect.getdoc(f)\n")

    def test_an_unguarded_read_is_a_site(self):
        r = analyze({"m.py": 'def f():\n    """f"""\n\nx = f.__doc__.strip()\n'})
        self.assertEqual(r.keep, {"m.py": {"f": "consumed"}})
        r = analyze({"m.py": 'def f():\n    """f"""\n\nif f.__doc__ is None:\n    x = f.__doc__.strip()\n'})
        self.assertEqual(r.keep, {"m.py": {"f": "consumed"}})


class TestUnresolved(unittest.TestCase):
    def test_dynamic_targets_are_reported_not_guessed(self):
        r = analyze({"m.py": ('def f():\n    """f"""\n\nfor item in things:\n    x = item.__doc__.strip()\n'
                              'y = type(f).__doc__.strip()\n')})
        self.assertEqual(r.keep, {})
        self.assertEqual([s["unresolved"][0] for s in r.sites],
                         ["loop variable item", "call result (type(...))"])

    def test_disabled_analysis_keeps_nothing(self):
        off = directives.loads("[consumption]\nenabled=false\n")
        r = docuse.analyze({"m.py": b'def f():\n    """f"""\n\nx = f.__doc__.strip()\n'}, off)
        self.assertEqual(r.keep, {})
        self.assertEqual(r.sites, [])

    def test_a_module_that_does_not_parse_is_reported(self):
        r = analyze({"m.py": "def f(:\n    x = f.__doc__\n"})
        self.assertEqual(r.parse_failures, ["m.py"])
        self.assertEqual(docuse.summarize(r)["parse_failures"], 1)


if __name__ == "__main__":
    unittest.main()
