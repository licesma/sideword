# Tool inventory — EST-106

What each of the 30 `base_commit` checkouts (12 repos, `corpus/instances.json`) runs as a
linter / formatter / type checker / coverage / doc tool, which per-line comment directives
those tools honour, and which code-quality checks run *inside* the test suite (and therefore
read the very source the stripper rewrites). Read together with `corpus/directives.toml`
(the allowlist) and `corpus/directives-histogram.tsv` (the evidence).

Config files read per checkout: `setup.cfg`, `pyproject.toml`, `tox.ini`,
`.pre-commit-config.yaml`, `.flake8`, `pylintrc`, `mypy.ini`, `.coveragerc`, `.isort.cfg`,
`.codespellrc`, `azure-pipelines.yml`, `.travis.yml`, `appveyor.yml`, `.circleci/config.yml`,
`.github/workflows/*.y*ml`, `Makefile`, `build_tools/`, `bin/`, `doc/conf.py`.

Terminology: "PASS_TO_PASS-relevant" means the check is in a test file that appears in an
instance's `PASS_TO_PASS`/`FAIL_TO_PASS`. Across the 30 instances the P2P test files are
exactly the files touched by the test patch (`test_axes.py`, `test_header.py`, ...); **none of
the source-scanning code-quality tests below (sympy `test_code_quality`, sklearn
`test_docstring_parameters`, pytest `acceptance_test`, mpl `test_pyplot`) is in any instance's
P2P set.** They still matter because (a) the SWE-bench harness runs the whole test *file*, and
(b) import-time failures break every test.

---

## 1. Directive semantics per tool (what the keep rules mirror)

| tool | comment directive | how the tool matches | keep rule |
|---|---|---|---|
| CPython / PEP 263 | `# -*- coding: utf-8 -*-`, `# coding=utf-8`, `# encoding: utf-8`, `# vim: set fileencoding=…` | `^[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)` on **line 1 or 2 only** | `coding` (regex, line 1-2) |
| OS | `#!/usr/bin/env python` | line 1 only | `shebang` (prefix `!`, line 1) |
| PEP 484 / mypy / pyright / pytype | `# type: X`, `# type: ignore[code]`, `# type: (int) -> str` | comment must **start** with `type:` (`#\s*type\s*:`); tokenizer emits TYPE_COMMENT / TYPE_IGNORE | `type-comment` |
| mypy inline config | `# mypy: disallow-any-generics` | `line.startswith("# mypy: ")` at column 0 | `mypy` |
| pyright | `# pyright: ignore[rule]`, `# pyright: basic\|strict` | prefix | `pyright` |
| flake8 | `# noqa`, `# noqa: E501,F401`, `# NOQA`, `# NoQA:E704` | `# noqa(?::[\s]?(?P<codes>…))?` **re.I, `re.search` on the physical line**; file-level `\s*# flake8[:=]\s*noqa` re.I | `noqa` (contains, ci), `flake8` |
| pycodestyle | `# noqa`, `# nopep8` | `# no(?:qa\|pep8)\b` re.I, search | `noqa`, `nopep8` |
| ruff | `# noqa`, `# noqa: RUF100`, `# ruff: noqa`, `# ruff: isort: skip_file` | `#\s*noqa` case-insensitive; `# ruff:` prefix | `noqa`, `ruff` |
| coverage.py | `# pragma: no cover`, `# pragma: no branch`, `# pragma: nocover` | DEFAULT_EXCLUDE `#\s*(pragma\|PRAGMA)[:\s]?\s*(no\|NO)\s*(cover\|COVER)`, `re.search` on the line; repos override `exclude_lines` (see §2) | `pragma` (regex, ci) |
| black | `# fmt: off`, `# fmt: on`, `# fmt: skip`, `# fmt:off`, `# yapf: disable/enable` | exact comment text; since 23.x also when combined `# x # fmt: skip` / `# fmt: skip; x` (`contains_fmt_directive`) | `fmt`, `yapf` |
| isort | `# isort:skip`, `# isort: skip`, `# isort: split`, `# isort:skip_file`, `# isort: off/on`, `# isort: dont-add-imports`, `# isort: list/dict/unique-list/…` | `"isort:skip" in line or "isort: skip" in line or "isort: split" in line` (anywhere); whole-line for off/on/skip_file/actions; `stripped_line.endswith("# isort: split")` | `isort` (regex `\bisort:\s*[A-Za-z_-]+`) |
| pylint | `# pylint: disable=…`, `enable`, `disable-next`, `skip-file` | OPTION_RGX `\#.*?\bpylint:\s*([^;#\n]+)` — the pragma may follow other text in the same comment | `pylint` (regex `#.*\bpylint:`) |
| bandit | `# nosec`, `# nosec B101` | `#\s*nosec:?\s*(?P<tests>[^#]+)?#?` search | `nosec` |
| Cython | `# cython: language_level=3`, `# distutils: language=c++` | header comment lines (`.pyx`, and `.py` in pure-Python mode) | `cython-directive` |
| sphinx-gallery | `# sphinx_gallery_thumbnail_number = 2`, `# sphinx_gallery_start_ignore`, `# %%` cell marker, `####…` (≥20) legacy separator | INFILE_CONFIG_PATTERN `^[ \t]*#\s*sphinx_gallery_([A-Za-z0-9_]+)(\s*=\s*(.+))?`; text-block header `^#{20,}.*\|^# ?%%.*` | `sphinx-gallery-config`, `cell-marker` (the `#{20,}` separator is **not** kept — decoration outside example dirs; the prose block after it is stripped anyway) |
| xgettext (django `makemessages --add-comments=Translators`) | `# Translators: …` block right before a gettext call | comment block **starting** with the case-sensitive tag | `translators` |
| DeepSource | `# skipcq: PYL-W0613` | anywhere in line | `skipcq` |
| codespell | `# codespell:ignore word`, `codespell:ignore-next-line` | `[^\w\s]\s*codespell:ignore(?!-)\b` search | `codespell` |
| LGTM/CodeQL | `# lgtm[py/unused-loop-variable]` | anywhere | `lgtm` |
| matplotlib `tools/boilerplate.py` | `################# REMAINING CONTENT GENERATED BY boilerplate.py ##############`, `# Autogenerated by boilerplate.py.  Do not edit as changes will be lost.` | exact line match / regenerated text compared by `test_pyplot_up_to_date` | `matplotlib-boilerplate` |
| doctest | `# doctest: +SKIP` | **only inside `>>>` example source** (docstrings / .rst) — never a COMMENT token; 0 comment occurrences in the corpus (sympy has 105-144 per checkout, all in docstrings) | none ([[human]] doctest-prose) |
| emacs / vim | `# -*- mode: python -*-` (line 1-2), `# vim: set ts=4:` (first/last 5 lines) | editor modelines | `emacs-modeline`, `vim-modeline` |

Not honoured by any tool → prose: `# TODO`, `# XXX`, `# FIXME`, `# NOTE:`, `# License:`, `# Author:`, `#: attribute doc` (sphinx autodoc reads `#:` comments for **documentation**, i.e. exactly what Sideword moves out; no test in the corpus asserts on them — see sphinx §2).

## 2. Per repo

### astropy (7336 · 13398 · 14365 · 14598)

| | 7336 (2018) | 13398 (2022) | 14365 / 14598 (2023, identical infra) |
|---|---|---|---|
| flake8 | `.travis.yml` `flake8 astropy --select=E101,W191,W291,W292,W293,W391,E111,E112,E113,E502,E722,E901,E902` (whitespace-only) | pre-commit flake8 3.9.2 `--select E101,W191,E201,E202,W291,W292,W293,W391,E111,E112,E113,E30,E502,E722,E901,E902,E999,F822,F823` | `setup.cfg [flake8] select=E,F,W`, `extend-ignore=E203,E501,E711,E721,E731,E741,F403,F821,F841,W5`, per-file-ignores (`__init__.py:F401,F403,E402`, `examples/*.py:E1,E2,E402`) |
| ruff | – | – | `[tool.ruff] select=["ALL"]` + ~230-line extend-ignore (ERA001 commented-out code ignored; D-rules partly on, numpy convention); per-file-ignores; `--fix` in pre-commit |
| black | – | – | `[tool.black] line-length=88, force-exclude` (examples/, extern/, *tab.py) |
| isort | – | 5.10.1 (`[tool.isort]` line_length=100, big extend_skip_glob) | via ruff isort |
| pyupgrade / flynt / codespell | – | pyupgrade --py38-plus | pyupgrade, flynt, **codespell** (`[tool.codespell]` skip + ignore-words-list) |
| pre-commit misc | – | end-of-file-fixer, **trailing-whitespace**, debug-statements | + **python-check-blanket-noqa** (every `# noqa` must carry a code), rst hooks |
| coverage | `astropy/tests/coveragerc` | `[tool.coverage.report] exclude_lines = pragma: no cover, except ImportError, raise AssertionError, raise NotImplementedError, 'def main(.*):', pragma: py{ignore_python_version}, def _ipython_key_completions_` | same |
| pytest | `doctest_plus = enabled`, `testpaths = astropy docs` | `doctest_plus = enabled`, `--doctest-rst`, `doctest_norecursedirs`, `doctest_subpackage_requires` | same + `filterwarnings = error` |
| sphinx-gallery | `docs/conf.py` (guarded import) | same | same |
| comment directives in non-test source | 17 `# noqa`, 129 `# doctest:` (docstrings) | 401 `# noqa`, 204 `# doctest:` | 61 `# noqa`, 206 `# doctest:`, `# fmt: skip/off/on` 82, `# isort: split` 28, `# pylint: disable` 79 |

**In-test-suite checks reading source:** `astropy/tests/tests/test_imports.py` (walks/imports every module — catches import-time failures; `test_toplevel_namespace`). No tokenizer / whitespace / noqa scanner. `astropy/utils/tests/test_parsing.py` skips itself when `_docstring_canary.__doc__` is falsy (i.e. auto-skips after stripping).

**Import-time docstring dependencies (stripper concern, listed for the record):** `astropy/io/ascii/core.py:1181/1189` (13398) `:1233/1246` (14365/14598) `func.__doc__ += inspect.cleandoc(cls.__doc__).strip()` in the reader/writer metaclass — **`cleandoc(None)` raises `AttributeError` at `import astropy.io.ascii`** if a reader/writer class docstring is removed (definite; 14365's P2P file is `astropy/io/ascii/tests/test_qdp.py`). `astropy/utils/decorators.py` `format_doc` raises `ValueError` only when called with `docstring=None` on an object whose `__doc__` is empty; the ~40 `@format_doc(base_doc, …)` uses in `coordinates/builtin_frames/*.py` and `baseframe.py` pass the module-level string constant `base_doc`, which re-sets `cls.__doc__`, so `builtin_frames/__init__.py:124` `cls.__doc__.splitlines()` is safe. `astropy/visualization/wcsaxes/patches.py` `Polygon.__init__.__doc__.replace(...)` reads *matplotlib's* (installed, unstripped) docstrings — safe. `astropy/cosmology/io/yaml.py:66` `representer.__doc__.format(tag)` (14365/14598) — unguarded, at import of `astropy.cosmology.io`. 7336-only unguarded: `astropy/coordinates/solar_system.py:333,367,416,464,497` `__doc__ += …` (import of `astropy.coordinates`), `astropy/io/fits/convenience.py:903,942`, `astropy/io/votable/exceptions.py:1449` `__doc__.format(...)`. Guarded (`if __doc__ is not None`): `astropy/constants/__init__.py`, all `astropy/units/*.py` unit summaries, `io/fits/hdu/table.py`, `io/registry`, `time/core.py`, `modeling/models.py`.

### django (7530 · 14631 · 14787)

- flake8 in all three (`setup.cfg [flake8]`, `max-line-length=119`, `ignore=W601` (7530) / `W504,W601` (14631+), **no select / no per-file-ignores** → E26x comment-format and W29x/W391/E30x whitespace checks active); tox `flake8`, GH `linters.yml` (14631+), pre-commit isort+flake8 (14631+).
- isort (`setup.cfg [isort]`, `known_first_party=django`, `multi_line_output=5`); `.editorconfig` `trim_trailing_whitespace`, `insert_final_newline`.
- Test runner is `tests/runtests.py` (unittest); no coverage/mypy/black/ruff/codespell config; `pyproject.toml` (14631+) is build-system only.
- Comment directives: `# noqa` 302, `# -*- coding: utf-8 -*-` (7530 only), **`# Translators:` 72** (humanize 21, boundfield, paginator, fields/__init__, admin/options, defaultfilters, utils/text …), 0 pragma/type/fmt/isort/pylint.
- **In-test-suite checks:** none scan `django/` source. `tests/view_tests/tests/test_debug.py:721` (14631+) reads source lines from disk but of the *test* file. All `__doc__` assertions target docstrings in `tests/`.
- Runtime `__doc__`: `django/db/models/base.py:349-351` `if cls.__doc__ is None: cls.__doc__ = "%s(%s)"` (behaviour change, no raise); `contrib/admindocs/utils.parse_docstring` None-safe; `core/management/commands/migrate.py` `(code.__doc__ or '')`. Nothing raises.

### matplotlib (14623 · 23299 · 24970 · 25311)

| | 14623 (2019) | 23299 (2022) | 24970 (Jan 2023) | 25311 (Mar 2023) |
|---|---|---|---|---|
| flake8 | `.flake8` no select; ignore incl. E265,E266,F401,F403,F811,F841,N8xx; long per-file-ignores; travis job | `.flake8` **select = C90,E,F,W,D1xx-D4xx (numpydoc set)**, max-line-length 79; flake8-docstrings/pydocstyle in pre-commit; reviewdog job | same as 23299 | `.flake8` **select = D,E,F,W**, max-line-length 88, `force-check=True`; `[tool.ruff] select=["D","E","F","W"]`, `external=[E122,E201,…]`, per-file-ignores; `[tool.isort]` custom sections |
| pre-commit | – | check-docstring-first, end-of-file-fixer, **mixed-line-ending**, name-tests-test, **trailing-whitespace**, flake8+pydocstyle `--docstring-convention=all`, **codespell v2.1.0** | same | same + isort 5.12.0 restricted to `galleries/` |
| coverage | `.coveragerc` exclude_lines = raise NotImplemented, def __str__, def __repr__, if __name__ … (**no `pragma: no cover`**) | + `pragma: no cover` | same | same |
| pytest | `pytest.ini` testpaths=lib, no doctests | + `filterwarnings = error` (`lib/matplotlib/testing/conftest.py`) | same | same |
| sphinx-gallery | `doc/conf.py sphinx_gallery_conf`; separators = `####…` banners (679), 0 `# %%`, 11 `sphinx_gallery_*` | `remove_config_comments=True`; 1101 banners, 0 `# %%`, 14 flags | 1130 banners, 2 `# %%`, 15 flags | `galleries/` reorg: **836 `# %%`**, 307 banners, 16 flags |
| directives | `# lgtm[…]` 4, `# nopep8` 0, `# noqa` 144 total across the four | | | |

**In-test-suite checks reading non-test source:**
- `lib/matplotlib/tests/test_pyplot.py::test_pyplot_up_to_date` (all four): copies `lib/matplotlib/pyplot.py`, runs `tools/boilerplate.py` on it and asserts byte-identity. `build_pyplot()` truncates at the exact comment line `################# REMAINING CONTENT GENERATED BY boilerplate.py ##############` (raises `ValueError` if missing — **kept by `matplotlib-boilerplate`**), then re-emits `# Autogenerated by boilerplate.py.  Do not edit as changes will be lost.` before every generated function (**kept**), inline `# noqa` (**kept**), and the **docstrings** of the 19 colormap functions (`"""Set the colormap to 'viridis'. …"""`) — those are docstrings and are removed by the stripper, so this test would fail on a stripped tree. Generation reads *signatures* only, so stripping docstrings from `axes/_axes.py` does not change the output. Not P2P for any instance.
- `lib/matplotlib/tests/test_matplotlib.py::test_use_doc_standard_backends` (all four): parses `matplotlib.use.__doc__.split('- interactive backends:\n')` — a **removed `use()` docstring makes it raise `AttributeError`**. `test_importable_with__OO` (23299+) is mpl's own "docstrings may be absent" contract test.
- `test_rcparams.py::test_if_rctemplate_is_up_to_date/would_be_valid` (14623 only) parse `#key: value` comment lines of the *data* file `mpl-data/matplotlibrc` (not `.py`, untouched).
- `test_artist.py::test_artist_inspector_get_aliases` etc. depend on `ArtistInspector` parsing setter docstrings (`.. ACCEPTS:` markers, ``Alias for `set_linewidth`.``).
- **Import-time docstring dependencies (verified by reading, all guarded):** `lib/matplotlib/artist.py` `ArtistInspector.get_aliases()` calls `re.search(..., inspect.getdoc(func))` only after `is_alias(func)` (which returns False when `getdoc` is None), and alias docstrings are generated at runtime by `_api.define_aliases` — so a stripped tree does **not** crash here (an earlier draft of this inventory said otherwise). `lib/matplotlib/scale.py:768` (14623 only) `textwrap.indent(inspect.getdoc(scale_class.__init__), " " * 8)` in `_get_scale_docs()` at module scope **does** raise `AttributeError` if any `ScaleBase.__init__` docstring is removed (23299+ use `or ""`). `_api/deprecation.py:486-487` (24970/25311) `def empty_with_docstring(): """doc"""` compared by `__code__.co_code` — replacing the docstring-only body with `pass` changes which overrides count as "empty". `_docstring.Substitution`/`interpd`/`dedent_interpd`/`copy` are `if func.__doc__:`-guarded, but a docstring that survives partially edited raises on `%(…)s` / `{dir}` formatting (`axes/_axes.py` fill_between, `scale.py`).

### mwaskom/seaborn (3069)

- flake8 (`setup.cfg`: max-line-length 88, ignore E741,F522,W503, exclude `seaborn/cm.py, seaborn/external`), `make lint`; mypy (`ignore_missing_imports`) on `seaborn/_core _marks _stats`; coverage `[coverage:report] exclude_lines = pragma: no cover, if TYPE_CHECKING:, raise NotImplementedError`; pytest with no ini (no doctests); pre-commit: flake8, mypy, check-yaml, end-of-file-fixer, trailing-whitespace.
- Directives: `# noqa` 46, `# type: ignore` 6, 0 pragma.
- **In-test-suite checks:** none read source; `tests/test_docstrings.py` uses in-test functions.
- **Import-time HARD failure on missing docstrings:** `seaborn/_marks/base.py:302` `docstring_lines = mark.__doc__.split("\n")` in `document_properties` (applied to 12 Mark classes in `_marks/area.py, bar.py, dot.py, line.py, text.py`); `seaborn/_docstrings.py:48-59` `DocstringComponents.from_function_params` → `NumpyDocString(pydoc.getdoc(func))["Parameters"]` at import of `distributions.py`, `relational.py`, then `""".format(params=_param_docs…)` calls in `distributions.py`, `relational.py`, `axisgrid.py`, `categorical.py`, `regression.py`. `import seaborn` (needed by the P2P file `tests/_core/test_plot.py`) breaks if those docstrings go.

### pallets/flask (5014)

- `.flake8` (bugbear B/B9, implicit-str-concat, `per-file-ignores = src/flask/__init__.py: F401`), black 23.1 (defaults), pyupgrade, reorder-python-imports, mypy (`[tool.mypy] files=["src/flask"]`, `warn_unused_ignores=true`), coverage (`[tool.coverage.run]` only, default pragma), pytest `testpaths=["tests"]`, `filterwarnings=["error"]`, no doctests. Directives: `# noqa` 8, `# type: ignore` 68, `# pragma: no cover` 14.
- No in-test source scanning; `views.py:128` / `signals.py:23` copy `__doc__` (None-safe).

### psf/requests (2931)

- Only `setup.cfg [wheel]` and `Makefile` (`py.test test_requests.py`, `--cov=requests`); no linters at all. Directives: `# noqa` 16, `# flake8: noqa` 13 (vendored chardet), `# nopep8` 1, `# -*- coding` 15. No source-scanning tests; the single `.__doc__` is vendored six.

### pydata/xarray (4356 · 7229)

| | 4356 (2020) | 7229 (2022) |
|---|---|---|
| flake8 | `setup.cfg` ignore E203,E402,E501,E731,W503; exclude .eggs, doc; azure job | same + `builtins = ellipsis`; flake8 6.0 pre-commit |
| black / blackdoc / isort | black stable, blackdoc, isort (`known_first_party=xarray`, multi_line_output=3) | black + black-jupyter, blackdoc, isort `profile=black`, autoflake, pyupgrade --py38-plus |
| mypy | `[mypy-*]` ignore_missing_imports blocks | `[tool.mypy] files="xarray"`, `show_error_codes`; CI mypy jobs |
| coverage | `.coveragerc` omit only (default pragma) | `[tool.coverage.report] exclude_lines = ["pragma: no cover", "if TYPE_CHECKING"]` |
| pytest | `testpaths = xarray/tests properties`, **no doctests** | same, but CI job `ci-additional.yaml:79` runs `pytest --doctest-modules xarray --ignore xarray/tests -Werror` (docstring doctests are CI tests) |
| other | `.deepsource.toml` (→ `# skipcq`), pep8speaks | pep8speaks |
| directives | `# noqa` 16, `# type: ignore` 36, `# pragma: no cover` 27 | `# noqa` 23, `# type: ignore` 94, `# pragma: no cover` 24 |

- **P2P-relevant:** `xarray/tests/test_duck_array_ops.py::test_docs` (instance 4356) asserts `DataArray.sum.__doc__` text — generated at import from the string constant `_REDUCE_DOCSTRING_TEMPLATE` in `xarray/core/ops.py` (an assignment, not a docstring → survives).
- **Import-time HARD failure (7229):** `xarray/plot/dataset_plot.py:672-674` `if da_doc is None: raise NotImplementedError("DataArray plot method requires a docstring")` in the `_update_doc_to_dataset` decorator; then `.replace("\n    Parameters\n    ----------\n    darray : DataArray\n    ", …)` needs the exact text. Silent `"None…"` docstrings: `plot/plot.py:573`, `dataset_plot.py:248` (4356), `dataarray_plot.py:851,1407` (7229). `xarray/core/_typed_ops.py` (7229) has 184 `.__doc__` copies (generated file).

### pylint-dev/pylint (6528)

- flake8 (`.flake8` ignore E203,W503,E501; flake8-typing-imports), **pylint on itself** (pre-commit `pylint -rn -sn --rcfile=pylintrc --fail-on=I`; `pylintrc` disables missing-docstring, `ignore-comments/docstrings/imports/signatures=yes` for similarities), mypy (`warn_unused_ignores`, `enable_error_code = ignore-without-code` → bare `# type: ignore` is an error), isort `profile=black`, black 22.3 + black-disable-checker, autoflake, pyupgrade, **copyright-notice** (`--notice=script/copyright.txt --enforce-all`: every `.py` must start with the 3-line license header — the [[human]] `pylint-license-header` rule), pydocstringformatter (`files: pylint`), rstcheck, coverage `.coveragerc` exclude_lines = pragma: no cover, def __repr__, if TYPE_CHECKING:, @overload, raise NotImplementedError(). pytest `testpaths=tests`, `--strict-markers`, no doctests.
- Directives: `# pylint:` 100, `# type: ignore` 55, `# pragma: no cover` 44, `# noqa` 1.
- **In-test-suite linters (P2P files for 6528 are `tests/lint/unittest_lint.py`, `tests/test_self.py`):** both run pylint only on files under `tests/` (regrtest_data, input, data) — untouched. `test_self.py:1436` lists `pylint/extensions/*.py` file names (set of files, not content). `unittest_lint.py::test_full_documentation` calls `print_full_documentation` which renders checker **class docstrings** (guarded `if doc:`) — spot-checks only auto-generated text and message ids, so passes without docstrings. `doc/test_messages_documentation.py` (CI-only, outside testpaths) lints `doc/data/messages/**/{good,bad}.py` and parses `# [message-id]` / `# +1: [msg]` annotation comments with `pylint.testutils.constants._EXPECTED_RE` — **230 non-test files whose comments and exact line numbers are load-bearing** for that (non-P2P) test. `tests/test_pylint_runners.py` runs pylint on itself (test file, untouched).
- Runtime `__doc__`: `pylint/config/arguments_manager.py:134` guarded; `pylint/checkers/base_checker.py:125` guarded.

### pytest-dev/pytest (5262 · 10051)

| | 5262 (2019) | 10051 (2022) |
|---|---|---|
| flake8 | `tox.ini` max-line-length 120, ignore E203,W503 | + **flake8-docstrings** (D200/D201/D206-D211/D300/D301/D403… enforced; D1xx ignored) + flake8-typing-imports |
| black / blacken-docs / pyupgrade / autoflake | black 19.3b0, blacken-docs, pyupgrade --keep-percent-format, reorder-python-imports | black 22.3 (`target-version=py37`), blacken-docs, autoflake, pyupgrade --py37-plus, setup-cfg-fmt, fix-encoding-pragma `--remove`, `python-use-type-annotations` (bans `# type:` annotations) |
| mypy | none (0 `# type: ignore`) | `[mypy]` strict-ish; 131 `# type: ignore` |
| coverage | `.coveragerc` no exclude_lines | `exclude_lines = \#\s*pragma: no cover, ^\s*raise NotImplementedError\b, ^\s*return NotImplemented\b, ^\s*assert False(,\|$), ^\s*assert_never\(, ^\s*if TYPE_CHECKING:, ^\s*@overload( \|$)` |
| pytest | `addopts = -ra -p pytester --strict-markers`, `testpaths=testing`, `xfail_strict`, `filterwarnings=error`; doctests only in `tox -e doctesting` | same via `[tool.pytest.ini_options]` |
| pygrep hooks | `py-deprecated` (bans `py.path.local`… **anywhere in any .py incl. comments**) | + `py-path-deprecated` |
| directives | `# noqa` 27, `# pragma: no cover` 3, `# fmt:` 2 | `# noqa` 10, `# type: ignore` 131, `# pragma: no cover` 4, `# fmt: off/on` 6 |

- **In-test-suite checks (not P2P):** `testing/acceptance_test.py::test_docstring_on_hookspec` asserts every `pytest_*` name in `src/_pytest/hookspec.py` has a truthy `__doc__`; `testing/python/approx.py::test_doctests` runs the doctests in `approx.__doc__` (`src/_pytest/python_api.py`; **unguarded in 5262** — `None` raises inside `get_doctest`); `testing/test_modimport.py` (5262) / `testing/test_meta.py` (10051) subprocess-import every `src/_pytest/*.py` with `-W error`.
- Runtime `__doc__`: `src/_pytest/assertion/rewrite.py:264/255` `mod.__doc__ or ""` (module docstring presence shifts where assert-rewriting starts — None-safe); `terminal.py`, `python.py --fixtures` guarded.

### scikit-learn (10297 · 13142 · 15100 · 25102)

| | 10297 / 13142 / 15100 | 25102 |
|---|---|---|
| flake8 | `setup.cfg [flake8] ignore=E121,E123,E126,E226,E24,E704,W503,W504`; `build_tools/circle/flake8_diff.sh` (diff-only), Makefile `flake8-diff`, `pylint -E` target | `max-line-length=88`, `exclude=…sklearn/externals…`, **`per-file-ignores = examples/*: E402, doc/conf.py: E402`**; `build_tools/linting.sh` (black --check, flake8, mypy sklearn/, git-grep bans on `# doctest\: \+(ELLIPSIS\|NORMALIZE_WHITESPACE)` and on `joblib import delayed`) |
| black / mypy / codespell | – | black 22.3 (`preview=true`, exclude), mypy (`ignore_missing_imports`, `allow_redefinition`), codespell (`[codespell]` skip + ignore-words) |
| coverage | `.coveragerc` **no exclude_lines** (default pragma) | same |
| pytest | **`--doctest-modules`** in all four (`doctest_optionflags = NORMALIZE_WHITESPACE ELLIPSIS` 15100+); every `sklearn/**/*.py` docstring is a collected doctest | same + `testpaths=sklearn`, `-p sklearn.tests.random_seed` |
| sphinx-gallery | `doc/conf.py sphinx_gallery_conf`; 0 `# %%`, 0-1 `sphinx_gallery_*` | `remove_config_comments=True`; **1057 `# %%`** in 145/285 example files, 2 `sphinx_gallery_thumbnail_number` |
| directives | `# noqa` 20/30/40, `# flake8: noqa` 0/2/0, `# pragma: no cover` 2/16/2 | `# noqa` 43, `# type: ignore` 24, `# pragma: no cover` 7 |

- **In-test-suite checks (not P2P):** `sklearn/tests/test_docstring_parameters.py::test_tabs` — `inspect.getsource(mod)` for every `sklearn.*` module, `assert '\t' not in source` (**never introduce a tab**); `::test_docstring_parameters` (skips only when numpydoc is missing) — a `None` docstring yields a `Parameters`-count mismatch → `AssertionError`; `sklearn/tests/test_docstrings.py` (25102) runs `numpydoc.validate` on every public class/method/function — missing docstring → `GL08` → `ValueError`; `sklearn/utils/estimator_checks.py:3933` (25102) `"feature_names_in_" not in estimator_orig.__doc__` → `TypeError` on `None`; `sklearn/tests/test_common.py::test_configure` `exec(open('setup.py').read())`.
- Runtime `__doc__`: `sklearn/utils/deprecation.py _update_doc` None-safe; `sklearn/setup.py` `warnings.warn(BlasNotFoundError.__doc__)` only when BLAS missing; datasets `DESCR=__doc__` (module docstrings become `Bunch.DESCR`, asserted by dataset tests).

### sphinx-doc/sphinx (8475 · 11445)

| | 8475 (2020) | 11445 (2023) |
|---|---|---|
| flake8 | `setup.cfg [flake8]` max-line-length 95, ignore E116,E241,E251,E741,W504,I101, `per-file-ignores = tests/*: E501`, import-order smarkets; **local plugin X101 `utils/checks.py:sphinx_has_header`** requires every `sphinx/**/*.py` module docstring to have the module-name header + `:copyright:`/`:license:` lines | `.flake8` (+SIM ignores); X101 gone |
| ruff | – | `[tool.ruff] select=["ALL"]` with ~100 ignores (D all, ERA001, PGH003, …), `external=["E704","W291","W293","SIM110","SIM113"]` (RUF100 whitelist for `# noqa` codes), per-file-ignores; CI ruff 0.0.261 |
| isort / mypy | isort line_length 95; mypy `warn_unused_ignores=True`, strict_optional=False | isort `profile=black`; `[tool.mypy]` strict, `warn_unused_ignores=true` |
| coverage | `[coverage:report] exclude_lines = pragma: no cover, raise NotImplementedError, if __name__ == .__main__.:` | same in pyproject |
| pytest | `testpaths=tests`, `filterwarnings=all` | same; `PYTHONWARNINGS=error` in tox |
| directives | `# NOQA` 93 + `# noqa` 9, `# type:` 966 (mostly PEP 484 signature comments), `# type: ignore` 289, `#:` attr docs 108 | `# NoQA:` 47 + `# noqa:` 25 + `#noqa` 3, `# type:` 249, `# type: ignore` 235, `#:` 114 |

- **In-test-suite checks:** none reads `sphinx/`'s own comments/docstrings. `tests/test_pycode.py` calls `ModuleAnalyzer.for_module('sphinx')` and asserts only `modname`/`srcname`; `find_attr_docs()` (`#:` comments) is exercised only on `tests/roots/**` and inline strings. All autodoc/napoleon targets are under `tests/roots/`. → the 108-114 `#:` attribute-doc comments in `sphinx/` are documentation, not test input; the stripper removes them.
- Runtime `__doc__`: all guarded (`ext/inheritance_diagram.py`, `ext/coverage.py`, `util/inspect.py`, `ext/napoleon`, `ext/autodoc`).

### sympy (13551 · 16597 · 20916 · 22714 · 23824)

| | 13551 | 16597 | 20916 | 22714 | 23824 |
|---|---|---|---|---|---|
| flake8 | – | – | `setup.cfg [flake8] doctests=True, ignore=F403, select=F,E722`, exclude `_antlr`, rubi; CI `flake8 sympy` | same | same |
| mypy | – | – | `[mypy]` (empty) + per-module | `warn_unused_configs`, exclude autolev test-examples; CI `mypy sympy` | same |
| coverage | – | `.coveragerc` **`exclude_lines = \#.*pragma:\s*no.?cover`, `^\s*if SYMPY_DEBUG:`** | `coveragerc_travis` same | same | same |
| pytest | no ini | `pytest.ini`: `testpaths = sympy doc/src`, `doctest_optionflags = NORMALIZE_WHITESPACE IGNORE_EXCEPTION_DETAIL ELLIPSIS FLOAT_CMP`, **`doctestplus = enabled`** | same (doctestplus) | doctestplus removed | same |
| directives (non-test) | `# pragma: no cover` 96 | 95, `# noqa` 1 | 94, `# noqa` 265, `# type:` 442 | 99, `# noqa` 268, `# type:` 820 | 99, `# noqa` 78, `# type:` 419 |
| unicode test | – | – | `sympy/testing/quality_unicode.py` (messages A-E) | same | B and D only |

- **`sympy/utilities/tests/test_code_quality.py` (13551/16597) → `sympy/testing/tests/test_code_quality.py` (20916+) `test_files`** walks `sympy/` (`*.py`), `examples/` (`*.py`), `bin/` (**every file**, pattern `*`, excluding `~ .pyc .sh (.mjs)`) and `isympy.py build.py setup.py setupegg.py`, and per line asserts: no `line.endswith(" \n") or line.endswith("\t\n")` (**trailing whitespace**), no `\r\n`, no tabs in leading whitespace (also inside `>>>` docstring lines), no `str_raise_re`/`gen_raise_re`/`old_raise_re` (all `^\s*`-anchored → comments can never match), no `implicit_test_re` (`from x import *`, anchored), no `func_is_re = \.\s*func\s+is` (**unanchored** — a comment containing `.func is` in a non-`test_*` file fails; removing comments can only remove matches), and at EOF: last line must end with `\n` (`message_eof`) and must not be a bare `\n` when `idx > 0` (`message_multi_eof`: **no blank line at end of file** — a stripper that deletes the last full-line comment of `code\n\n# c\n` leaves `code\n\n` and fails). Test-file-only rules (`def` naming, duplicate tests, bare expressions in 22714+, `find_self_assignments` in 13551/16597) don't touch stripped files.
- **`sympy/testing/quality_unicode.py._test_this_file_encoding` (20916/22714/23824):** non-whitelisted files may contain no non-ASCII char at all (A/B); whitelisted files (`liealgebras/type_g.py`, `weyl_group.py`, `physics/wigner.py`, `physics/optics/polarization.py`, `physics/mechanics/joint.py` (22714+), `bin/authors_update.py`/`mailmap_check.py`, `parsing/latex/_antlr/__init__.py` strict, plus test files) **must** contain one (D) and, in 20916/22714, **must carry a `# coding=utf-8` header on line 1-2 (C)**; non-whitelisted files must not carry the header without unicode (E). Verified for all three checkouts: after stripping comments and non-doctest docstrings, the unicode in every whitelisted non-test file survives (type_g/weyl_group: code string literals `"0≡<≡0…"`; wigner/polarization: doctest docstrings; joint.py: the `PinJoint` doctest docstring at :313 keeps `≡`… while the class docstring at :16 is removed) and the header comment is kept by the `coding` rule.
- Other source readers: `sympy/core/tests/test_args.py::test_all_classes_are_tested` (regex `^class …` on file text — comment-safe); `test_module_imports.py` (subprocess); `bin/test_*` scripts are CI steps, not pytest.
- **Import-time `__doc__` failures if docstrings are removed:** `sympy/physics/vector/functions.py` `cross.__doc__ += Vector.cross.__doc__` (×3, module level, `TypeError` on None; :24/32/219 in 13551 … :27/37/230 in 23824), `sympy/physics/vector/printing.py` `init_printing.__doc__.split('Examples\n    ========')` (:421 13551 … :370 23824), `sympy/vector/basisdependent.py` `evalf/simplify/trigsimp/factor/diff.__doc__ += Expr.….__doc__` (5 class-body sites per checkout). Guarded: `multipledispatch/dispatcher.py`, `core/kind.py`, `assumptions/assume.py`, `testing/runtests.py`, matrices `A.__doc__ = B.__doc__`.

## 3. Cross-cutting: what the stripper must preserve besides the [[keep]] comments

| property | required by |
|---|---|
| no trailing whitespace on any line; no `\r`; no tabs; single `\n` at EOF; **no blank last line** | sympy `test_code_quality::test_files` (sympy/, examples/, bin/, top-level scripts); astropy flake8 `--select W291,W293,W391,…`; django flake8 defaults; matplotlib/astropy/xarray/pytest/pylint pre-commit `trailing-whitespace`, `end-of-file-fixer`, `mixed-line-ending`; sklearn `test_tabs` (`'\t' not in inspect.getsource(mod)`) |
| `# coding=utf-8` header on line 1-2 of sympy unicode-whitelisted files | sympy 20916/22714 `quality_unicode` message C — covered by `coding` keep rule |
| module/class/function docstrings that are consumed at import (`__doc__ +=`, `.split`, `.format`, `inspect.cleandoc`, `document_properties`, `_update_doc_to_dataset`) | seaborn (`_marks/base.py:302` `mark.__doc__.split` on 12 Mark classes; `_docstrings.py:48-59` numpydoc parse of `KDE.__init__` etc. then `.format(params=…)`), xarray-7229 (`plot/dataset_plot.py:673` explicit `NotImplementedError`), astropy 13398/14365/14598 (`io/ascii/core.py` `inspect.cleandoc(cls.__doc__)` in the reader/writer metaclass — import of `astropy.io.ascii`; `utils/decorators.format_doc` only raises when called with `docstring=None` on an empty `__doc__`; `builtin_frames` is safe because `format_doc(base_doc, …)` re-sets `__doc__` from the string constant), matplotlib-14623 (`scale.py:768`), sympy (`physics/vector/functions.py` `+=` ×3, `physics/vector/printing.py` `.split`, `vector/basisdependent.py` `+=` ×5 — only on import of `sympy.physics.vector` / `sympy.vector`, not `import sympy`) — **these break `import <pkg>` under the current contract (remove all non-doctest docstrings): seaborn-3069 (P2P imports seaborn), xarray-7229 (P2P imports xarray), astropy-14365 (P2P is `io/ascii/tests/test_qdp.py`) are affected instances; flagged in the EST-106 spec for the strip step** |
| docstrings asserted by (non-P2P) tests | matplotlib `use.__doc__`, `test_pyplot_up_to_date` colormap docstrings; pytest `hookspec` docstrings, `approx.__doc__` doctests; sklearn numpydoc validation; astropy registry/cosmology docstrings |
| doctest-bearing docstrings | kept by contract (astropy doctestplus, sympy doctestplus/bin/doctest, sklearn `--doctest-modules`, xarray-7229 CI doctest job) |
