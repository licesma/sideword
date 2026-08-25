# Admission check — 30 instances × 3 arms

Every instance in `corpus/instances.json`, every arm, scored twice with no model
involved: once against the arm's own gold patch (must resolve) and once against an
empty patch (must not). An arm that gets either answer wrong cannot tell a solved
instance from an unsolved one and must not be run with a model.

```sh
uv run --extra eval python -m harness.evaluate \
    --instance <id> --arm <orig|sw|nc> --model admission --score-only <gold|empty>
```

180 runs, 3 at a time, on emulated x86_64 images. Zero model calls. Machine-readable
form in `corpus/admission.json`.

## Summary

| | |
|---|---:|
| instances | 30 |
| instance × arm pairs | 90 |
| pairs that discriminate | 72 |
| pairs that do not | 18 |
| **instances usable for a three-arm run** | **22** |
| instances excluded | 8 |
| of those, failing in arm 1 as well | 2 |

Every one of the twelve instances checked previously reproduced exactly: the same
seven clean, the same four broken in arms 2 and 3 only, and `django__django-7530`
broken in all three.

## Usable instances

All three arms score gold resolved and empty unresolved. These are the 22 the
experiment can actually use.

- `django__django-14631`
- `django__django-14787`
- `matplotlib__matplotlib-14623`
- `matplotlib__matplotlib-23299`
- `matplotlib__matplotlib-24970`
- `matplotlib__matplotlib-25311`
- `pallets__flask-5014`
- `psf__requests-2931`
- `pydata__xarray-4356`
- `pydata__xarray-7229`
- `pytest-dev__pytest-5262`
- `scikit-learn__scikit-learn-10297`
- `scikit-learn__scikit-learn-13142`
- `scikit-learn__scikit-learn-15100`
- `scikit-learn__scikit-learn-25102`
- `sphinx-doc__sphinx-11445`
- `sphinx-doc__sphinx-8475`
- `sympy__sympy-13551`
- `sympy__sympy-16597`
- `sympy__sympy-20916`
- `sympy__sympy-22714`
- `sympy__sympy-23824`

## Excluded instances

| instance | arms lost | mechanism |
|---|---|---|
| `astropy__astropy-13398` | 2 sw, 3 nc | reads its own docstrings |
| `astropy__astropy-14365` | 2 sw, 3 nc | reads its own docstrings |
| `astropy__astropy-14598` | 2 sw, 3 nc | reads its own docstrings |
| `astropy__astropy-7336` | 1 orig, 2 sw, 3 nc | harness: submodule gitlink |
| `django__django-7530` | 1 orig, 2 sw, 3 nc | empty patch resolves |
| `mwaskom__seaborn-3069` | 2 sw, 3 nc | reads its own docstrings |
| `pylint-dev__pylint-6528` | 2 sw, 3 nc | lints itself |
| `pytest-dev__pytest-10051` | 2 sw, 3 nc | docstring is config |

## Failure mechanisms, grouped

### Repositories that read their own docstrings at runtime — 4 instances, arms 2 and 3

The stripped tree does not import. Nothing installs wrong; the failure is at
collection time, and no test on either list ever runs.

**`astropy__astropy-13398`** — astropy/io/ascii/core.py:1181,1189 `func.__doc__ += inspect.cleandoc(cls.__doc__).strip()`. Stripped, cls.__doc__ is None -> AttributeError: 'NoneType' object has no attribute 'expandtabs', raised while astropy/conftest.py::pytest_configure imports astropy.io.ascii. pytest INTERNALERROR; 0 of 4 F2P and 0 of 68 P2P run.

**`astropy__astropy-14365`** — astropy/io/ascii/core.py:1233,1246, same `func.__doc__ += inspect.cleandoc(cls.__doc__)`. pytest INTERNALERROR at configure; 0 of 1 F2P and 0 of 8 P2P run.

**`astropy__astropy-14598`** — astropy/io/ascii/core.py:1233,1246, same pattern. pytest INTERNALERROR at configure; 0 of 1 F2P and 0 of 175 P2P run.

**`mwaskom__seaborn-3069`** — seaborn/relational.py:178 `DocstringComponents.from_function_params(EstimateAggregator.__init__)` routes through seaborn/_docstrings.py:41-49 `pydoc.getdoc(func)` parsed by NumpyDocString. Stripped, the entries dict is empty and seaborn/relational.py:576 (`lineplot.__doc__ = """...{params.stat.errorbar}..."""`) raises AttributeError: 'DocstringComponents' object has no attribute 'errorbar' at `import seaborn`. Collection error; 0 of 2 F2P and 0 of 94 P2P run.

The three astropy instances share one line; seaborn's is its own. Both are cases a
stripper could in principle be taught: the consuming expression names the object
whose docstring it needs, so the docstring that must survive is statically visible.

### A docstring that is executable configuration — 1 instance, arms 2 and 3

**`pytest-dev__pytest-10051`** — PYTEST_DONT_REWRITE appears in exactly one place in the repository: src/_pytest/pytester.py:3, inside the module docstring. src/_pytest/assertion/rewrite.py:759-760 `is_rewrite_disabled(docstring)` greps for that token; mark_rewrite (rewrite.py:213) then calls _warn_already_imported. Stripped, the opt-out is gone and pytest emits PytestAssertRewriteWarning: Module already imported so cannot be rewritten: _pytest.pytester. The repo sets filterwarnings = error, so this raises inside pytest_cmdline_parse and pytest never starts; 0 of 1 F2P and 0 of 15 P2P run.

The sharpest case in the corpus: prose the interpreter greps. Unlike the group
above there is no expression naming `pytester.__doc__` — the coupling is a string
literal in one file and a substring search in another, and no static rule short of
knowing the token would connect them.

### A repository that lints itself — 1 instance, arms 2 and 3

**`pylint-dev__pylint-6528`** — The suite runs pylint over pylint. All 4 F2P pass; the P2P test tests/test_self.py::TestRunTC::test_pkginfo fails because pylint on pylint/__pkginfo__.py emits C0114 missing-module-docstring and C0116 missing-function-docstring, exit 16 instead of 0. (The two test_generate_toml_config failures in the same log are pre-existing tomlkit breakage: they fail in arm 1 too and are on neither list.)

Not recoverable by keeping selected docstrings: the check is that *every* module and
function has one.

### An instance that cannot discriminate — 1 instance, all three arms

**`django__django-7530`** — The empty patch scores resolved: 1/1 F2P and 59/59 P2P pass with no change applied. Reproduces under stock SWE-bench in an untouched image; nothing to do with stripping.

### A corpus or harness problem — 1 instance, all three arms

**`astropy__astropy-7336`** — materialize() aborts: `git ls-files -z | xargs -0 -r rm -f` hits the `astropy_helpers` submodule (mode 160000) and `rm -f` refuses a directory. Nothing installs, no test runs. The only instance of the 30 with a gitlink.

This one is flagged separately and loudly: **it fails in arm 1**, so it is not a
statement about stripping. It is the only instance of the 30 whose tree contains a
gitlink, and it never reaches `pip install` or a test in any arm. Whether its arms 2
and 3 would otherwise pass is unknown — astropy 1.3's `io/ascii/core.py` does *not*
carry the `inspect.cleandoc(cls.__doc__)` line that disqualifies the 5.x instances.
Fixing the harness would recover up to three arms; it is reported, not fixed.

## A near miss worth recording

`sympy__sympy-13551` and `sympy__sympy-16597` **fail to install** in arms 2 and 3 and
are still admissible.

```python
# setup.py:347 (13551) / setup.py:382 (16597)
with open(os.path.join(dir_setup, 'sympy', '__init__.py')) as f:
    long_description = f.read().split('"""')[1]
```

The build reads a source file as text and lifts the module docstring out by splitting
on triple quotes. Stripped there are none, so `[1]` is an `IndexError`, `egg_info`
exits 1 and `pip install -e .` fails. It does not change any verdict — the image's
editable install already points at `/testbed` and sympy's `bin/test` imports from the
source tree — and gold and empty both score exactly as they do in arm 1. Later sympy
dropped the line, which is why 20916, 22714 and 23824 install cleanly.

It belongs in the same family as pytest's `PYTEST_DONT_REWRITE`: documentation read
back as data, this time by the packaging system rather than the runtime.

A second instance of the pattern is present and *not* fatal. astropy's unit parser is
PLY, whose lexer regexes and grammar productions live in function docstrings
(`astropy/units/format/generic.py`, `t_UFLOAT`, `p_main`), and the stripper removed
them. It does not break because astropy checks the generated tables
(`generic_lextab.py`, `generic_parsetab.py`) into the repository; verified by parsing
`erg / (s cm2 Angstrom)` inside a landed `-nc` tree.

## Every row

`gold` must read *resolved* and `empty` must read *unresolved*; a wrong answer is
bold. `install` is whether the arm's tree installed cleanly in the scoring container
during the gold run.

| instance | arm | gold | empty | install | F2P (gold) | P2P (gold) | mechanism |
|---|---|---|---|---|---|---|---|
| `astropy__astropy-7336` | 1 orig | — | — | — | 0/0 | 0/0 | harness: submodule gitlink |
| `astropy__astropy-7336` | 2 sw | — | — | — | 0/0 | 0/0 | harness: submodule gitlink |
| `astropy__astropy-7336` | 3 nc | — | — | — | 0/0 | 0/0 | harness: submodule gitlink |
| `astropy__astropy-13398` | 1 orig | resolved | unresolved | yes | 4/4 | 68/68 |  |
| `astropy__astropy-13398` | 2 sw | **unresolved** | unresolved | yes | 0/4 | 0/68 | reads its own docstrings |
| `astropy__astropy-13398` | 3 nc | **unresolved** | unresolved | yes | 0/4 | 0/68 | reads its own docstrings |
| `astropy__astropy-14365` | 1 orig | resolved | unresolved | yes | 1/1 | 8/8 |  |
| `astropy__astropy-14365` | 2 sw | **unresolved** | unresolved | yes | 0/1 | 0/8 | reads its own docstrings |
| `astropy__astropy-14365` | 3 nc | **unresolved** | unresolved | yes | 0/1 | 0/8 | reads its own docstrings |
| `astropy__astropy-14598` | 1 orig | resolved | unresolved | yes | 1/1 | 175/175 |  |
| `astropy__astropy-14598` | 2 sw | **unresolved** | unresolved | yes | 0/1 | 0/175 | reads its own docstrings |
| `astropy__astropy-14598` | 3 nc | **unresolved** | unresolved | yes | 0/1 | 0/175 | reads its own docstrings |
| `django__django-7530` | 1 orig | resolved | **resolved** | yes | 1/1 | 59/59 | empty patch resolves |
| `django__django-7530` | 2 sw | resolved | **resolved** | yes | 1/1 | 59/59 | empty patch resolves |
| `django__django-7530` | 3 nc | resolved | **resolved** | yes | 1/1 | 59/59 | empty patch resolves |
| `django__django-14631` | 1 orig | resolved | unresolved | yes | 2/2 | 117/117 |  |
| `django__django-14631` | 2 sw | resolved | unresolved | yes | 2/2 | 117/117 |  |
| `django__django-14631` | 3 nc | resolved | unresolved | yes | 2/2 | 117/117 |  |
| `django__django-14787` | 1 orig | resolved | unresolved | yes | 1/1 | 20/20 |  |
| `django__django-14787` | 2 sw | resolved | unresolved | yes | 1/1 | 20/20 |  |
| `django__django-14787` | 3 nc | resolved | unresolved | yes | 1/1 | 20/20 |  |
| `matplotlib__matplotlib-14623` | 1 orig | resolved | unresolved | yes | 1/1 | 400/400 |  |
| `matplotlib__matplotlib-14623` | 2 sw | resolved | unresolved | yes | 1/1 | 400/400 |  |
| `matplotlib__matplotlib-14623` | 3 nc | resolved | unresolved | yes | 1/1 | 400/400 |  |
| `matplotlib__matplotlib-23299` | 1 orig | resolved | unresolved | yes | 1/1 | 192/192 |  |
| `matplotlib__matplotlib-23299` | 2 sw | resolved | unresolved | yes | 1/1 | 192/192 |  |
| `matplotlib__matplotlib-23299` | 3 nc | resolved | unresolved | yes | 1/1 | 192/192 |  |
| `matplotlib__matplotlib-24970` | 1 orig | resolved | unresolved | yes | 1/1 | 253/253 |  |
| `matplotlib__matplotlib-24970` | 2 sw | resolved | unresolved | yes | 1/1 | 253/253 |  |
| `matplotlib__matplotlib-24970` | 3 nc | resolved | unresolved | yes | 1/1 | 253/253 |  |
| `matplotlib__matplotlib-25311` | 1 orig | resolved | unresolved | yes | 1/1 | 181/181 |  |
| `matplotlib__matplotlib-25311` | 2 sw | resolved | unresolved | yes | 1/1 | 181/181 |  |
| `matplotlib__matplotlib-25311` | 3 nc | resolved | unresolved | yes | 1/1 | 181/181 |  |
| `mwaskom__seaborn-3069` | 1 orig | resolved | unresolved | yes | 2/2 | 94/94 |  |
| `mwaskom__seaborn-3069` | 2 sw | **unresolved** | unresolved | yes | 0/2 | 0/94 | reads its own docstrings |
| `mwaskom__seaborn-3069` | 3 nc | **unresolved** | unresolved | yes | 0/2 | 0/94 | reads its own docstrings |
| `pallets__flask-5014` | 1 orig | resolved | unresolved | yes | 1/1 | 59/59 |  |
| `pallets__flask-5014` | 2 sw | resolved | unresolved | yes | 1/1 | 59/59 |  |
| `pallets__flask-5014` | 3 nc | resolved | unresolved | yes | 1/1 | 59/59 |  |
| `psf__requests-2931` | 1 orig | resolved | unresolved | yes | 1/1 | 84/84 |  |
| `psf__requests-2931` | 2 sw | resolved | unresolved | yes | 1/1 | 84/84 |  |
| `psf__requests-2931` | 3 nc | resolved | unresolved | yes | 1/1 | 84/84 |  |
| `pydata__xarray-4356` | 1 orig | resolved | unresolved | yes | 8/8 | 604/604 |  |
| `pydata__xarray-4356` | 2 sw | resolved | unresolved | yes | 8/8 | 604/604 |  |
| `pydata__xarray-4356` | 3 nc | resolved | unresolved | yes | 8/8 | 604/604 |  |
| `pydata__xarray-7229` | 1 orig | resolved | unresolved | yes | 1/1 | 280/280 |  |
| `pydata__xarray-7229` | 2 sw | resolved | unresolved | yes | 1/1 | 280/280 |  |
| `pydata__xarray-7229` | 3 nc | resolved | unresolved | yes | 1/1 | 280/280 |  |
| `pylint-dev__pylint-6528` | 1 orig | resolved | unresolved | yes | 4/4 | 171/171 |  |
| `pylint-dev__pylint-6528` | 2 sw | **unresolved** | unresolved | yes | 4/4 | 170/171 | lints itself |
| `pylint-dev__pylint-6528` | 3 nc | **unresolved** | unresolved | yes | 4/4 | 170/171 | lints itself |
| `pytest-dev__pytest-5262` | 1 orig | resolved | unresolved | yes | 1/1 | 108/108 |  |
| `pytest-dev__pytest-5262` | 2 sw | resolved | unresolved | yes | 1/1 | 108/108 |  |
| `pytest-dev__pytest-5262` | 3 nc | resolved | unresolved | yes | 1/1 | 108/108 |  |
| `pytest-dev__pytest-10051` | 1 orig | resolved | unresolved | yes | 1/1 | 15/15 |  |
| `pytest-dev__pytest-10051` | 2 sw | **unresolved** | unresolved | yes | 0/1 | 0/15 | docstring is config |
| `pytest-dev__pytest-10051` | 3 nc | **unresolved** | unresolved | yes | 0/1 | 0/15 | docstring is config |
| `scikit-learn__scikit-learn-10297` | 1 orig | resolved | unresolved | yes | 1/1 | 28/28 |  |
| `scikit-learn__scikit-learn-10297` | 2 sw | resolved | unresolved | yes | 1/1 | 28/28 |  |
| `scikit-learn__scikit-learn-10297` | 3 nc | resolved | unresolved | yes | 1/1 | 28/28 |  |
| `scikit-learn__scikit-learn-13142` | 1 orig | resolved | unresolved | yes | 2/2 | 54/54 |  |
| `scikit-learn__scikit-learn-13142` | 2 sw | resolved | unresolved | yes | 2/2 | 54/54 |  |
| `scikit-learn__scikit-learn-13142` | 3 nc | resolved | unresolved | yes | 2/2 | 54/54 |  |
| `scikit-learn__scikit-learn-15100` | 1 orig | resolved | unresolved | yes | 1/1 | 93/93 |  |
| `scikit-learn__scikit-learn-15100` | 2 sw | resolved | unresolved | yes | 1/1 | 93/93 |  |
| `scikit-learn__scikit-learn-15100` | 3 nc | resolved | unresolved | yes | 1/1 | 93/93 |  |
| `scikit-learn__scikit-learn-25102` | 1 orig | resolved | unresolved | yes | 2/2 | 59/59 |  |
| `scikit-learn__scikit-learn-25102` | 2 sw | resolved | unresolved | yes | 2/2 | 59/59 |  |
| `scikit-learn__scikit-learn-25102` | 3 nc | resolved | unresolved | yes | 2/2 | 59/59 |  |
| `sphinx-doc__sphinx-8475` | 1 orig | resolved | unresolved | yes | 1/1 | 17/17 |  |
| `sphinx-doc__sphinx-8475` | 2 sw | resolved | unresolved | yes | 1/1 | 17/17 |  |
| `sphinx-doc__sphinx-8475` | 3 nc | resolved | unresolved | yes | 1/1 | 17/17 |  |
| `sphinx-doc__sphinx-11445` | 1 orig | resolved | unresolved | yes | 2/2 | 8/8 |  |
| `sphinx-doc__sphinx-11445` | 2 sw | resolved | unresolved | yes | 2/2 | 8/8 |  |
| `sphinx-doc__sphinx-11445` | 3 nc | resolved | unresolved | yes | 2/2 | 8/8 |  |
| `sympy__sympy-13551` | 1 orig | resolved | unresolved | yes | 1/1 | 17/17 |  |
| `sympy__sympy-13551` | 2 sw | resolved | unresolved | **no** | 1/1 | 17/17 | _install fails, verdicts unaffected_ |
| `sympy__sympy-13551` | 3 nc | resolved | unresolved | **no** | 1/1 | 17/17 | _install fails, verdicts unaffected_ |
| `sympy__sympy-16597` | 1 orig | resolved | unresolved | yes | 3/3 | 74/74 |  |
| `sympy__sympy-16597` | 2 sw | resolved | unresolved | **no** | 3/3 | 74/74 | _install fails, verdicts unaffected_ |
| `sympy__sympy-16597` | 3 nc | resolved | unresolved | **no** | 3/3 | 74/74 | _install fails, verdicts unaffected_ |
| `sympy__sympy-20916` | 1 orig | resolved | unresolved | yes | 1/1 | 1/1 |  |
| `sympy__sympy-20916` | 2 sw | resolved | unresolved | yes | 1/1 | 1/1 |  |
| `sympy__sympy-20916` | 3 nc | resolved | unresolved | yes | 1/1 | 1/1 |  |
| `sympy__sympy-22714` | 1 orig | resolved | unresolved | yes | 1/1 | 11/11 |  |
| `sympy__sympy-22714` | 2 sw | resolved | unresolved | yes | 1/1 | 11/11 |  |
| `sympy__sympy-22714` | 3 nc | resolved | unresolved | yes | 1/1 | 11/11 |  |
| `sympy__sympy-23824` | 1 orig | resolved | unresolved | yes | 1/1 | 2/2 |  |
| `sympy__sympy-23824` | 2 sw | resolved | unresolved | yes | 1/1 | 2/2 |  |
| `sympy__sympy-23824` | 3 nc | resolved | unresolved | yes | 1/1 | 2/2 |  |
