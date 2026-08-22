# v0 grammar against real code — resolver pass

First contact between `FORMAT.md` v0 and code nobody wrote for it.

**Corpus.** The CPython 3.14 standard library, 155 modules, ~4.5 MB. Chosen
because it is offline, comment-dense, and written by many hands over decades.
It is a stand-in, not the SWE-bench corpus the issue calls for — but it is
enough to settle three of the four open questions.

**Method.** No model. The resolver enumerates every anchor a file admits, so
collisions and unnameable positions surface mechanically. That means every
number here is a fact about the *grammar*, with no converter accuracy mixed in.

```
cargo run --release -p sideword-resolver -- audit <files>.py
```

| | |
|---|---|
| Files | 155 |
| Parse failures | 0 |
| Anchors enumerated | 125,698 |
| Wall clock | 0.26 s |
| Anchors needing an occurrence suffix | 8,351 (6.6%) |
| Canonical anchors naming two or more nodes | 996 — **661 root**, 335 inherited |

An ambiguity is *inherited* when a shorter prefix is already ambiguous:
`Popen._get_handles#param:self` collides only because `Popen._get_handles`
does. Only roots are independent evidence.

## The headline

**Every root collision is in the symbol path. Not one is in a statement or an
element.**

| Where | Root collisions |
|---|---|
| `§1.1` symbols | 661 |
| `§1.3` statements | 0 |
| `§1.4` elements | 0 |
| `§1.2` symbol parts | 0 |

The part of the format that looked riskiest — naming a `raise` three loops deep
by the text of its enclosing statements — holds up across 52,463 statement
anchors. Sibling ties (§1.5) absorb the duplicates, and they are common enough
(6.6%) to confirm **open question 1**: ties must be derived, never authored. An
author writing `if:x` cannot see the identical `if:x` forty lines below.

The part that looked settled is where it breaks.

## F1 · A symbol path names a binding, so rebinding collides — 600 cases

| Cause | Count |
|---|---|
| `self.x` assigned in 2–19 methods | 464 |
| Module/class variable rebound in a conditional branch | 111 |
| Module/class variable rebound at the same scope | 18 |
| Plain redefinition | 7 |

```python
class shlex:
    def __init__(self):
        self.state = ' '        # shlex.state
    def read_token(self):
        self.state = nextchar   # shlex.state — 19 of these in one class
```

**Open question 2 asked the wrong thing.** It framed `Cart.total` versus
`Cart.__init__#assign:self.total` as a choice of *which anchor wins*. The real
problem is that `Cart.total` is not unique to begin with.

**Proposed v1.** A symbol anchor names a **name, not a binding**. One attribute,
one anchor, one doc — which is what a reader wants anyway; nobody documents
`self.state` nineteen times. The resolver picks the first binding as the render
position. Every other binding stays addressable as a statement anchor
(`shlex.read_token#assign:self.state`) for a comment about that particular
write. No counting appears in the anchor text.

This also covers the conditional-rebinding cases (`try: import x / except:
x = fallback`), which are the same shape.

## F2 · Two definitions, same qualname — 68 cases

| Cause | Count |
|---|---|
| Redefined in a conditional branch | 39 |
| `@property` + `@x.setter` / `@x.deleter` | 22 |
| Plain redefinition | 7 |

```python
if _mswindows:
    def _get_handles(self, ...): ...
else:
    def _get_handles(self, ...): ...   # subprocess.Popen, both platforms
```

Unlike F1 these genuinely want **separate docs** — a getter and a setter say
different things, and the Windows and POSIX branches are different code. So the
name-not-binding rule does not apply; they need a discriminator.

**Proposed v1.** Extend `~n` from segments to symbol paths:
`SSLContext.minimum_version~2`. §1.5 already licenses exactly this for exact
duplicates among siblings, and two defs with one qualname are exact duplicates
among siblings. One mechanism, derived the same way, no new syntax.

`@overload` (open question 3) did not appear in this corpus — the stdlib is not
typing-heavy — but it is the same shape and the same fix. **Open question 3 is
answered**, though a typed corpus should confirm it.

## F3 · §1.4 describes far less than real code contains

| | Occurrences |
|---|---|
| Positional call arguments — no rule at all in §1.4 | 22,588 |
| Elements nested deeper than the one level §1.4 allows | 5,438 |

§1.4 names dict keys and keyword arguments. Real code puts comments on
positional arguments and inside nested literals constantly. The resolver already
emits both — positional args keyed by their own source text, and element chains
to depth 6 — and neither produced a single collision. **§1.4 should be widened
to match**, since the mechanism already works.

## F4 · Discriminators drawn from source are unbounded — 2,457 over 80 chars

Worst in corpus, 300+ characters, from `pickletools`:

```
opcodes#item:I(name='INST', code='i', arg=stringnl_noescape_pair, stack_before=[...
```

An anchor is supposed to be cheap to read in an index. A rule is needed:
truncate with a stable hash, or fall back to `~n` when the discriminator exceeds
a budget.

## F5 · Grammar hazards in the discriminator

The discriminator is raw source, so it can contain the separator `/` and the tie
marker `~n`.

Mitigated in the resolver: a `/` only splits when a known kind follows it *and*
is followed by `:`, `/`, `~`, or end-of-string. `if:n/2>1` and
`call:reduce(a/item)` both survive. It still mis-reads `assign:total/item`,
where the division's right operand ends the anchor and is spelled like a kind.

Rare, but the format should say so explicitly rather than leave it to the parser.

## F6 · Spec inconsistencies found by implementing it

1. **`except` is written two ways.** §1.3's table gives `try/except:ValueError`;
   the prose example just below gives `Cart.add#except:ValueError/pass`. The
   resolver canonicalizes the first and accepts the second as an alias. Pick one.
2. **`elif` is listed as taking no discriminator** — but an `elif` has a
   condition, and a chain of them is otherwise unaddressable. The resolver emits
   `if:a/elif:b`. The table is wrong.
3. **`else` and `finally` have no AST node**, so their anchors borrow the range
   of the first statement inside them — 354 anchors with an approximate
   position. Harmless for retrieval, wrong for rendering a `lead` comment above
   the `else:` line. The renderer will need the keyword's real offset.
4. **A decorated symbol has two defensible attachment lines** — above the
   decorators, or above the `def`. The resolver anchors on the `def`, since a
   comment above a decorator is already addressable as `#decorator:`.
5. **§1.1 does not say what a module-level statement anchors to.** The resolver
   uses `<module>#call:...`, extending `<module>` from "the docstring" to "the
   module as a container".

## Still open

- **Open question 4, migration.** Untouched here. Note that `ast`-equivalent
  parsing turned out to be enough for the resolver, and `tokenize`-equivalent
  comment extraction should be enough for the stripper — LibCST may not be
  needed at all.
- **The model half.** Every number above is about what the grammar *can* name.
  Whether a model reliably picks the right anchor is a separate question, and
  the converter arm of EST-81 is what answers it.
- **Corpus bias.** The stdlib is not SWE-bench. It has few type annotations, no
  `@overload`, and little Sphinx markup — the exact features that stress
  `#param:` splitting.

---

## What v1 did with this (EST-120, 2026-08-18)

Every finding above is answered in `FORMAT.md` v1, and the resolver was changed
with it. Re-running the same audit over the same 155 modules:

| | v0 | v1 |
|---|---|---|
| Anchors enumerated | 125,698 | 126,376 |
| Canonical anchors naming two or more nodes — **root** | **661** | **0** |
| Parse failures | 0 | 0 |

* **F1** — a symbol path names a name, not a binding. The first binding owns the
  anchor; every later write stays reachable as a statement anchor.
* **F2** — repeated *definitions* of one qualified name tie on the path
  (`SSLContext.minimum_version~2`), since a getter and a setter say different
  things. The grammar gained `path := name ( "." name )* [ "~" n ]`.
* A third case the audit surfaced only once F1 and F2 were in: a name both
  **defined and assigned** (`def reduce` … `reduce = _warn(reduce)`, 20 cases).
  The definition owns the anchor whichever comes first. That is what took the
  root collisions to zero.
* **F3** — §1.4 widened to positional arguments, list/set/tuple items, and
  nesting to depth 6. The walk already emitted all of it.
* **F4** — §1.6 gives discriminators a canonical form and an 80-character
  budget, applied to both sides of a lookup so an author and the walk converge.
* **F5** — the `/` and `~n` hazards are stated in §1.6 rather than left to the
  parser, and the walk now strips `#` comments and `\` continuations out of a
  discriminator before it becomes one.
* **F6** — `except` is canonically `try/except:E` with the short form aliased;
  `elif` takes its condition, with the v0 spelling aliased for sidedocs written
  against v0; `else`/`finally` positions stay approximate (still open, for the
  renderer); a decorated symbol anchors on the `def`; module-level statements
  are `<module>#...`.

Two things the stdlib audit could not see, both from the EST-111 model pilot:

* Ties must be stripped at **every** depth on lookup, not only on the last
  segment — an author writing `for:x in xs/while:True/assign:total` cannot know
  the walk numbered the `for`.
* A documentation record is a **block**, not a line (§3). 48% of the pilot's
  records shared an anchor with another record, and 95% of those groups were one
  paragraph split apart line by line.
