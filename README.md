# Sideword

Python source stored separately from its documentation.

Each file becomes three things: clean `.py` source, a small index naming which
symbols are documented, and the documentation itself. Docs attach to semantic
anchors — functions, classes, variables, parameters — not line numbers. The
grammar is `FORMAT.md`; the evidence behind it is `FINDINGS.md`.

## Setup

**Build the resolver first.** The Python harness shells out to the compiled
binary for every anchor lookup, so its test suite fails without it.

The resolver is Rust, edition 2024, and needs toolchain **1.95 or newer** — a
distro `rustc` is usually too old:

```sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cargo build --release -p sideword-resolver
cargo test -p sideword-resolver   # 37 tests
```

Then Python. 3.14 is required, and a system 3.9/3.10 will fail at import; `uv`
supplies it without touching the system interpreter.

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --frozen                 # installs CPython 3.14 and 2 dependencies
uv run python -m unittest discover -s harness/tests -t .    # 251 tests
```

## What is here

| | |
|---|---|
| `FORMAT.md` | the anchor grammar, v1.1 |
| `FINDINGS.md` | what real code did to v0, and what v1 changed in response |
| `crates/resolver` | enumerates every anchor a file admits; anchors resolve by lookup |
| `harness/strip.py` | removes comments and docstrings, byte-exactly, with a sidecar |
| `harness/anchoring.py` | anchors each record from the position it occupied |
| `harness/sidedoc.py`, `inline.py` | write the two artifacts, and read them back |
| `harness/roundtrip.py` | original → strip → artifacts → reconstruct, verified |
| `harness/migrate.py` | convert a whole repository |
| `harness/convert_pilot.py`, `convert_corpus.py` | the model converter and its accounting |
| `harness/model_bench.py` | score any model against the same blobs, mechanically |
| `harness/sideword_cli.py` | the `sideword` command — arm 2's retrieval surface |
| `harness/evaluate.py` | one instance, one arm, one model: run, extract, score, record |
| `cache/*.anchors.json` | 5,448 blobs converted by Opus 5 — anchors and kinds only |

## What is not here

Two things are too large or regenerable for version control, and the corpus work
needs both:

* **The upstream mirror**, ~1.7 GB — twelve repositories at the base commit of
  every instance. Build with `harness/mirror.py`, or copy it.
* **The strip cache**, ~280 MB — one stripped source and one sidecar per blob.
  Rebuild with `harness/pass1.py` (hours), or copy it.

`cache/*.anchors.json` *is* tracked, deliberately: it is 16 MB, it cost $815 of
model time, and it cannot be regenerated for free.

## Converting a repository

No model is required. Comments already sit beside what they describe, so the
anchor is a parse and a lookup:

```sh
uv run python -m harness.migrate <repo> --out <dir>   # or --check to verify only
```

Two invariants gate every write, and a file failing either is left untouched:
the clean source is AST-equal to the original with the `# noqa` family intact,
and no documentation block goes missing without being reported. Over the
11,609-blob corpus that leaves 11 of 239,698 records unanchorable, no code
changed, and no prose lost.

What this cannot do is decide that a comment written inside a function body is
*about* the function rather than the statement it precedes. That judgement is
what a model adds, and `FORMAT.md`'s own metric does not measure it.

## Running the experiment

`harness/evaluate.py` is one instance, one arm, one model. It needs Docker, the
corpus mirror, and two pinned packages that the rest of the repository does not:

```sh
uv sync --extra eval          # mini-swe-agent 2.4.6 and swebench 4.1.0
export SIDEWORD_CLAUDE_CONFIG_DIR=$HOME/.claude2   # which account to bill
uv run --extra eval python -m harness.evaluate \
    --instance pallets__flask-5014 --arm sw --model claude-opus-5
```

`--arm` is `orig` (the base commit), `sw` (stripped plus `.sideword/`) or `nc`
(stripped, no docs). The record lands in
`corpus/eval/<model>/<arm>/<instance_id>.json`.

Three ways to run it without calling a model:

```sh
--dry-run            # container up, tree verified, sideword probed, then stop
--score-only gold    # score the instance's own patch, re-derived for the arm
--score-only empty   # score nothing at all
--script <file.json> # replay recorded assistant turns through the whole loop
```

`gold` and `empty` are the arm's validity check, and they exit non-zero when the
answer is wrong: an arm whose own patch does not resolve is an arm that cannot
measure anything, and an instance whose tests pass unpatched cannot either. Both
happen — see the module docstring.
