# Converter pilot report (EST-111)

Generated 2026-08-18 17:21 · model `claude-opus-5` via headless Claude Code (`claude -p`, subscription) · resolver `sideword-resolver` · sample 100 blobs

**Runs on disk:** low 0/100, medium 100/100, high 0/100. Blocked-by-spend-limit files: {'low': 0, 'medium': 0, 'high': 0}. Runs are resumable (`convert_pilot.py run` skips finished blobs); rerun `score` after more runs land.

## Sample

| repo | blobs |
|---|---|
| astropy/astropy | 10 |
| django/django | 8 |
| matplotlib/matplotlib | 10 |
| mwaskom/seaborn | 7 |
| pallets/flask | 7 |
| psf/requests | 7 |
| pydata/xarray | 8 |
| pylint-dev/pylint | 8 |
| pytest-dev/pytest | 7 |
| scikit-learn/scikit-learn | 10 |
| sphinx-doc/sphinx | 8 |
| sympy/sympy | 10 |

| size bucket | blobs |
|---|---|
| small | 40 |
| medium | 40 |
| large | 20 |

Total 2,382,521 bytes, 6,509 documentation records (per file mean 65.09, median 30.0, max 418). Sample list: `corpus/convert-pilot/sample.json`.

## Calls

| effort | runs scored | runs retried | failed files |
|---|---|---|---|
| low | 0 | 0 | 0 |
| medium | 100 | 0 | 0 |
| high | 0 | 0 | 0 |

## Headline per effort

| effort | records | coverage ok | anchored | resolve=found (of anchored) | placement correct (of anchored) | placement correct (of all records) | lenient: + ambiguous with expected among candidates (of all) | unanchorable | false unanchorable (strict: unambiguous expected line has resolver anchors / any) | kind ok | found on orig only (not on stripped) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| low | 0 | 0.0% | 0.0% | n/a | n/a | 0.0% | 0.0% | 0.0% | 0 strict / 0 any | n/a | 0 |
| medium | 4344 | 100.0% | 100.0% | 95.7% | 95.5% | 95.5% | 98.2% | 0.0% | 0 strict / 0 any | 99.7% | 0 |
| high | 0 | 0.0% | 0.0% | n/a | n/a | 0.0% | 0.0% | 0.0% | 0 strict / 0 any | n/a | 0 |

Per-file (macro) view — accuracy = correct / records of that file:

| effort | files | macro mean acc | median acc | min acc | files at 100% | files >= 95% | macro mean unanchorable |
|---|---|---|---|---|---|---|---|
| medium | 100 | 94.4% | 100.0% | 20.0% | 54 | 73 | 0.0% |

Worst files per effort (accuracy = correct / records):

| effort | path | records | correct | unanchorable | acc |
|---|---|---|---|---|---|
| medium | examples/text_labels_and_annotations/annotation_demo.py | 25 | 5 | 0 | 20.0% |
| medium | tutorials/introductory/animation_tutorial.py | 7 | 4 | 0 | 57.1% |
| medium | examples/cluster/plot_digits_linkage.py | 5 | 3 | 0 | 60.0% |
| medium | examples/compose/plot_compare_reduction.py | 11 | 7 | 0 | 63.6% |
| medium | requests/__init__.py | 6 | 4 | 0 | 66.7% |
| medium | pylint/extensions/redefined_loop_name.py | 3 | 2 | 0 | 66.7% |

Resolver status of anchored records:

| effort | found | unverified | ambiguous | missing | malformed | resolver-error |
|---|---|---|---|---|---|---|
| low | 0 | 0 | 0 | 0 | 0 | 0 |
| medium | 4157 | 0 | 121 | 65 | 0 | 0 |
| high | 0 | 0 | 0 | 0 | 0 | 0 |

## Placement accuracy per record kind (per effort)

| record kind | effort | records | anchored | unanch. | dropped | found | correct | acc (of anchored) | acc (of records) | wrong place | ambiguous | missing | malformed | unverified | kind ok | expected-ambiguous |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| comment-full-line | medium | 2133 | 2132 | 1 | 0 | 1978 | 1970 | 92.4% | 92.4% | 8 | 101 (99 hit) | 53 | 0 | 0 | 99.6% | 0 |
| comment-todo | medium | 89 | 89 | 0 | 0 | 82 | 81 | 91.0% | 91.0% | 1 | 3 (3 hit) | 4 | 0 | 0 | 94.4% | 0 |
| comment-trailing | medium | 604 | 604 | 0 | 0 | 580 | 580 | 96.0% | 96.0% | 0 | 16 (16 hit) | 8 | 0 | 0 | 100.0% | 404 |
| docstring | medium | 1373 | 1373 | 0 | 0 | 1372 | 1372 | 99.9% | 99.9% | 0 | 1 (1 hit) | 0 | 0 | 0 | 100.0% | 0 |
| doctest_docstring | medium | 132 | 132 | 0 | 0 | 132 | 132 | 100.0% | 100.0% | 0 | 0 (0 hit) | 0 | 0 | 0 | 100.0% | 0 |
| stray_string | medium | 13 | 13 | 0 | 0 | 13 | 13 | 100.0% | 100.0% | 0 | 0 (0 hit) | 0 | 0 | 0 | 100.0% | 13 |

## Placement accuracy per anchor depth

| depth | effort | anchored | found | correct | acc | ambiguous | missing | malformed |
|---|---|---|---|---|---|---|---|---|
| symbol | low | 0 | 0 | 0 | n/a | 0 | 0 | 0 |
| symbol | medium | 1786 | 1783 | 1782 | 99.8% | 1 | 2 | 0 |
| symbol | high | 0 | 0 | 0 | n/a | 0 | 0 | 0 |
| 1-seg | low | 0 | 0 | 0 | n/a | 0 | 0 | 0 |
| 1-seg | medium | 1491 | 1391 | 1388 | 93.1% | 95 | 5 | 0 |
| 1-seg | high | 0 | 0 | 0 | n/a | 0 | 0 | 0 |
| 2+seg | low | 0 | 0 | 0 | n/a | 0 | 0 | 0 |
| 2+seg | medium | 1066 | 983 | 978 | 91.7% | 25 | 58 | 0 |
| 2+seg | high | 0 | 0 | 0 | n/a | 0 | 0 | 0 |

## Placement accuracy per last segment kind (effort low)

| last kind | anchored | found | correct | acc | ambiguous | missing | malformed |
|---|---|---|---|---|---|---|---|

## Kind prediction (expected -> predicted, counts)

| expected->predicted | low | medium | high |
|---|---|---|---|
| doc->doc | 0 | 1518 | 0 |
| lead->lead | 0 | 2114 | 0 |
| lead->post | 0 | 4 | 0 |
| post->lead | 0 | 5 | 0 |
| post->post | 0 | 9 | 0 |
| todo->lead | 0 | 3 | 0 |
| todo->todo | 0 | 84 | 0 |
| todo->trail | 0 | 2 | 0 |
| trail->trail | 0 | 604 | 0 |

## Tokens and latency per call (mean / median / p90 / total)

| effort | calls | input (file+prompt, uncached = input+cache_creation) | cache_read (CC overhead + system prompt) | output | thinking | duration_ms/1000 (s) | wall (s) | nominal cost USD (opus only) |
|---|---|---|---|---|---|---|---|---|
| low | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| medium | 100 | 16,606 / 11,601 / 39,823 / 1,660,638 | 8,382 / 8,338 / 8,338 / 838,223 | 4,082 / 1,354 / 9,838 / 408,214 | 2,024 / 632 / 5,515 / 202,357 | 37.8 / 14.6 / 89.1 / 3,777.6 | 40.1 / 17.3 / 90.9 / 4,008.6 | 0.272 / 0.163 / 0.709 / 27.230 |
| high | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

| effort | input tokens per KB (pooled) | input tokens per KB per file (mean/median/p90/sum) | output tokens per record (pooled) | output tokens per record per file | duration_api (s) |
|---|---|---|---|---|---|
| low | 0 | n/a | 0.0 | n/a | n/a |
| medium | 714 | 1,382 / 827 / 2,322 / 138,161 | 94.0 | 93.2 / 89.7 / 141.3 / 9,321.8 | 39.0 / 15.7 / 90.3 / 3,896.1 |
| high | 0 | n/a | 0.0 | n/a | n/a |

Projection per 1,000 files of this size mix (mean per call x 1000):

| effort | input tokens | cache_read tokens | output tokens | thinking tokens | nominal USD | wall hours at 1 call at a time |
|---|---|---|---|---|---|---|
| medium | 16,606,380 | 8,382,230 | 4,082,140 | 2,023,570 | 272 | 11.1 |

| effort | num_turns distribution | calls with cache_read > 20k |
|---|---|---|
| low | {} | 0 |
| medium | {2: 97, 3: 3} | 3 |
| high | {} | 0 |

Notes: `input` = `usage.input_tokens + usage.cache_creation_input_tokens` (the file, records, schema, and — on the first calls — the system prompt before it was cached). `cache_read` is the byte-identical system prompt (FORMAT.md + contract) plus Claude Code's own fixed overhead, read from cache. Costs are nominal API prices reported by the CLI; nothing was billed (subscription).

## Three-way agreement across efforts

| metric | count | rate |
|---|---|---|
| records with all three efforts | 0 |  |
| 3-way agreement (same anchor or same non-anchor verdict) | 0 | 0.0% |
| 3-way agreement AND placement correct at high | 0 | 0.0% |
| all three differ | 0 | 0.0% |

Pairwise (on records that have both runs):

| pair | records | same anchor | rate | same and correct (2nd) | differ: 1st correct, 2nd not | differ: 2nd correct, 1st not |
|---|---|---|---|---|---|---|
| low-medium | 0 | 0 | n/a | 0 | 0 | 0 |
| medium-high | 0 | 0 | n/a | 0 | 0 | 0 |
| low-high | 0 | 0 | n/a | 0 | 0 | 0 |

## Failure patterns (all efforts pooled; see failures.md)

### unanchorable (1)

| pattern | count | low | medium | high |
|---|---|---|---|---|
| inside a multi-line expression (condition / call args) | 1 | 0 | 1 | 0 |

### malformed (0)

none

### missing (65)

| pattern | count | low | medium | high |
|---|---|---|---|---|
| segment `assign` names nothing under a resolved prefix (residual) | 22 | 0 | 22 | 0 |
| segment `return` names nothing under a resolved prefix (residual) | 8 | 0 | 8 | 0 |
| segment `if` names nothing under a resolved prefix (residual) | 7 | 0 | 7 | 0 |
| segment `arg` names nothing under a resolved prefix (residual) | 7 | 0 | 7 | 0 |
| segment `item` names nothing under a resolved prefix (residual) | 5 | 0 | 5 | 0 |
| segment `else` names nothing under a resolved prefix (residual) | 4 | 0 | 4 | 0 |
| symbol path names nothing (attribute/import/local name/typo) | 2 | 0 | 2 | 0 |
| segment `elif` names nothing under a resolved prefix (residual) | 2 | 0 | 2 | 0 |
| segment `key` names nothing under a resolved prefix (residual) | 2 | 0 | 2 | 0 |
| segment `raise` names nothing under a resolved prefix (residual) | 1 | 0 | 1 | 0 |
| resolver discriminator contains a comment or backslash continuation (resolver hazard: raw source) | 1 | 0 | 1 | 0 |
| segment `break` names nothing under a resolved prefix (residual) | 1 | 0 | 1 | 0 |
| segment `continue` names nothing under a resolved prefix (residual) | 1 | 0 | 1 | 0 |
| segment `call` names nothing under a resolved prefix (residual) | 1 | 0 | 1 | 0 |
| segment `for` names nothing under a resolved prefix (residual) | 1 | 0 | 1 | 0 |

### ambiguous (121)

| pattern | count | low | medium | high |
|---|---|---|---|---|
| segment `assign` needs ~n | 63 | 0 | 63 | 0 |
| segment `call` needs ~n | 20 | 0 | 20 | 0 |
| segment `if` needs ~n | 12 | 0 | 12 | 0 |
| segment `try` needs ~n | 11 | 0 | 11 | 0 |
| segment `arg` needs ~n | 7 | 0 | 7 | 0 |
| segment `import` needs ~n | 3 | 0 | 3 | 0 |
| segment `for` needs ~n | 2 | 0 | 2 | 0 |
| segment `return` needs ~n | 1 | 0 | 1 | 0 |
| segment `pass` needs ~n | 1 | 0 | 1 | 0 |
| symbol path (F1/F2 rebinding) | 1 | 0 | 1 | 0 |

### wrong_place (9)

| pattern | count | low | medium | high |
|---|---|---|---|---|
| lead comment attached to a distant statement | 5 | 0 | 5 | 0 |
| hoisted to the enclosing statement (comment sits on an element inside it) | 3 | 0 | 3 | 0 |
| symbol anchor for a comment (points at first binding / definition) | 1 | 0 | 1 | 0 |

### dropped (0)

none

### kind_mismatch (14)

| pattern | count | low | medium | high |
|---|---|---|---|---|
| post -> lead | 5 | 0 | 5 | 0 |
| lead -> post | 4 | 0 | 4 | 0 |
| todo -> lead | 3 | 0 | 3 | 0 |
| todo -> trail | 2 | 0 | 2 | 0 |

## Prompt template

System prompt (byte-identical for every call; `corpus/convert-pilot/system-prompt.txt`) = the full text of `FORMAT.md` + `---` + the contract below.

```
# Task

You name anchors for documentation records of a Python file. Anchors follow the grammar above
exactly. Output only JSON matching the schema. For each record give the anchor (verbatim grammar,
discriminators copied from source text with whitespace normalized as the spec says) and the kind
(doc|lead|trail|todo|post). If no anchor in the grammar can name a record, put it in unanchorable with a
one-line reason. Never invent anchor kinds. Never quote or rewrite the record text.

Conventions that follow from the spec:
- Every record id (r1..rN) must appear exactly once, either in `anchors` or in `unanchorable`.
- A docstring / doctest docstring record has kind `doc` and its anchor is the symbol that owns it
  (`<module>`, `Cart`, `Cart.add`); a stray string documents the statement just above it.
- A comment on its own line has kind `lead` (or `todo` if it starts with TODO/FIXME/XXX/HACK) and
  is anchored to the statement it sits above; a comment at the end of a code line has kind `trail`
  (or `todo`) and is anchored to that statement.
- A comment block with no statement after it — the end of a file, or the end of the block it
  closes — has kind `post` and is anchored to the statement it follows.
- A record is a comment *block*, not a line: consecutive comment lines arrive as one record
  (`[comment block, lines 124–136, ...]`) and take one anchor and one kind.
- Statements at module level are anchored as `<module>#...` (e.g. `<module>#import:os`,
  `<module>#if:__name__=="__main__"`); statements inside a function or method as
  `Class.method#...`; module and class variables as symbols (`MAX_TOKENS`, `Cart.total`).
- The user prompt shows the file with 1-based line numbers (`   12| code`) followed by the records.
```

User prompt (`corpus/convert-pilot/prompts/<sha>.txt`):

```
\
File: <path>  (repo <owner/name>)

```
    1| <line 1 of the ORIGINAL file>
    2| <line 2>
  ...
```

Records (<N>):
r1 [comment, line 40, col 4] # verbatim comment text
r2 [docstring, lines 20–31, owner Cart.add] """first content line of the docstring
r3 [doctest_docstring (kept in source), lines 50–70, owner f] """first content line
r4 [stray_string (kept in source), line 90] """first content line
```

Command:

```
env -i HOME=$HOME PATH=/usr/bin:/bin:/Users/esteban/.nvm/versions/node/v20.19.5/bin USER=$USER TERM=dumb \
  claude -p --model claude-opus-5 --effort <effort> --system-prompt-file /Users/esteban/repos/sideword/corpus/convert-pilot/system-prompt.txt --no-session-persistence --output-format json --tools  --json-schema '{"type":"object","properties":{"anchors":{"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"anchor":{"type":"string"},"kind":{"type":"string","enum":["doc","lead","trail","todo","post"]}},"required":["id","anchor","kind"],"additionalProperties":false}},"unanchorable":{"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"reason":{"type":"string"}},"required":["id","reason"],"additionalProperties":false}}},"required":["anchors","unanchorable"],"additionalProperties":false}'  < prompts/<sha>.txt
```
