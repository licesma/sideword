# Harness contract (EST-85 pre-gate, -nc arm only)

Python: `/Users/esteban/repos/sideword/.venv/bin/python` (CPython 3.14.3). Every script in
`harness/` runs under it. Stdlib only in `harness/strip.py`; `pyarrow`/`huggingface_hub`
are installed for the instance step.

## Layout

```
corpus/instances.json      EST-104  chosen instances (see schema below)
corpus/directives.toml     EST-106  keep / watch / human lists (schema in the file header)
corpus/directives-histogram.tsv     first-token histogram behind the allowlist
harness/paths.py           is_test_path(path) — shared by pass 1 and pass 2
harness/directives.py      load(path) + classify(comment_text, lineno) -> Keep|Human|Unresolved|Remove
harness/strip.py           strip_source(src: bytes, directives, keep_owners=None) -> (out: bytes, records: list[dict]); CLI
harness/astcheck.py        equal(orig: bytes, stripped: bytes, directives=None, keep_owners=None) -> (ok, detail); CLI
harness/docuse.py          analyze({path: bytes}, directives) -> which docstrings the tree reads back (rule "consumed")
harness/tests/             unit tests (stdlib corpus for the stripper)
harness/pass1.py           EST-108  fill cache/<blob-sha>.py + cache/<blob-sha>.jsonl
harness/pass2.py           EST-109  materialize -nc commits + tags in the mirror
cache/                     content-addressed by git blob sha (sha1 of "blob <len>\0<bytes>")
~/repos/sideword-corpus    EST-105  the mirror repo (branch per source repo, remotes per upstream)
```

## corpus/instances.json

```json
[{"instance_id": "sympy__sympy-13091", "repo": "sympy/sympy", "base_commit": "<sha>",
  "version": "1.1", "FAIL_TO_PASS": [...], "PASS_TO_PASS": [...],
  "test_patch_paths": ["sympy/core/tests/test_x.py", ...],
  "patch_paths": ["sympy/core/x.py", ...],
  "created_at": "..."}]
```

## Test-path rule (`harness/paths.py`)

A path is a test path (never stripped) if ANY holds:
- any path segment is `tests`, `test`, `testing`;
- basename is `conftest.py`, `tests.py`, matches `test_*.py` or `*_test.py`;
- it appears in the instance's `test_patch_paths`.
Everything else ending in `.py` is stripped, including `doc/`, `docs/`, `examples/`,
`benchmarks/`, `setup.py`. Non-`.py` files are never touched.

## Stripper rules (`harness/strip.py`)

- tokenize + ast; edits are span deletions/replacements on the ORIGINAL bytes so encoding,
  BOM, per-line line endings, tabs, and everything untouched stay byte-identical.
- Remove every COMMENT token unless `directives.classify` says Keep. Full-line comment (only
  whitespace before `#` on its physical line) -> delete the whole physical line incl. its
  newline. Trailing comment -> delete from the end of the last non-whitespace char before `#`
  to end of line (never leave trailing whitespace: sympy's code-quality test is PASS_TO_PASS).
- Docstring = first statement of Module / ClassDef / FunctionDef / AsyncFunctionDef that is
  `Expr(Constant(str))`. Remove it unless, in this order:
  1. any line of its value, lstripped, starts with `>>>` (doctest -> keep byte-for-byte,
     record kind="doctest_docstring");
  2. a general `[[docstrings]]` rule in directives.toml matches it
     (`Directives.classify_docstring(value, owner, module_text)`: pattern on the value, `owner`
     regex fullmatched against the qualified owner name, `module` regex searched in the module
     source) -> keep byte-for-byte, record kind="docstring" action="kept" rule=<name>;
  3. its owner fullmatches an entry of `keep_owners`, the `[(owner_regex, rule)]` context the
     caller passes because the blob alone cannot carry it: the consumption analysis
     (`harness/docuse.py`, run by pass 1 over the whole instance tree; rule "consumed") and the
     per-repo tier of directives.toml (resolved by pass 1 from repo + path; rule = entry name)
     -> keep, recorded the same way.
  If removal empties the body, put `pass` at the docstring's indentation (same whitespace
  bytes as the original line prefix; one-liner `def f(): "d"` -> `def f(): pass`).
- A non-empty `keep_owners` is echoed into the `stats` record (`keep_owners`), so a cache entry
  states the context it was written under; pass 1 refuses (`context_conflict`) when a blob is
  wanted under a different context than the cache holds, or by two instances under different
  contexts. The cache stays keyed by blob sha.
- Bare string statements elsewhere (attribute docs, e.g. `x = 1` then `"""doc"""`) are KEPT
  and recorded kind="stray_string" so the leak is measurable. Not a docstring per Python.
- `from __future__` stays first executable statement automatically; verify in tests.
- Files that fail `ast.parse` under 3.14 are left byte-identical and recorded as
  `{"kind":"parse_error"}` — never crash the batch.
- Output must satisfy `astcheck.equal(orig, stripped)`.

## astcheck.equal

`ast.dump(norm(parse(orig)), include_attributes=False) == ast.dump(norm(parse(stripped)), include_attributes=False)`
where `norm` drops every leading non-doctest string statement of a doc-owner body and inserts
`Pass` when that empties a class/function body. Also require: stripped parses; every
non-doctest docstring remaining in stripped is one of the original's leading strings for the
same owner (same value) AND is allowed to stay -- a general `[[docstrings]]` rule matches it or
its owner fullmatches `keep_owners` (`equal(orig, stripped, directives, keep_owners)`; passes 2
and 4 read the context back from the sidecar's `stats.keep_owners`); comment tokens remaining
in stripped all classify as Keep. Returns (ok: bool, detail: str).

## Sidecar JSONL (`cache/<sha>.jsonl`, one record per line)

```
{"kind":"comment",           "action":"removed","line":12,"col":4,"text":"# ...","unresolved":false}
{"kind":"comment",           "action":"removed","line":40,"col":0,"text":"# ...","unresolved":true,"watch":"tool-words"}
{"kind":"directive",         "action":"kept",   "line":13,"col":8,"text":"# noqa: E501","rule":"noqa"}
{"kind":"docstring",         "action":"removed","line":20,"end_line":31,"text":"\"\"\"...\"\"\"","owner":"Cart.add"}
{"kind":"doctest_docstring", "action":"kept",   "line":50,"end_line":70,"owner":"sympy.core.x.f"}
{"kind":"docstring",         "action":"kept",   "line":3,"end_line":3,"owner":"<module>","rule":"pytest-dont-rewrite"}
{"kind":"docstring",         "action":"kept",   "line":61,"end_line":66,"owner":"Basic","rule":"consumed"}
{"kind":"stray_string",      "action":"kept",   "line":90,"end_line":90}
{"kind":"parse_error",       "error":"..."}
{"kind":"stats","comments_removed":N,"docstrings_removed":N,"doctest_docstrings_kept":N,
 "docstrings_kept":N,"directives_kept":N,"stray_strings_kept":N,"unresolved":N,
 "lines_before":N,"lines_after":N,"bytes_before":N,"bytes_after":N,
 "keep_owners":[["Basic","consumed"],...]}      <- only when the context is non-empty
```
`line`/`end_line` are ORIGINAL 1-based line numbers. `text` is verbatim (docstring text may
be omitted for doctest/stray kinds to keep sidecars small; comments always carry text).
The `stats` record is always the LAST line.

## Pass-2 gate (per snapshot; any failure blocks the tag)

1. `astcheck.equal` on every stripped file.
2. Zero `unresolved` across the snapshot's sidecars.
3. Every test path byte-identical to base_commit.
4. Zero `parse_error` files, OR each is listed in the report (parse errors don't block; they
   are left unstripped and counted).
