# Sideword

Python code stored separately from its comments and documentation.

Each file becomes three things: clean `.py` source, a small index naming which symbols are documented, and the documentation itself. Docs attach to semantic anchors — functions, classes, variables, parameters — not line numbers.

**Humans** get the normal inline view back, reconstructed by a VS Code extension. Reading and editing feel unchanged; the split is invisible.

**Agents** read the code plus the tiny index, and retrieve full documentation only when it earns its place in context.

## The experiment

Convert SWE-bench Verified repos to Sideword, then run identical agents across three arms:

1. **Original** repos, unchanged.
2. **Sideword** — clean code + index + retrievable docs.
3. **Ablation** — Sideword clean code, no docs at all.

Sweep multiple model generations. Measure resolve rate, tokens, cost, latency, and retrieval behavior.

Arm 3 is load-bearing: it separates "docs help" from "less context helps." If it ties arm 2, the docs were never worth retrieving.

## If it works

VS Code extension and GitHub integration, with semantic documentation diffs alongside code diffs.

## Linear is the system of record

Workspace `esteban-ml` · team **Esteban** (`EST`) · project **Sideword**.

Every conversation in this repo is bound to exactly one Linear issue — top-level or a subissue at any depth. Depth doesn't matter; binding does.

### Binding

Bind on the first substantive turn, using the `assign-issue` skill. Skip it only for trivial one-off questions that leave no trace.

Once bound, load the issue **and its full ancestor chain up to the root**, plus the project, plus the issue's spec document if it has one. Work with the whole chain in view, not just the leaf — a subissue rarely makes sense without the parent that motivates it.

Creating a new issue, or moving this conversation to a different one, **requires confirmation**. Propose it and wait. The one exception: when the user directs it explicitly ("create a new issue for this", "move this to EST-12"), act without asking.

If the conversation's focus drifts off its issue, say so and propose a move rather than letting the binding quietly go stale.

### Descriptions and specs

Two audiences, two places.

**The description is for the user.** At most five lines — what, why, done-when. It is what someone reads in a list view without opening anything, so it stays a summary and never grows into a spec. A description is optional; an issue with nothing durable to say is better left blank.

**The spec is for agents.** It lives in a Linear document parented to the issue: `save_document` with `issue: "<EST-XX>"` and `title: "EST-XX — <short title>"`. Everything that would bloat the description goes here — constraints, edge cases, prior art, acceptance criteria, decisions and the reasons behind them. Not every issue needs one; write it when the work has detail worth carrying between conversations.

A spec never goes in a comment. Comments record what happened; they scroll away and can't be revised in place.

When a spec doc exists, the description's last line links it: `Spec: <document url>`.

#### Reading an issue

Never work from the description alone.

1. `get_issue` on the identifier — list views truncate.
2. If the description links a doc, `get_document` on that URL or slug and treat its contents as part of the spec.
3. If it doesn't, check anyway — a doc can exist with the link missing. `list_documents` has **no** `issueId` filter, so pass `teamId` (or `query` with the issue identifier) plus `fields: ["id", "title", "url", "issue"]` and match on the `issue` field client-side. If you find one that way, add its URL to the description so the next run doesn't have to search.
4. Only if there is genuinely no doc, work from the description.

#### Changing them

**Change a description only when a new finding contradicts what it currently says.** Not when you learn something additional. Not to log progress. Not to add nuance or hedge. Contradiction is the sole trigger — if the description is still true, leave it alone even when you could say more.

The spec doc is the opposite: it is the working record, so extend it as understanding develops. `patch` an existing doc in place rather than creating a second one for the same issue.

Use `save_issue` with `patch` to edit descriptions surgically rather than rewriting the whole field.

### Ownership

The assignee answers *whose move is it* — not who did the work. Status says what phase the work is in; the assignee says who it is waiting on.

| Assignee | Meaning |
|---|---|
| **Knuth** | an agent owns it — working it now if In Progress, queued for an agent otherwise |
| **Esteban Martínez** | waiting on you: a decision, a review, or work only you can do |

Every issue an agent creates is assigned to **Knuth**, whatever its status. Picking work up means In Progress **and** assigned to Knuth. Set the assignee in the same `save_issue` call as the status — never as a follow-up.

An issue assigned to you always carries a comment saying why. No exceptions: that comment is the entire point of the assignment. Opening it should answer "what do you need from me" without reading anything else.

#### Handoffs

A stretch of agent work ends in exactly one of two states.

**Blocked on you.** Status stays **In Progress** — the work is stalled, not finished. Reassign to you and comment: what is needed, what was already tried, what the options are. Say it in the conversation too, but the conversation is the notification and the comment is the record. When the chat is gone, Linear still has it.

**Finished and verified.** → **Done**, assignee stays Knuth. Done issues sit in nobody's queue, and the assignee is then a record of who did the work.

**Handing back.** When you settle the question in the conversation, comment the decision and its reasoning on the issue, then reassign to Knuth if an agent is the one to act on it. The round trip stays legible in Linear to someone who never saw the chat.

Handoff comments are appended, never edited in place — the sequence is the record. Each opens with a bold marker line: `**Needs your attention**`, `**Decision**`, `**Handed back to Knuth**`.

### Status

| Event | Action |
|---|---|
| Binding to an issue in Backlog or Todo | → **In Progress**, assigned to **Knuth** |
| New issue for work starting now | Create as **In Progress**, assigned to **Knuth** |
| New issue for later work | Create as **Backlog**, assigned to **Knuth** |
| Agent is blocked on you | Stays **In Progress**, reassigned to **you**, with a comment saying why |
| Work in the conversation is finished and verified | → **Done**, automatically |
| Resuming work on a Done issue | → **In Progress**, assigned to **Knuth**, and say so |
| Any issue reaches Done | Run the parent check |
| Canceled / Duplicate | Never automatic — always propose |

Done means the work is genuinely complete and verified. A conversation ending is not completion, and neither is code that hasn't been run.

#### The parent check

Every time an issue reaches Done, look at its parent.

| Siblings | Parent reads… | Action |
|---|---|---|
| any still open (Backlog, Todo, In Progress) | — | leave the parent alone |
| all Done or Canceled | complete — the children delivered what it asked for | → **Done**, assignee stays Knuth |
| all Done or Canceled | incomplete — more subissues are needed | assign the parent to **you**, leave the status, comment what looks missing |

Judge the third column against the parent's description *and* its spec doc, not the subissue titles. Uncertainty resolves to asking, never to closing: if you cannot tell whether the parent is finished, that is row three.

When the check closes a parent, run it again on the grandparent, and keep walking up until a level stops it or the root closes.

### Conversation list

Every issue carries the list of conversations bound to it, in one dedicated comment. The `assign-issue` skill owns that comment's format and upkeep — including rewriting a conversation's title on the issue when the conversation gets renamed.
