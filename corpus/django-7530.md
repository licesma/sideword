# `django__django-7530`: why the empty patch scores resolved

**Verdict: (a) the instance is defective upstream; our harness is correct.**

SWE-bench Verified lists the wrong test as `FAIL_TO_PASS`. The test it names,
`test_squashmigrations_initial_attribute`, passes at `base_commit` and is untouched
by the `test_patch`. The test the `test_patch` actually changes,
`test_makemigrations_consistency_checks_respect_routers`, errors at base and passes
with the gold patch — the real fail-to-pass — but is on neither list. So any patch
that leaves the 59 `PASS_TO_PASS` tests green scores resolved, including no patch.
SWE-bench's own `run_evaluation` reports the same. The defect is filed upstream and
acknowledged by the maintainers (see "Prior reports").

Everything below was done on 2026-08-24 with `swebench` 4.1.0, the official image
`swebench/sweb.eval.x86_64.django_1776_django-7530:latest` (id `843450ff83f4`),
and nothing from `harness/` in the loop. No model was called.

## 1. Reproduce with nothing of ours

Pristine container, `/testbed` untouched. The image's HEAD is a build commit
sitting directly on `base_commit`:

```
HEAD          08b782086fecd4a72cb9a49a23c7d0264c80f5fc  "SWE-bench" <setup@swebench.com>
HEAD~1        f8fab6f90233c7114d642dfe01a4e6d4cb14ee7d  == dataset base_commit
```

That is normal SWE-bench layout (the eval script itself runs `git diff <base_commit>`
to show it). Python 3.5.6, Django `1.11.dev`, installed from `/testbed`.

The eval script came straight from `make_test_spec(row).eval_script` on the
HuggingFace row (saved as `/tmp/django-7530-eval.sh`, copied in, run as
`bash /eval.sh`). It resets `tests/migrations/test_commands.py` to `base_commit`,
applies the dataset's `test_patch`, and runs
`./tests/runtests.py --verbosity 2 --settings=test_sqlite --parallel 1 migrations.test_commands`.

**No patch applied** (`/tmp/django-7530-empty.log`):

```
Applied patch tests/migrations/test_commands.py cleanly.
test_makemigrations_consistency_checks_respect_routers (migrations.test_commands.MakeMigrationsTests) ... ERROR
test_squashmigrations_initial_attribute (migrations.test_commands.SquashMigrationsTests) ... ok
Ran 63 tests in 0.586s
FAILED (errors=1)
```

The one error:

```
  File "/testbed/tests/migrations/test_commands.py", line 650, in test_makemigrations_consistency_checks_respect_routers
    apps.get_app_config(app_name).get_model(call_kwargs['model_name'])
LookupError: App 'migrations2' doesn't have a 'ModelWithCustomBase' model.
```

That is exactly the bug the issue describes: at base, `makemigrations` calls
`allow_migrate()` with every model in the project for every app; the patched test
asserts each `(app_label, model_name)` pair is valid and blows up on the first
invalid one.

**Gold patch applied** in a second pristine container (`/tmp/django-7530-gold.log`):

```
Applied patch django/core/management/commands/makemigrations.py cleanly.
Applied patch tests/migrations/test_commands.py cleanly.
test_makemigrations_consistency_checks_respect_routers (migrations.test_commands.MakeMigrationsTests) ... ok
test_squashmigrations_initial_attribute (migrations.test_commands.SquashMigrationsTests) ... ok
Ran 63 tests in 0.539s
OK
```

Per-test outcome for every listed test, parsed with `swebench.harness.grading.get_logs_eval`:

| list | test | no patch | gold |
|---|---|---|---|
| FAIL_TO_PASS | `test_squashmigrations_initial_attribute (…SquashMigrationsTests)` | PASSED | PASSED |
| PASS_TO_PASS | all 59 entries | 59 PASSED, 0 failed | 59 PASSED, 0 failed |
| *not listed* | `test_makemigrations_consistency_checks_respect_routers (…MakeMigrationsTests)` | **ERROR** | PASSED |
| *not listed* | `test_ticket_23799_squashmigrations_no_optimize (…SquashMigrationsTests)` | PASSED | PASSED |

`get_eval_report` on the no-patch log: `resolved: True`, F2P 1/1, P2P 59/59.
The F2P test is genuinely executed and reported `ok` by unittest at verbosity 2 —
it is not skipped, and it is not a parser artefact: its source at base is a plain
squashmigrations-writes-`initial = True` check that has nothing to do with routers.
It was added to Django by `db97a88495` (Fixed #24375), long before this instance.

## 2. The dataset row vs `corpus/instances.json`

Fetched `django__django-7530` from `princeton-nlp/SWE-bench_Verified` the same way
`harness/instances.py` does (single parquet via `huggingface_hub`).

| field | dataset | ours | match |
|---|---|---|---|
| `base_commit` | `f8fab6f90233c7114d642dfe01a4e6d4cb14ee7d` | same | yes |
| `version` | `1.11` | `1.11` | yes |
| `FAIL_TO_PASS` | 1 entry, `test_squashmigrations_initial_attribute` | same | yes |
| `PASS_TO_PASS` | 59 entries | same 59 | yes |
| `test_patch` | touches only `tests/migrations/test_commands.py` | `test_patch_paths` = same | yes |
| `patch` | touches only `django/core/management/commands/makemigrations.py` | `patch_paths` = same | yes |

`corpus/instances.json` stores paths, not the diffs themselves; the harness reads the
diffs from the dataset at run time. Our copy is faithful. The defect is in the
dataset, not in our transcription of it.

The `test_patch` in the dataset edits **only**
`test_makemigrations_consistency_checks_respect_routers` (adds an
`@override_settings(INSTALLED_APPS=['migrations', 'migrations2'])` decorator and the
per-call validity assertions). It does not touch the test named in `FAIL_TO_PASS`.

## 3. SWE-bench's own harness

`swebench.harness.run_evaluation` refuses to evaluate a literally empty
`model_patch` (it goes to `empty_patch_ids` and is skipped, `run_evaluation.py`
lines 458-469), so the closest legal equivalent was used: a patch that adds one
comment line to `README.rst` and nothing else.

```
uv run --extra eval python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Verified --predictions_path preds.jsonl \
  --instance_ids django__django-7530 --run_id readme7530 --max_workers 1 --namespace swebench
```

Result (`/tmp/sb7530/readme-only.readme7530.json` and
`logs/run_evaluation/readme7530/readme-only/django__django-7530/report.json`):

```
Instances resolved: 1     Instances unresolved: 0
report: resolved: True, patch_successfully_applied: True
        FAIL_TO_PASS success: [test_squashmigrations_initial_attribute], failure: []
        PASS_TO_PASS success: 59, failure: []
test_output.txt: ...respect_routers ... ERROR / ...initial_attribute ... ok / Ran 63 tests / FAILED (errors=1)
```

The reference implementation reports **resolved** for a change that touches no code.
Our harness (`harness/evaluate.py`, `score()`) calls the same `make_test_spec` and
`get_eval_report`, runs the same test command in the same image, and only re-points
the two informational `git show` / `git diff` lines of the eval script. It agrees
with the reference because it *is* the reference on everything that decides an
outcome.

## 4. Mechanism

Not dependency drift, not a wrong checkout, not a skip. The `FAIL_TO_PASS` list
names a test that already passes at base and that the fix does not affect. The
real fail-to-pass test exists but is unlisted, so the grader never looks at it.
Why the original validation run recorded `test_squashmigrations_initial_attribute`
as failing-then-passing is not recoverable from here (the upstream issue does not
say either); what is established is that in the shipped image, with the shipped
eval script, it passes both before and after the gold patch.

A corrected copy exists: `codeset/SWE-bench_Verified` on HuggingFace carries the
same `base_commit` and `test_patch` for this instance but lists
`FAIL_TO_PASS = ["test_makemigrations_consistency_checks_respect_routers (migrations.test_commands.MakeMigrationsTests)"]`.
With that list, the no-patch run above would score unresolved (that test ERRORs)
and the gold run resolved.

## 5. Prior reports

- **SWE-bench/swe-bench-tasks#22** — "`django__django-7530` is missing test case",
  opened 2025-12-08, label `bug`, still open. Reports precisely this: the test patch
  lives entirely in `test_makemigrations_consistency_checks_respect_routers`, nothing
  checks it, "the models get a free passing example ... including no code change at
  all". Reproduced by the reporter with `run_evaluation` on gold and with the patch
  step disabled. Maintainer (ofirpress, 2026-03-12): "We'll push out the fix for this
  soon." No fix has landed in `princeton-nlp/SWE-bench_Verified` as of today.
  https://github.com/SWE-bench/swe-bench-tasks/issues/22
- **UKGovernmentBEIS/inspect_evals#36** — "Issues in SWE-bench scoring": lists
  `django__django-7530` as a false positive under *both* their implementation and the
  original SWE-bench implementation, i.e. resolved without a real fix.
  https://github.com/UKGovernmentBEIS/inspect_evals/issues/36
- **pan2013e/explainbench#5** — "Instances to exclude": includes `django__django-7530`.
  https://github.com/pan2013e/explainbench/issues/5

## What this means for the experiment

`corpus/admission.md` is right to exclude it: it cannot discriminate between arms,
and it says nothing about stripping or about our harness. The remaining 22 usable
instances are unaffected by this finding. If the instance is ever wanted back, the
fix is a one-line override of its `FAIL_TO_PASS` to the codeset value, applied
identically in all three arms — but that is a deviation from the published dataset
and should be recorded as such, not done silently.

## Artefacts (outside the repo, `/tmp`)

- `/tmp/django-7530-row.json` — the HuggingFace row
- `/tmp/django-7530-eval.sh` — `make_test_spec(...).eval_script`, unmodified
- `/tmp/django-7530-empty.log`, `/tmp/django-7530-gold.log` — pristine-container runs
- `/tmp/sb7530/` — `run_evaluation` predictions, report and logs
