# Handling Linear

How conversations bind to Linear issues, where specs live, and the mechanics of
keeping the two in sync. Part one is the policy; part two is the procedure.

Repo-specific values below — workspace, team, project, the comment marker, the
skill path, and the two names ownership moves between (**Knuth**, the agent user,
and **Esteban Martínez**, the human) — are the Sideword settings. Substitute your own.

---

# Part one — policy

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

---

# Part two — the `assign-issue` skill

Frontmatter, as it appears at the top of `.claude/skills/assign-issue/SKILL.md`:

```yaml
---
name: assign-issue
description: Bind this conversation to a Linear issue in the Sideword project — an issue the user names, or a new one created in the right place in the tree — keep the issue's conversation list current, and keep ownership honest: agent work is assigned to Knuth, work blocked on the user is handed back with a comment saying why, and every Done runs the parent check. Use on the first substantive turn of a conversation, when the user asks to assign / move / create an issue, when the focus has drifted off the current issue, when work is blocked on the user or handed back, and when an issue is finished.
---
```

Binds a conversation to a Linear issue, maintains the reverse link, and moves ownership between the agent and the user. Part one above is the governing rules — this is the mechanics.

## Identity

A conversation's durable key is its **session ID**, which survives renames. Its **title** is display-only and changes as the conversation develops.

```
.claude/skills/assign-issue/session.sh [sessionId]   # prints "<sessionId>\t<title>"
```

Pass the session ID explicitly when you know it — it is the UUID directory segment in the scratchpad path given in your system prompt. With no argument the script falls back to the most recently modified transcript, which is wrong if two sessions are running in this repo at once.

The local index `.claude/conversation-index.json` maps session IDs to issues for fast lookup:

```json
{ "60042abb-8a48-49e0-a02d-0079273e03e5": { "issue": "EST-12", "title": "...", "boundAt": "2026-08-14" } }
```

This index is a cache. **Linear is the source of truth** — if they disagree, believe Linear and repair the index.

## Resolving the binding

1. Read the index for this session ID. If present, `get_issue` on it and you're bound.
2. If absent and the user named an issue, use that.
3. If absent and no issue is named, work out where it belongs in the tree and **propose** it — a specific existing issue, or a new one with a parent — then wait. Unless the user already directed it explicitly, in which case act.

Once bound, walk `parent` from the issue up to the root and load every ancestor, plus the project. Then resolve the issue's spec document by the procedure in § Reading an issue — the description is a summary, not the spec. Report the chain to the user compactly: `Sideword › EST-3 Converter › EST-12 Anchor format`.

## Creating an issue

Give it a description of at most five lines — what, why, done-when. If the work has detail beyond that, put the detail in a document parented to the issue (`save_document` with `issue: "<EST-XX>"`) and link it from the description's last line as `Spec: <document url>`. If an existing issue's description has already grown into a spec, move the body into a doc and cut the description back.

## Ownership and handoffs

Part one § Ownership is the policy; this is the mechanics.

`save_issue` takes `assignee` as a name, so no ID lookup is needed — `assignee: "Knuth"` for agent-owned, `assignee: "Esteban Martínez"` for user-owned. Put it in the same call as `state`, so an issue is never In Progress with the wrong owner even briefly.

```
save_issue  id: EST-12  state: "In Progress"  assignee: "Knuth"
```

Handoff comments are appended, never edited in place — `save_comment` with `issueId` and no `id`. One marker line, then a short body:

```markdown
**Needs your attention**

The resolver treats `elif` as a bare `if`, so 732 pilot records miss. Two fixes, and
they diverge downstream — pick one:

1. Give `elif` its own kind with the condition as discriminator.
2. Flatten `elif` into a nested `if` and let the existing rule cover it.

Blocked here until this is settled; nothing else in FORMAT v1 depends on it.
```

Use `**Decision**` when recording what the user chose and why, and `**Handed back to Knuth**` when picking the work back up. Keep them to what the next reader needs — detail that outlives the handoff belongs in the spec doc, not in a comment.

Saying "this needs you" only in the conversation is the failure mode this exists to prevent. The comment and the reassignment come first; the chat message says the same thing afterwards.

## The parent check

Run on every transition to Done, against the parent of the issue just closed.

1. `list_issues` with `parentId: "<EST-XX>"` and `fields: ["id", "title", "status", "statusType", "assignee"]`.
2. Any sibling whose `statusType` is not `completed` or `canceled` → stop. The parent is untouched.
3. Otherwise read the parent for real — `get_issue`, plus its spec doc by part one § Reading an issue — and ask whether what the children delivered is the whole of what the parent asked for.
   * **Yes** → `save_issue` with `state: "Done"`, assignee left as Knuth. Then run the check again on *its* parent.
   * **No, or unsure** → `save_issue` with `assignee: "Esteban Martínez"`, status untouched, plus a `**Needs your attention**` comment naming what looks missing and the subissues you would add. Stop the walk.

A parent that has no children never reaches this check — it closes on its own work, like any leaf.

## The conversation comment

One comment per issue, created on first bind and updated in place thereafter (`save_comment` with `id`). Find it by its marker:

```markdown
<!-- sideword:conversations -->
**Conversations**

- **Plan Sideword documentation separation tool** — `60042abb-8a48-49e0-a02d-0079273e03e5` · 2026-08-14
```

Never create a second one. `list_comments` on the issue, find the marker, update that comment's body.

## Syncing

Whenever you touch the issue for any reason, and at bind time:

1. Run `session.sh` to get the current title.
2. If it differs from the title in the conversation comment, rewrite that entry. The session ID identifies the row; the title is what changes.
3. If the index disagrees with Linear, fix the index.

Titles stabilize early in a conversation, so this converges quickly without needing a dedicated trigger.

## Moving a conversation

Remove its row from the old issue's comment, add it to the new one's, update the index. Then apply the status rules in part one to **both** issues — the old one may no longer be In Progress, and the new one may need to become it.

Do not delete the old comment when its last row is removed; leave the header in place so the marker survives.
