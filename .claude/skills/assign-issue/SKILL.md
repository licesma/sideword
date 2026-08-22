---
name: assign-issue
description: Bind this conversation to a Linear issue in the Sideword project — an issue the user names, or a new one created in the right place in the tree — keep the issue's conversation list current, and keep ownership honest: agent work is assigned to Knuth, work blocked on the user is handed back with a comment saying why, and every Done runs the parent check. Use on the first substantive turn of a conversation, when the user asks to assign / move / create an issue, when the focus has drifted off the current issue, when work is blocked on the user or handed back, and when an issue is finished.
---

# assign-issue

Binds a conversation to a Linear issue, maintains the reverse link, and moves ownership between the agent and the user. See `CLAUDE.md` for the governing rules — this skill is the mechanics.

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
3. If absent and no issue is named, work out where it belongs in the Sideword tree and **propose** it — a specific existing issue, or a new one with a parent — then wait. Unless the user already directed it explicitly, in which case act.

Once bound, walk `parent` from the issue up to the root and load every ancestor, plus the project. Then resolve the issue's spec document by the procedure in `CLAUDE.md` § Reading an issue — the description is a summary, not the spec. Report the chain to the user compactly: `Sideword › EST-3 Converter › EST-12 Anchor format`.

## Creating an issue

Give it a description of at most five lines — what, why, done-when. If the work has detail beyond that, put the detail in a document parented to the issue (`save_document` with `issue: "<EST-XX>"`) and link it from the description's last line as `Spec: <document url>`. If an existing issue's description has already grown into a spec, move the body into a doc and cut the description back.

## Ownership and handoffs

`CLAUDE.md` § Ownership is the policy; this is the mechanics.

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
3. Otherwise read the parent for real — `get_issue`, plus its spec doc by § Reading an issue — and ask whether what the children delivered is the whole of what the parent asked for.
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

Remove its row from the old issue's comment, add it to the new one's, update the index. Then apply the status rules in `CLAUDE.md` to **both** issues — the old one may no longer be In Progress, and the new one may need to become it.

Do not delete the old comment when its last row is removed; leave the header in place so the marker survives.
