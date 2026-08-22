# Round trip: original -> strip -> artifacts -> reconstruct

100 blobs, 4199 documentation records, 71 of them tied on an (anchor, kind) slot.

| check | files | share |
|---|---:|---:|
| byte-exact | 36 | 36% |
| code identical after re-strip | 85 | 85% |
| code identical ignoring blank lines | 100 | 100% |
| every record preserved | 100 | 100% |
| no record dropped unreported | 100 | 100% |
| exact once the format's own normalisations are allowed | 43 | 43% |

## Why the rest differ

Each file counted once, under the worst thing in its diff.

| primary cause | files |
|---|---:|
| blank-line placement | 36 |
| content differs | 13 |
| pass ambiguity | 8 |
| trailing comment gap | 3 |
| comment marker spacing | 3 |
| docstring quote style | 1 |

Every reason seen anywhere in a diff (a file can appear in several rows):

| reason | files |
|---|---:|
| blank-line placement | 50 |
| comment marker spacing | 19 |
| content differs | 13 |
| trailing comment gap | 10 |
| docstring quote style | 8 |
| pass ambiguity | 8 |
| comment indent | 4 |
| whitespace | 1 |

## What the format normalises away

| record property | records |
|---|---:|
| trail-gap | 412 |
| no-space-after-hash | 252 |
| docstring-quotes | 46 |
| comment-indent | 19 |
| hoisted-from-continuation | 5 |
| hoisted-from-expression | 2 |

## Files that lost something

| file | lost | added | code |
|---|---:|---:|---|
| sympy/core/mul.py | 0 | 0 | CHANGED |
| sklearn/linear_model/_glm/_newton_solver.py | 0 | 0 | CHANGED |
| examples/text_labels_and_annotations/annotation_demo.py | 0 | 0 | CHANGED |
| django/contrib/gis/geos/prototypes/coordseq.py | 0 | 0 | CHANGED |
| sphinx/ext/autosummary/__init__.py | 0 | 0 | CHANGED |
| script/bump_changelog.py | 0 | 0 | CHANGED |
| pylint/utils/file_state.py | 0 | 0 | CHANGED |
| pylint/checkers/variables.py | 0 | 0 | CHANGED |
| pylint/lint/pylinter.py | 0 | 0 | CHANGED |
| xarray/core/accessor_str.py | 0 | 0 | CHANGED |
| src/_pytest/pathlib.py | 0 | 0 | CHANGED |
| requests/packages/chardet/euctwfreq.py | 0 | 0 | CHANGED |
| requests/packages/chardet/euckrfreq.py | 0 | 0 | CHANGED |
| seaborn/relational.py | 0 | 0 | CHANGED |
| seaborn/_oldcore.py | 0 | 0 | CHANGED |
