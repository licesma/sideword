# Converter pilot report (EST-111)

Generated 2026-08-18 18:57 · model `claude-opus-5` via headless Claude Code (`claude -p`, subscription) · resolver `sideword-resolver` · sample 100 blobs

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
| medium | 100 | 1 | 0 |
| high | 0 | 0 | 0 |

## Headline per effort

**Placement here is the strict number: it excludes every record that only resolved because of the model's line hint.** Those are counted on their own below. Scoring them as placement would be circular — the model is handed each record's position in the prompt, hands a line back, and the expected line is derived from the same record, so the comparison mostly measures copying, not anchoring.

| effort | records | coverage ok | anchored | resolve=found (of anchored, incl. position-disambiguated) | placement correct (of anchored, EXCL. position) | placement correct (of records, EXCL. position) | position-disambiguated (own bucket, not in the two columns left of this) | lenient: all correct incl. position + ambiguous with expected among candidates (of all) | unanchorable | false unanchorable (strict: unambiguous expected line has resolver anchors / any) | kind ok | found on orig only (not on stripped) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| low | 0 | 0.0% | 0.0% | n/a | n/a | 0.0% | 0 (0.0%) | 0.0% | 0.0% | 0 strict / 0 any | n/a | 0 |
| medium | 4344 | 100.0% | 100.0% | 98.0% | 97.8% | 97.8% | 140 (3.2%) | 97.8% | 0.0% | 0 strict / 0 any | 99.7% | 0 |
| high | 0 | 0.0% | 0.0% | n/a | n/a | 0.0% | 0 (0.0%) | 0.0% | 0.0% | 0 strict / 0 any | n/a | 0 |

## Position disambiguation (§1.5)

Ties are derived, never authored: two textually identical siblings cannot be told apart by any anchor an author could write. Every anchor now carries the line the model says it names; the resolver uses it *only* when the anchor is `Ambiguous`, and marks the outcome `disambiguated_by: "position"` so it never merges with an unambiguous hit.

| effort | anchored | resolved by position | share of anchored | still ambiguous (no usable hint) | expected among candidates | candidate-set hit rate (anchor work) | hint agreed with expected | hint disagreed with expected | agreement rate (CIRCULAR — see below) | mean candidates |
|---|---|---|---|---|---|---|---|---|---|---|
| medium | 4343 | 140 | 3.2% | 0 | 138 | 98.6% | 138 | 2 | 98.6% | 4.2 |

Two different things in that table, and only one of them is honest evidence about the model.

**Candidate-set hit rate is anchor work.** It asks whether the expected line was among the siblings the anchor named at all — that is the anchor naming the right family, and no line hint can fake it. Read this one.

**Agreement rate is circular. Do not read it as accuracy.** The line came from the model and the expected line is derived from the same record, so agreement mostly says the model copied the number the prompt showed it. Picking *which* sibling of a correctly named family is the hint's job, not the anchor's. The feature's real payoff is the coverage column — records that stop being unresolvable ambiguities — with the strict placement number above left untouched by it.

Line-weighted placement (one unit per physical comment line, excluding position-disambiguated records on both sides):

| effort | comment lines (excl. position) | correct | rate |
|---|---|---|---|
| medium | 6039 | 5881 | 97.4% |

Per-file (macro) view — accuracy = correct / records of that file. `strict` drops position-disambiguated records from both sides; the plain column keeps them and is the circular one:

| effort | files | macro mean acc (strict) | median acc (strict) | macro mean acc (incl. position) | median acc (incl. position) | min acc | files at 100% (incl. position) | files >= 95% (incl. position) | macro mean unanchorable |
|---|---|---|---|---|---|---|---|---|---|
| medium | 100 | 98.1% | 100.0% | 98.3% | 100.0% | 66.7% | 74 | 90 | 0.0% |

Worst files per effort (accuracy = correct / records):

| effort | path | records | correct | unanchorable | acc |
|---|---|---|---|---|---|
| medium | examples/layered_bivariate_plot.py | 3 | 2 | 0 | 66.7% |
| medium | examples/user_interfaces/gtk3_spreadsheet_sgskip.py | 6 | 5 | 0 | 83.3% |
| medium | sympy/core/mul.py | 184 | 154 | 0 | 83.7% |
| medium | pylint/utils/utils.py | 23 | 20 | 0 | 87.0% |
| medium | xarray/util/print_versions.py | 9 | 8 | 0 | 88.9% |
| medium | seaborn/_oldcore.py | 184 | 167 | 0 | 90.8% |

Resolver status of anchored records:

| effort | found | unverified | ambiguous | missing | malformed | resolver-error |
|---|---|---|---|---|---|---|
| low | 0 | 0 | 0 | 0 | 0 | 0 |
| medium | 4256 | 0 | 0 | 87 | 0 | 0 |
| high | 0 | 0 | 0 | 0 | 0 | 0 |

## Placement accuracy per record kind (per effort)

| record kind | effort | records | anchored | unanch. | dropped | found | correct (excl. position) | acc (of anchored, excl. position) | acc (of records, excl. position) | position-disambiguated | wrong place | ambiguous | missing | malformed | unverified | kind ok | expected-ambiguous |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| comment-full-line | medium | 2133 | 2132 | 1 | 0 | 2064 | 1944 | 96.3% | 96.3% | 114 (112 agreed) | 6 | 0 (0 hit) | 68 | 0 | 0 | 99.7% | 0 |
| comment-todo | medium | 89 | 89 | 0 | 0 | 86 | 81 | 96.4% | 96.4% | 5 (5 agreed) | 0 | 0 (0 hit) | 3 | 0 | 0 | 92.1% | 0 |
| comment-trailing | medium | 604 | 604 | 0 | 0 | 588 | 572 | 97.3% | 97.3% | 16 (16 agreed) | 0 | 0 (0 hit) | 16 | 0 | 0 | 100.0% | 404 |
| docstring | medium | 1373 | 1373 | 0 | 0 | 1373 | 1369 | 100.0% | 100.0% | 4 (4 agreed) | 0 | 0 (0 hit) | 0 | 0 | 0 | 100.0% | 0 |
| doctest_docstring | medium | 132 | 132 | 0 | 0 | 132 | 131 | 100.0% | 100.0% | 1 (1 agreed) | 0 | 0 (0 hit) | 0 | 0 | 0 | 100.0% | 0 |
| stray_string | medium | 13 | 13 | 0 | 0 | 13 | 13 | 100.0% | 100.0% | 0 (0 agreed) | 0 | 0 (0 hit) | 0 | 0 | 0 | 100.0% | 13 |

## Placement accuracy per anchor depth

| depth | effort | anchored | found | correct (excl. position) | acc (excl. position) | position-disambiguated | ambiguous | missing | malformed |
|---|---|---|---|---|---|---|---|---|---|
| symbol | low | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| symbol | medium | 1792 | 1789 | 1783 | 99.8% | 5 | 0 | 3 | 0 |
| symbol | high | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| 1-seg | low | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| 1-seg | medium | 1485 | 1480 | 1371 | 99.4% | 106 | 0 | 5 | 0 |
| 1-seg | high | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| 2+seg | low | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |
| 2+seg | medium | 1066 | 987 | 956 | 92.2% | 29 | 0 | 79 | 0 |
| 2+seg | high | 0 | 0 | 0 | n/a | 0 | 0 | 0 | 0 |

## Placement accuracy per last segment kind (effort low)

| last kind | anchored | found | correct (excl. position) | acc (excl. position) | position-disambiguated | ambiguous | missing | malformed |
|---|---|---|---|---|---|---|---|---|

## Kind prediction (expected -> predicted, counts)

| expected->predicted | low | medium | high |
|---|---|---|---|
| doc->doc | 0 | 1518 | 0 |
| lead->lead | 0 | 2116 | 0 |
| lead->post | 0 | 2 | 0 |
| post->lead | 0 | 5 | 0 |
| post->post | 0 | 9 | 0 |
| todo->lead | 0 | 3 | 0 |
| todo->post | 0 | 1 | 0 |
| todo->todo | 0 | 82 | 0 |
| todo->trail | 0 | 3 | 0 |
| trail->trail | 0 | 604 | 0 |

## Tokens and latency per call (mean / median / p90 / total)

| effort | calls | input (file+prompt, uncached = input+cache_creation) | cache_read (CC overhead + system prompt) | output | thinking | duration_ms/1000 (s) | wall (s) | nominal cost USD (opus only) |
|---|---|---|---|---|---|---|---|---|
| low | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| medium | 100 | 15,993 / 11,142 / 37,876 / 1,599,263 | 9,240 / 8,563 / 8,563 / 924,031 | 4,324 / 1,608 / 11,737 / 432,438 | 2,107 / 792 / 5,294 / 210,654 | 39.0 / 17.4 / 98.8 / 3,901.3 | 40.4 / 18.9 / 99.8 / 4,041.3 | 0.273 / 0.166 / 0.727 / 27.265 |
| high | 0 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

| effort | input tokens per KB (pooled) | input tokens per KB per file (mean/median/p90/sum) | output tokens per record (pooled) | output tokens per record per file | duration_api (s) |
|---|---|---|---|---|---|
| low | 0 | n/a | 0.0 | n/a | n/a |
| medium | 687 | 1,376 / 827 / 2,322 / 137,565 | 99.5 | 98.3 / 93.9 / 141.8 / 9,829.0 | 40.2 / 18.6 / 100.2 / 4,021.9 |
| high | 0 | n/a | 0.0 | n/a | n/a |

Projection per 1,000 files of this size mix (mean per call x 1000):

| effort | input tokens | cache_read tokens | output tokens | thinking tokens | nominal USD | wall hours at 1 call at a time |
|---|---|---|---|---|---|---|
| medium | 15,992,630 | 9,240,310 | 4,324,380 | 2,106,540 | 273 | 11.2 |

| effort | num_turns distribution | calls with cache_read > 20k |
|---|---|---|
| low | {} | 0 |
| medium | {2: 97, 3: 3} | 4 |
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

### missing (87)

| pattern | count | low | medium | high |
|---|---|---|---|---|
| segment `assign` names nothing under a resolved prefix (residual) | 30 | 0 | 30 | 0 |
| segment `return` names nothing under a resolved prefix (residual) | 10 | 0 | 10 | 0 |
| segment `if` names nothing under a resolved prefix (residual) | 10 | 0 | 10 | 0 |
| segment `elif` names nothing under a resolved prefix (residual) | 7 | 0 | 7 | 0 |
| segment `arg` names nothing under a resolved prefix (residual) | 5 | 0 | 5 | 0 |
| segment `item` names nothing under a resolved prefix (residual) | 4 | 0 | 4 | 0 |
| segment `else` names nothing under a resolved prefix (residual) | 3 | 0 | 3 | 0 |
| segment `call` names nothing under a resolved prefix (residual) | 3 | 0 | 3 | 0 |
| symbol path names nothing (attribute/import/local name/typo) | 3 | 0 | 3 | 0 |
| segment `for` names nothing under a resolved prefix (residual) | 2 | 0 | 2 | 0 |
| segment `assert` names nothing under a resolved prefix (residual) | 2 | 0 | 2 | 0 |
| segment `key` names nothing under a resolved prefix (residual) | 2 | 0 | 2 | 0 |
| segment `while` names nothing under a resolved prefix (residual) | 1 | 0 | 1 | 0 |
| callee is itself a call: `call:getattr` vs resolver `call:getattr(...)` | 1 | 0 | 1 | 0 |
| tuple target: model named the first target only / resolver keeps trailing comma | 1 | 0 | 1 | 0 |
| resolver discriminator contains a comment or backslash continuation (resolver hazard: raw source) | 1 | 0 | 1 | 0 |
| segment `break` names nothing under a resolved prefix (residual) | 1 | 0 | 1 | 0 |
| segment `try` names nothing under a resolved prefix (residual) | 1 | 0 | 1 | 0 |

### ambiguous (0)

none

### wrong_place (6)

| pattern | count | low | medium | high |
|---|---|---|---|---|
| lead comment attached to a distant statement | 3 | 0 | 3 | 0 |
| hoisted to the enclosing statement (comment sits on an element inside it) | 2 | 0 | 2 | 0 |
| symbol anchor for a comment (points at first binding / definition) | 1 | 0 | 1 | 0 |

### wrong_place_by_position (2)

| pattern | count | low | medium | high |
|---|---|---|---|---|
| lead comment attached to a distant statement | 2 | 0 | 2 | 0 |

### dropped (0)

none

### kind_mismatch (14)

| pattern | count | low | medium | high |
|---|---|---|---|---|
| post -> lead | 5 | 0 | 5 | 0 |
| todo -> trail | 3 | 0 | 3 | 0 |
| todo -> lead | 3 | 0 | 3 | 0 |
| lead -> post | 2 | 0 | 2 | 0 |
| todo -> post | 1 | 0 | 1 | 0 |

## Prompt template

System prompt (byte-identical for every call; `corpus/convert-pilot/system-prompt.txt`) = the full text of `FORMAT.md` + `---` + the contract below.

```
# Task

You name anchors for documentation records of a Python file. Anchors follow the grammar above
exactly. Output only JSON matching the schema. For each record give the anchor (verbatim grammar,
discriminators copied from source text with whitespace normalized as the spec says), the kind
(doc|lead|trail|todo|post) and the line. If no anchor in the grammar can name a record, put it in
unanchorable with a one-line reason. Never invent anchor kinds. Never quote or rewrite the record text.

`line` is the 1-based line number of the thing the anchor names — the statement, definition,
parameter or element the record documents — NOT the line the comment or docstring itself sits on
(for a `lead` comment those differ; for a `trail` comment they are the same line). It is a position
hint only: it never changes what the anchor text has to say, and an anchor that names the right
thing is still required. Its one job is §1.5. Ties are derived, never authored, so when two
textually identical siblings both match your anchor, no anchor text can say which you meant; the
line does, and the resolver assigns the `~n` from it. Still write the untied anchor.

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
  claude -p --model claude-opus-5 --effort <effort> --system-prompt-file /Users/esteban/repos/sideword/corpus/convert-pilot/system-prompt.txt --no-session-persistence --output-format json --tools  --json-schema '{"type":"object","properties":{"anchors":{"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"anchor":{"type":"string"},"kind":{"type":"string","enum":["doc","lead","trail","todo","post"]},"line":{"type":"integer"}},"required":["id","anchor","kind","line"],"additionalProperties":false}},"unanchorable":{"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"reason":{"type":"string"}},"required":["id","reason"],"additionalProperties":false}}},"required":["anchors","unanchorable"],"additionalProperties":false}'  < prompts/<sha>.txt
```
