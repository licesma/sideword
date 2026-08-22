# Prior work on the no-comments arm

Literature check for EST-83: has anyone run arm 3 — a repository-level coding
benchmark with comments and docstrings stripped — and what happened?

Verification marks: **[v]** confirmed directly against the source; **[r]**
reported by the search pass from a table or page body, not re-checked here.

## Answer

**Arm 1 vs arm 3 has been run twice. Arm 2 has never been run.**

Both existing arm-3 results are recent, small, and **disagree in sign**.

| Study | Setup | Result |
|---|---|---|
| Hrubec & Cito, [arXiv:2606.01326](https://arxiv.org/abs/2606.01326), 31 May 2026 **[v]** | SWE-bench Verified, GPT-4.1, n=100 | remove-comments 46.0% → 45.0%; remove-docstrings 46.0% → 43.0% **[r]** |
| [Antimemetic AI](https://antimemeticai.com/comment-ablation), Feb 2026 | SWE-bench Verified, mini-swe-agent, GPT-5-mini / GPT-5.2, triplicated | comment removal a small but significant **increase** for GPT-5-mini; no effect for GPT-5.2 **[r]** |

The paper is a token-reduction study, not a documentation study: comments and
docstrings are two of several semantics-preserving minifications, ablated
separately and never combined. It reports no confidence intervals and warns
that small differences should not be read closely. The blog post publishes no
pass rates, no p-values, and no sample sizes — directional only.

Neither is decisive, and their disagreement is the most useful fact here: the
effect is small enough that two competent attempts got opposite signs.

Two incidental findings from the same paper worth keeping: **docstring removal
was the single cheapest context saving measured** — −22% input tokens for −3 pp
resolve rate, the best ratio of any transformation tried — and stacking all
minifications cost −12 pp for −42% tokens. **[r]**

## The strongest evidence for the thesis is not on issue resolution

**Code-QA-Bench**, [arXiv:2605.29277](https://arxiv.org/abs/2605.29277) — three
conditions (closed-book / code-only / documented) over 10 SWE-bench Python
repos, 628 QA tasks, four frontier models. Docstrings, comments, `docs/`,
`README*`, `*.md`, `*.rst` deleted; code and type annotations kept. **[r]**

- 528 code-derivable tasks: documented − code-only = **+0.007, insignificant**
- 100 deliberately doc-dependent tasks: **+0.071, p<0.003**
- code over closed-book: **+0.231**, ~3× the documentation gain

This is close to a prediction for our arm 2 vs arm 3: near-zero on average,
real but small on the subset that actually needs prose. Their stripping script
is our arm-3 transform, already written.

Also relevant, in the "less prose is better" direction:

- **RepoQA** ([arXiv:2406.06025](https://arxiv.org/abs/2406.06025)) strips
  comments and re-pads with filler to hold context length fixed. Nearly every
  model **improved** — gpt-4-turbo 76.4 → 92.6. Code search, not patching. **[r]**
- **RepoExec** (Findings of NAACL 2025,
  [arXiv:2406.11927](https://arxiv.org/abs/2406.11927)) — signatures-only
  context beat signatures+docstrings for two of three models. **[r]**
- **Agentless** ([arXiv:2407.01489](https://arxiv.org/abs/2407.01489)) —
  docstring-free skeletons localized better *and* ~7× cheaper than full files. **[r]**

And one in the other direction: **RepoRepair**
([arXiv:2603.01048](https://arxiv.org/abs/2603.01048)) adds a retrieved
LLM-generated doc layer for **+8.7 pp** on SWE-bench Lite — but on top of an
unmodified repo, so it measures added synthetic docs, not the repo's own. **[r]**

## What is actually novel

1. **Arm 2 in any form.** Nobody strips a repo's own human-written
   documentation, hands the agent an index plus a retrieval tool, and measures
   resolve rate. The closest, "Do Context Files Help Coding Agents?"
   ([arXiv:2607.27250](https://arxiv.org/abs/2607.27250)), does selective
   retrieval on `AGENTS.md`, not in-code docs, at n=17, and finds nothing. **[r]**
2. **Arm 3 as a single combined condition** at adequate power. Comments and
   docstrings have been ablated separately, never together, never with
   significance testing.

Prior art on the *mechanism* — not the experiment — is **Codetations**
([arXiv:2504.18702](https://arxiv.org/abs/2504.18702)): annotations stored
outside the file, anchored to spans, resynchronized across edits. Sideword's
contribution is the measurement and the code+index+retrieval combination, not
the idea of external annotations. **[r]**

## Four consequences for the experiment

**1. The benchmark is compromised. [v]** OpenAI
[retired SWE-bench Verified in February 2026](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/):
frontier models reproduce gold patches and problem statements verbatim, and
59.4% of 138 consistently-failed problems have flawed tests. They recommend
SWE-bench Pro. This contradicts the corpus named in EST-81 and in `CLAUDE.md`
and needs a decision before conversion work scales up.

Note the direction of the confound: memorization needs neither code nor docs,
so it hurts arm 1 vs arm 3 more than arm 2 vs arm 3, which is the contrast we
care about. It is a threat to the headline, less to the result.

**2. Hold token count constant, or the experiment measures length.** Arm 3 is
strictly shorter than arm 1. Pure compression is worth +2 to +4.6 pp on
SWE-bench Verified (SWEzze, [arXiv:2603.28119](https://arxiv.org/abs/2603.28119)),
and context length alone degrades performance even when the extra content is
masked to whitespace (Findings of EMNLP 2025,
[arXiv:2510.05381](https://arxiv.org/abs/2510.05381)). **[r]** Borrow RepoQA's
control: re-pad stripped regions with filler. This is the single most important
design fix the literature suggests.

**3. Power for a ~1 pp effect.** Every measured delta in this space is 1–3 pp,
and Code-QA-Bench's +0.007 on code-derivable tasks is the honest prior. SWE-bench
instances are overwhelmingly code-derivable. Repeated seeds, and pre-register a
stratification by doc-dependence — otherwise arms 2 and 3 tie for the wrong
reason and a null is indistinguishable from an underpowered run.

**4. Expect arm 2 to be flat.** Developer-written context files *reduced*
resolve rate in Gloaguen et al.
([arXiv:2602.11988](https://arxiv.org/abs/2602.11988)): 33.5% → 29.6% on
SWE-bench Lite, 32.5% → 24.2% on their AGENTbench. **[r]** If Sideword's docs
faithfully reproduce the repo's existing prose, the honest prior for arm 2 is
null or slightly negative. Worth saying out loud before running it.

## A side argument that survives any result

Comment-borne prompt injection is real — Alibi
([arXiv:2607.24964](https://arxiv.org/abs/2607.24964)) reports 91–100% attack
success against LLM vulnerability detectors using adversarial comments alone,
with **comment stripping the only effective defense**. **[r]** Sideword's split
makes that stripping structural rather than a preprocessing step.

## Explicitly not an answer

HumanEval/MBPP/CoderEval-style docstring removal (e.g. FeedbackEval, Claude-3.5
52.6% → 47.4%) measures removing the *task specification*, not documentation.
At least one paper conflates the two. Also: RepoBench's "commented cross-file
context" means a `#` path marker, not prose — not a comment ablation.

Confirmed to contain no comment/docstring ablation: RepoBench, CrossCodeEval,
RepoCoder, Long Code Arena, DevEval, EvoCodeBench, ClassEval, BigCodeBench,
Commit0, Aider polyglot, SWE-Gym, SWE-smith, OpenHands, AutoCodeRover,
Moatless. **[r]**

## Confidence

"Nobody has run arm 2" is a strong claim — three independent search threads
converged on the same empty category. "Nobody has run a powered arm 3" is
moderate.

Caveat on the evidence base: most of the closest hits are from the last six
months, and several are single-author preprints, thesis spinouts, or blog
posts. It is thinner and newer than the citation count suggests.

Unread, worth a manual pass: the TU Wien thesis behind arXiv:2606.01326 (likely
has the stacked ablation table), Code-QA-Bench's stripping script, and the
appendix of *On Code-Induced Reasoning in LLMs*
([arXiv:2509.21499](https://arxiv.org/abs/2509.21499)), which runs a
comment-perturbation taxonomy across 3,331 experiments but does not
disaggregate comment removal in the accessible version.
