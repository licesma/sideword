# Prompt caching in the converter (EST-130)

Measured 2026-08-20 against `claude` 2.1.238, `claude-opus-5`, effort `medium`, on the
`~/.claude2` account. 50 controlled model calls, $1.79 total.

## Verdict

**The cached prefix already survives across separate `claude -p` invocations.** In the
5,094-call corpus run, 4,635 calls (91%) read exactly 8,563 cached tokens and only 11
read zero. `--no-session-persistence` is not the problem; a fresh session per call is
not the problem. The premise behind the ~47% figure — "the spec is re-cached every
call" — is false. The 5,451-token median `cache_creation` is not the system prompt; it
is the per-file user prompt plus a fixed 2,852-token block of `CLAUDE.md` and project
auto-memory that Claude Code appends *after* the cached prefix.

**But ~33% is reachable, from two other things**, both verified end to end:

| Lever | Saving / call | % of the $0.160 bill | Over 5,094 calls |
|---|---:|---:|---:|
| `FORCE_PROMPT_CACHING_5M=1` — stop paying 1-hour-TTL write prices | $0.0357 | 22.3% | $182 |
| `--safe-mode` — keep `CLAUDE.md` + auto-memory out of the prompt | $0.0285 | 17.8% | $145 |
| **Both** (5m rate applies to the smaller block, so they don't simply add) | **$0.0536** | **33.5%** | **$273** |

Shrinking `FORMAT.md` is worth **~0.5%** and is not worth doing for cost. Details below.

## What the CLI is actually doing

One `claude -p` call issues one Opus request (9% of corpus calls report `num_turns=3`,
implying an occasional second) plus one ~2,000-token Haiku side call
(~$0.0021, ~4% of the bill; not avoidable from the CLI). The Opus request is split into
two cache blocks:

| Block | Size | Contents | Fate |
|---|---:|---|---|
| prefix | 8,563 tok | Claude Code scaffolding (582 tok, measured with an empty `--system-prompt-file`) + `system-prompt.txt` (~7,981 tok = FORMAT.md + CONTRACT) | **read** at $0.50/M on 91% of calls |
| tail | varies | `CLAUDE.md` + project auto-memory (**2,852 tok**) + per-turn system-reminders (~600 tok) + the per-file user prompt | **written** every call, because the user prompt makes it unique |

Nothing can make the tail cacheable — it is unique per file by construction. So the
question was never "can we stop re-creating the prefix" (we already don't); it is "how
much can the tail shrink, and at what write price".

### The write price was double what we assumed

Least-squares over all 5,094 recorded `usage` blocks recovers the CLI's own pricing
**exactly** (mean absolute error 0.000000):

```
cache_creation  $10.00 / Mtok      <- 2.0x input = 1-HOUR TTL write
cache_read       $0.50 / Mtok
output          $25.00 / Mtok
input            $5.00 / Mtok
```

$10/M, not the $6.25/M (1.25x, 5-minute) the earlier estimate assumed. Claude Code opts
subscription sessions into 1-hour-TTL cache writes (`fTe()` in the bundled binary: 1h is
on for non-overage subscription scopes including `sdk`, unless
`FORCE_PROMPT_CACHING_5M` is set). Confirmed directly — `usage.cache_creation` reports
`ephemeral_1h_input_tokens` equal to the whole `cache_creation` figure, and a call made
after a 7.5-minute idle gap still read the prefix from cache.

So the corrected baseline per call is:

| Line | Tokens | $/call | Share |
|---|---:|---:|---:|
| cache_creation @ $10/M | 9,521 | 0.0952 | 59.5% |
| cache_read @ $0.50/M | 9,691 | 0.0048 | 3.0% |
| output @ $25/M | 2,147 | 0.0537 | 33.5% |
| Haiku side call | ~2,000 | 0.0062 | 3.9% |
| **total** | | **0.1600** | |

which reproduces the run's actual billed total of $814.84 ($783.23 Opus + $31.61 Haiku)
over 5,094 calls.

## Conditions measured

Two blocks of calls, each using the *same* prompts across conditions so the comparison
is paired. `cc` = `cache_creation_input_tokens`, `cr` = `cache_read_input_tokens`, `$` =
Opus cost only.

### Block C — 3 identical prompts (3.2–3.4 KB), sequential

| Condition | cc | cr | $/call | Reading |
|---|---:|---:|---:|---|
| C1 exact production flags | 4,465 | 8,563 | 0.0630 | baseline |
| C2 drop `--no-session-persistence` | **0** | 13,028 | 0.0212 | prompt bytes byte-identical to C1 → full cache hit. The flag has **no** effect on caching. |
| C3 add `--exclude-dynamic-system-prompt-sections` | **0** | 13,028 | 0.0202 | also byte-identical → the flag is ignored when a custom system prompt is used, as its help text says |
| C4 add `--safe-mode` | 1,613 | 8,563 | 0.0345 | −2,852 cc; prefix untouched |
| C5 `cwd` outside the repo instead | **0** | 10,254 | 0.0186 | byte-identical to C4 → the two levers remove exactly the same bytes |
| C6 `--safe-mode`, 4 concurrent | 1,823 | 8,563 | 0.0337 | no concurrency penalty once the prefix is warm |

(C2/C3/C5 show `cc=0` *because* they reproduce an earlier condition's bytes within the
cache TTL. That is the evidence, not an anomaly: identical bytes ⇒ nothing to write.)

### Block R — 3 identical prompts (4.2–4.4 KB), fresh, sequential

| Condition | cc (per prompt) | TTL | cr | $/call |
|---|---|---|---:|---:|
| R4 production flags | 5,208 / 4,874 / 4,848 | 1h | 8,563 | 0.0645 |
| R2 `--safe-mode` + `FORCE_PROMPT_CACHING_5M=1` | 2,356 / 2,022 / 1,996 | **5m** | 8,563 | 0.0284 |

The `cc` delta is **exactly 2,852 on all three prompts** — that is `CLAUDE.md` (8,203
chars) plus the project auto-memory file, to the token. Opus cost falls 56% on these
prompts (they are smaller than the corpus mean, so the corpus-wide figure is 33.5%).

### Other conditions

- **7.5-minute idle gap** (C7): `cr = 8,563` — a hit. Confirms 1-hour TTL.
- **Prefix TTL risk of switching to 5m**: the corpus run's median inter-call gap was
  2.9 s and only **17** gaps exceeded 5 minutes. Switching to 5-minute TTL would add at
  most ~17 cold prefix writes ≈ **$0.91** against $182 saved.
- **`DISABLE_PROMPT_CACHING_OPUS=1`** (R3): 10,767 uncached input tokens, $0.0681 and
  13.5 s for a call that costs ~$0.032 and ~6 s with caching on. Turning caching off is
  2.1x worse. Don't.
- **Output quality spot check**: 3 files run under production flags and under
  `--safe-mode` + `FORCE_PROMPT_CACHING_5M` produced **identical anchor sets** (same id,
  anchor, kind, line) and identical unanchorable sets.

## Shrinking FORMAT.md is not a cost lever

`system-prompt.txt` sits in the **read** block, billed at $0.50/M. The whole 8,563-token
prefix costs $0.0048/call — 3% of the bill. A grammar-only variant could plausibly drop
the intro and artifact table, the "What changed in v1" blockquote, §4 Index, §5 Sidedoc,
§6 Resolution, the Open section and the scattered evidence counts: roughly 1,600–2,400
tokens, ~30%. That saves **$0.0008–0.0012 per call, 0.5–0.75%, ~$4–6 over the whole
corpus.** It is not worth the risk of perturbing a normative spec for that. (FORMAT.md
was not modified.)

If a trimmed spec is wanted, the argument has to be attention/quality, not cost — and it
would have to be scored against the pilot, since it changes what the model reads.

Note also that the earlier "5,448 tokens" figure for the system prompt is low: measured
against an empty `--system-prompt-file`, Claude Code's own scaffolding is 582 tokens, so
`system-prompt.txt` is ~7,981 tokens (21,894 chars ≈ 2.74 chars/token — it is dense in
grammar, tables and backticks).

## Recommended change

Two edits in `harness/convert_pilot.py`:

```python
def claude_cmd(effort: str) -> list[str]:
    return ["claude", "-p", "--model", MODEL, "--effort", effort,
            "--system-prompt-file", str(SYSTEM_PROMPT_FILE),
            "--safe-mode",                       # <- keeps CLAUDE.md + auto-memory out of the prompt
            "--no-session-persistence", "--output-format", "json", "--tools", "",
            "--json-schema", json.dumps(JSON_SCHEMA, separators=(",", ":"))]
```

```python
    env = {"HOME": ..., "PATH": ..., "USER": ..., "TERM": "dumb",
           "FORCE_PROMPT_CACHING_5M": "1"}      # <- 5-minute cache writes: $6.25/M, not $10/M
```

Equivalent to `--safe-mode`: point `cwd` at a scratch directory outside any `CLAUDE.md`
tree (measured byte-identical, C4 vs C5). `--safe-mode` is the more explicit statement
of intent and does not depend on where the process happens to run.

`--no-session-persistence` and `--exclude-dynamic-system-prompt-sections` can stay or go
as far as caching is concerned; neither moves a token.

### Caveats before adopting

1. `FORCE_PROMPT_CACHING_5M` is an internal Claude Code env var, found by inspecting the
   bundled binary — it is not in `--help` and could change or vanish. The harness should
   assert `usage.cache_creation["ephemeral_5m_input_tokens"] == usage.cache_creation_input_tokens`
   on the first call of a batch and warn otherwise, so a silent regression to $10/M is
   caught rather than paid.
2. `--safe-mode` removes `CLAUDE.md` from the model's context. That content is about the
   Sideword *experiment*, not about naming anchors, and the 3-file spot check was
   identical — but a config that changes model input should be re-scored on the 100-file
   pilot before a full corpus run, not adopted mid-batch.
3. Do not mix configs within one corpus arm.
4. The remaining `cache_creation` is the per-file user prompt itself and cannot be
   removed. Even at the floor (5m writes, no `CLAUDE.md`), the cache-creation line is
   $0.0417/call — 39% of the optimised $0.106. The next lever after this is output
   tokens ($0.0537/call, 34% of the current bill, unchanged by any of the above).
