# Does `.sideword/` change what the repos' own test suites do?

**EST-163.** Arm 2 adds 66–1,766 files under `.sideword/` to each checkout; arm 3 does not.
If any repository's own test suite reacts to those files, arm 2 loses that instance and we would
misread it as "documentation did not help" when the real cause is "we added files."

**Verdict: arm 2 is safe to run as built. `.sideword/` does not need to move out of the checkout root.**

Zero of the 30 instances react. Twelve — one per repo family, chosen to include every instance
Stage 1 flagged — were verified by actually running their tests with and without `.sideword/`
present; all twelve produced byte-identical per-test outcomes. The remaining eighteen are covered
by the structural argument below plus the per-instance static scan.

---

## Why nothing can react: three structural facts

**1. `.sideword/` is the only difference, and it is a pure addition.**
`git diff --name-status <id>-nc <id>-sw` is 100% `A` for all 30 pairs (798 A for astropy-7336,
1766 A for sympy-22714, etc.).

**2. Every entry mirrors an existing `.py` file, and nothing inside is Python.**
Checked programmatically over all 30 `-sw` tags: **0 mismatches**. For every
`.sideword/<X>.md` and `.sideword/<X>.idx`, `<X>` exists in the tree and ends in `.py`.
The extension histogram is exactly `{.md: n, .idx: n}` — no `.py`, no `__init__.py`,
no `conftest.py`, no `test_*.py`, and no mirrors of non-Python files. `.sideword/` also
contains **no `tests/` subtree in any instance** (the converter skips test paths).

**3. The name is hostile to every discovery mechanism these repos use.**

| Mechanism | Why `.sideword/` is invisible to it |
|---|---|
| `setuptools.find_packages()` | `_find_packages_iter` skips any directory whose name contains `.` — verified live: `find_packages()` returns 24 (sphinx), 190 (django), 88 (sklearn) packages, none from `.sideword` |
| Python import | `.sideword` is not a valid identifier and is not on `sys.path`; its subdirs have no `__init__.py` |
| pytest directory recursion | default `norecursedirs` includes `.*`, which prunes hidden dirs. Overridden without `.*` by astropy, pytest-dev and sympy — see below, still inert |
| pytest file collection | `python_files` is `test_*.py` / `*_test.py` (or stricter) everywhere; `.md`/`.idx` match nothing |
| pytest doctest collection | default `--doctest-glob` is `test*.txt`; astropy sets `text_file_format = rst` + `--doctest-rst`; sklearn uses `--doctest-modules` (`.py` only). No repo globs `*.md` |
| sympy's own runner | `SymPyTests.get_test_files` filters `test_*.py`; `SymPyDocTests.get_test_files` filters `*.py` **and** requires a sibling `__init__.py` |
| django's own runner | `tests/runtests.py` scans `tests/` (not the checkout root) and skips any entry whose name contains `.` or lacks `__init__.py` |

Direct probes inside the eval images, pointing the collector *straight at* `.sideword/`:

```
# astropy-14598 (norecursedirs overridden, --doctest-rst, doctest_plus=enabled)
$ pytest --collect-only -q .sideword          -> no tests collected in 1.60s
$ pytest --collect-only -q .sideword/astropy  -> no tests collected in 1.25s

# scikit-learn-25102 (addopts includes --doctest-modules)
$ pytest --collect-only -q .sideword          -> no tests collected in 0.11s

# sympy-22714, walking with the repo's own runner, rooted at the checkout root:
SymPyTests.get_test_files("sympy")     -> 575 files, any ".sideword": False
SymPyDocTests.get_test_files("sympy")  -> 880 files, any ".sideword": False
SymPyDocTests.get_test_files(".")      -> 880 files, any ".sideword": False
```

---

## Per-instance table

`files` = number of files added under `.sideword/`. "Mechanism examined" names the closest thing
to a tree-walk that could execute during that instance's test run (test files named by
`PASS_TO_PASS`/`FAIL_TO_PASS`, every `conftest.py` in the repo, the repo's test runner, and its
packaging/lint config), and says whether the walk can actually reach `.sideword/`.

| Instance | files | At risk | Mechanism examined | Verified how |
|---|---|---|---|---|
| astropy__astropy-7336 | 798 | no | `setup.cfg [tool:pytest]` overrides `norecursedirs` without `.*` (`"docs[\/]_build" …`), `doctest_plus = enabled`. No walk in `test_quantity_decorator.py`, `astropy/conftest.py`, root `conftest.py`. Collection is scoped to the explicit test path; `.md`/`.idx` match no glob | static |
| astropy__astropy-13398 | 1006 | no | as above, plus `addopts = --doctest-rst` and `astropy/io/misc/asdf/conftest.py:7: paths = Path(asdf_dir).rglob("test_*.py")` — rooted at `astropy/io/misc/asdf`, cannot see a root-level `.sideword/`, and only loaded when collecting under that dir | static |
| astropy__astropy-14365 | 1020 | no | as 13398; `asdf/conftest.py:13: paths = Path(asdf_dir).rglob("*.py")` — same root, `*.py` filter excludes `.md`/`.idx` | static |
| astropy__astropy-14598 | 1018 | no | as 14365 (`--color=yes --doctest-rst`, `text_file_format = rst`); `astropy/io/fits/tests/conftest.py` has no walk | **dynamic**: 175 outcomes identical; `pytest --collect-only .sideword` → nothing |
| django__django-7530 | 1686 | no | `tests/runtests.py:94: for f in os.listdir(dirpath)` — `dirpath` is `RUNTESTS_DIR` (= `tests/`), and the body `continue`s on `'.' in f` and on missing `__init__.py`. `.sideword/` has no `tests/` subtree. `setup.py:36: packages=find_packages(exclude=…)`. `tox.ini:62 isort --recursive … django tests scripts` is not part of the eval command | **dynamic**: `Ran 63 tests … OK` both runs, output identical line-for-line |
| django__django-14631 | 1706 | no | `tests/runtests.py:131: with os.scandir(dirpath) as entries` — same `tests/` root and same `'.' in f.name` skip | static |
| django__django-14787 | 1708 | no | `tests/runtests.py:122: with os.scandir(dirpath) as entries` — identical | static |
| matplotlib__matplotlib-14623 | 1496 | no | `pytest.ini: testpaths = lib`, `python_files = test_*.py`; default `norecursedirs` prunes `.*`. `setupext.py:378 (base / subdir).rglob("*")` is rooted at `lib/matplotlib/mpl-data` and runs only at build time | static |
| matplotlib__matplotlib-23299 | 1540 | no | as above; `setup.py:246 packages=find_packages("lib")` | **dynamic**: 195 outcomes identical (2 pre-existing env failures on both sides) |
| matplotlib__matplotlib-24970 | 1554 | no | as above; `setup.py:234 long_description=Path("README.md").read_text(...)` is a fixed path, not a glob | static |
| matplotlib__matplotlib-25311 | 1538 | no | as above | static |
| mwaskom__seaborn-3069 | 222 | no | No walk in `tests/_core/test_plot.py` or `tests/conftest.py`; no pytest config. `ci/cache_datasets.py:7-8 path.rglob("*.py")` is CI-only, never invoked by the test command | **dynamic**: 173 outcomes identical (74 pre-gold-patch failures on both sides) |
| pallets__flask-5014 | 66 | no | `pyproject.toml: testpaths = ["tests"]`; nothing in `tests/test_blueprints.py` or `tests/conftest.py` enumerates files | **dynamic**: 59 passed both |
| psf__requests-2931 | 166 | no | No pytest config, no walk in `test_requests.py` | **dynamic**: 167 outcomes identical (see note on warning counts below) |
| pydata__xarray-4356 | 192 | no | `setup.cfg: python_files = test_*.py`, `testpaths = xarray/tests properties`; root `conftest.py` only fills `doctest_namespace` | static |
| pydata__xarray-7229 | 230 | no | as above, plus `xarray/tests/conftest.py` (no walk) | **dynamic**: 282 outcomes identical |
| pylint-dev__pylint-6528 | 810 | **flagged, cleared** | Highest a-priori risk: the fix *is* recursive file discovery. `tests/test_self.py:1254: self._runtest([".", "--recursive=y"], code=0)` — but it is wrapped in `_test_cwd()` after `os.chdir(join(HERE, "regrtest_data", "directory"))` (L1250), so `.` is a fixture dir, not the checkout root. `test_self.py:1436: for filename in os.listdir(os.path.dirname(extensions.__file__))` lists the installed `pylint/extensions/` package dir, `.py`-filtered. `tests/lint/unittest_lint.py` anchors every path on `REGRTEST_DATA_DIR`. `setup.cfg: testpaths = tests`, `python_files = *test_*.py` | **dynamic**: 169 outcomes, 0 differing (`2 failed, 166 passed, 1 xfailed` on both sides; the 2 failures are pre-existing `toml` env failures) |
| pytest-dev__pytest-5262 | 148 | no | `tox.ini [pytest]: norecursedirs = testing/example_scripts` overrides the default without `.*`, `python_files = test_*.py *_test.py testing/*/*.py`. `setup.cfg:65 [check-manifest]` exists but check-manifest is not in the eval command. `testing/test_capture.py` runs through the `testdir` fixture in a tmpdir | static |
| pytest-dev__pytest-10051 | 172 | no | as above (`pyproject.toml: norecursedirs = ["testing/example_scripts"]`, `python_files = [...]`, `[check-manifest]` at `setup.cfg:85`); `testing/logging/test_fixture.py` has no walk | **dynamic**: 19 outcomes identical |
| scikit-learn__scikit-learn-10297 | 992 | no | `setup.cfg addopts` includes `--doctest-modules` (collects `.py` only, and only from the explicit test path). `setup.py:71: for dirpath, dirnames, filenames in os.walk('sklearn')` — rooted at the package dir, build-time only | static |
| scikit-learn__scikit-learn-13142 | 1088 | no | as above (`setup.py:71`); root `conftest.py` only gates `DoctestItem`s on numpy version | static |
| scikit-learn__scikit-learn-15100 | 1068 | no | as above (`setup.py:81`), plus `sklearn/conftest.py` (no walk) | static |
| scikit-learn__scikit-learn-25102 | 1238 | no | as above (`setup.py:135`, `setup.cfg:80 [check-manifest]`, `testpaths = sklearn`) | **dynamic**: 59 passed both; `pytest --collect-only .sideword` → nothing; `find_packages()` → 88, none from `.sideword` |
| sphinx-doc__sphinx-8475 | 376 | no | `setup.cfg: testpaths = tests`; `tests/conftest.py:22: collect_ignore = ['roots']`. `setup.py:219 packages=find_packages(exclude=['tests','utils'])` and `setup.py:114 for locale in os.listdir(self.directory)` (the `compile_catalog` command, over `sphinx/locale`). `tox.ini` uses `usedevelop = True`, so no sdist is built | static |
| sphinx-doc__sphinx-11445 | 348 | no | `pyproject.toml: testpaths = ["tests"]`; `tests/conftest.py:28: collect_ignore = ['roots']`. The `images_dir.rglob('*')` set-comparisons in `test_build_epub/html/latex.py` are rooted in `tests/roots/**` and are not this instance's test file | **dynamic**: 7 passed both; `find_packages()` → 24, none from `.sideword` |
| sympy__sympy-13551 | 1350 | no | Eval runs `bin/test`, not pytest. `sympy/utilities/runtests.py:1047,1149: for path, folders, files in os.walk(dir)` — `dir` is `<root>/sympy`, filtered `test_*.py` (tests) or `*.py` + sibling `__init__.py` (doctests). `setup.py:163 os.walk(dir_setup)` walks the repo root but lives in the custom `clean` command; the package list at `setup.py` is hardcoded | static |
| sympy__sympy-16597 | 1504 | no | as above (`runtests.py:1082,1194`, `setup.py:172`); `pytest.ini` overrides `norecursedirs` without `.*` but sets `testpaths = sympy doc/src`; `conftest.py:18 collect_ignore = ["sympy/integrals/rubi"] + _get_doctest_blacklist()` is a literal list | static |
| sympy__sympy-20916 | 1690 | no | as above (`sympy/testing/runtests.py:1367,1515`, `setup.py:182`) | static |
| sympy__sympy-22714 | 1766 | **flagged, cleared** | Largest `.sideword/` in the corpus. `sympy/testing/runtests.py:1349,1497 os.walk(dir)` as above | **dynamic**: `12 passed` both; runner walk from the repo root returns 0 `.sideword` entries |
| sympy__sympy-23824 | 1756 | no | as above; additionally `sympy/testing/pytest.py:277` opens `this_file.parent.parent.parent / 'doc' / 'src' / 'explanation' / 'active-deprecations.md'` — a fixed path to a real repo file, not a glob, and `.sideword/` never mirrors non-`.py` files | static |

---

## Stage 2 method

`.sideword/` is copied into the **pristine `/testbed`** of the official
`swebench/sweb.eval.x86_64.<instance_id>` image, and the same test command is run before and
after. This is a tighter control than `-nc` vs `-sw`: the source code is byte-identical across
the two runs, so the *only* variable is the presence of the added files. (It deliberately does
not test the code-stripping itself, which is a different question.)

```
docker run --platform linux/amd64 -d --name ab_<id> swebench/sweb.eval.x86_64.<id> sleep infinity
docker exec ... "cd /testbed && <test_cmd>"          > <id>.base.log
docker cp /tmp/swconf/wt/<id>/.sideword ab_<id>:/testbed/.sideword
docker exec ... "cd /testbed && <test_cmd>"          > <id>.sw.log
```

Outcomes are compared per node id from the `-rA` short summary (`PASSED`/`FAILED`/`ERROR`/
`SKIPPED`/`XFAIL`/`XPASS`, ANSI-stripped), plus the summary line. Absolute failure counts are
irrelevant here — several instances fail tests in a pristine image (no network, no gold patch);
what matters is that the two columns match.

| Instance | outcomes compared | only in base | only in sw | differing |
|---|---|---|---|---|
| astropy__astropy-14598 | 175 | 0 | 0 | 0 |
| django__django-7530 | 63 (`Ran 63 tests … OK`) | 0 | 0 | 0 |
| matplotlib__matplotlib-23299 | 195 | 0 | 0 | 0 |
| mwaskom__seaborn-3069 | 173 | 0 | 0 | 0 |
| pallets__flask-5014 | 59 | 0 | 0 | 0 |
| psf__requests-2931 | 167 | 0 | 0 | 0 |
| pydata__xarray-7229 | 282 | 0 | 0 | 0 |
| pylint-dev__pylint-6528 | 169 | 0 | 0 | 0 |
| pytest-dev__pytest-10051 | 19 | 0 | 0 | 0 |
| scikit-learn__scikit-learn-25102 | 59 | 0 | 0 | 0 |
| sphinx-doc__sphinx-11445 | 7 | 0 | 0 | 0 |
| sympy__sympy-22714 | 12 (`tests finished: 12 passed`) | 0 | 0 | 0 |

x86_64 images run under emulation on this arm64 Mac, but the runs were cheap (0.2 s – 20 s each);
the cost was image pulls (4–7 GB each). No instance was skipped for being too slow and no image
was unavailable.

### The one apparent difference, and why it isn't one

`psf__requests-2931` reported `28 warnings` in the baseline run and `9 warnings` in the
`.sideword` run. The extra 19 are `DeprecationWarning: invalid escape sequence \*` raised at
**bytecode-compile time**; they appear only on the first run in a container, because the second
run reuses the `__pycache__` the first one wrote. Order-reversal control — deleting `.sideword/`
and re-running with a warm `__pycache__` — reproduces exactly `85 passed, 1 xfailed, 9 warnings,
81 errors`, identical to the `.sideword` run, with all 167 per-test outcomes matching. Nothing to
do with the added files.

---

## Two operational notes for building the arm-2 checkout

Neither is a test-suite reaction; both are ways the *harness* could manufacture the confound.

1. **Commit `.sideword/` in the arm-2 checkout, or `.gitignore` it.** SWE-bench extracts the
   model patch with `git diff` in `/testbed`. Untracked files are invisible to `git diff`, so
   the default is safe — but any agent or wrapper that runs `git add -A` before diffing would
   sweep 66–1,766 files into the prediction patch and fail the instance for reasons unrelated
   to the model. Committing them at setup time makes that impossible.

2. **Don't add `check-manifest`, `isort --recursive`, or `python setup.py clean/audit` to the
   run.** These are the only places in the corpus where a walk is rooted at the checkout root
   (`sympy setup.py:182 os.walk(dir_setup)`, `django tox.ini:62`, `pytest-dev setup.cfg
   [check-manifest]`). None of them is part of any SWE-bench eval command, and none of them
   would run inside a `pytest`/`runtests.py`/`bin/test` invocation.
