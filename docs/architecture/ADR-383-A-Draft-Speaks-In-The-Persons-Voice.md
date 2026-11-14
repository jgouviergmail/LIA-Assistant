# ADR-383 — A draft speaks in the person's voice

**Status**: Accepted, 2026-11-13.
**Date**: 2026-11-13

**Amends**:
[ADR-344](ADR-344-Mailbox-Drafts-Kept-Freely-Sent-After-One-Confirmation.md) — the reply the
person confirms (`reply_email_tool`) is written by the same writer as the reply saved as a
draft when the person dictated no words of their own.

## Context

LIA writes e-mails for the person in two places: the reply drafter (`reply_drafting`, read by
the reply saved in the mailbox and by the Tools' « reply » assist) and the new-mail writer
(`content_generation`, read by `send_email_tool`, the mailbox draft tools and the Tools'
« compose » assist). Both wrote in the register of the RECEIVED e-mail, or of the instruction,
and signed with no name unless asked: two people answering the same message got the same
reply. And the most common reply of all — « answer Paul that Friday works », which the
planner turned into `reply_email_tool` — was written by the planner itself, in a body
parameter, by no e-mail writer at all.

How a person writes is in their own sent mail: the greeting they use, how they sign off,
whether and how they sign, « tu » or « vous », emojis, length. Measured before any product code
on FICTIONAL people only (`apps/api/scripts/emails/measure_writing_style.py`,
`task emails:writing-style:measure`; owner directive 2026-11-11: no proof on a real mailbox):
four personas with planted facts in what they sent, three model families, each mark checked by
rule, a planted fact written into a new e-mail counted as a leak. The final run used the very
request and blocks this decision ships:

| Writer | Without the profile | With it | Leaks |
|---|---|---|---|
| Replies (66 marks a family) | 42, 42, 41 | 64, 62, 63 | 0 |
| New mails (44 marks a family) | 27, 24, 23 | 44, 42, 38 | 0 |

Three of the person's own e-mails shown verbatim did worse than a profile (51-61/66) and carry
their facts into the prompt; a blind judge preferred the profile arm as well. Total measured
spend: €0.173.

## Decision

1. **A profile of how the person writes, never of what they wrote.** One row per account
   (`writing_styles`): a profile a model wrote from the person's latest sent e-mails
   (`WRITING_STYLE_SENT_MAILS`), each read by its opening and its end where the greeting and the
   signature are, encrypted at rest, with how many e-mails it was learned from and when. The
   request (`writing_style_profile_prompt.txt`) forbids any name, place, project or date; the
   e-mails reach the model as data. Fewer sent e-mails than `WRITING_STYLE_MIN_SENT_MAILS`
   teach nothing: the row says it was built and holds no profile, so the sent folder is not read
   again before it is due (ADR-248).

2. **Learned on the run of the first writer that needs it.** No scheduler and no sweep: the
   first e-mail LIA writes for the person reads their sent folder (`in:sent`, whole on Gmail and
   IMAP, one message at a time on Graph) and asks the e-mail slot, billed to that writer's turn
   or assist; the profile is then served from the database until it is
   `WRITING_STYLE_MAX_AGE_DAYS` old. Drafts asked together learn once (`run_single_flight`).
   Nothing is held across a wait (ADR-304): a short session reads, the mailbox is opened and
   closed, the model answers, a new short session keeps the result.

3. **One door, read by every writer** (`agents/emails/writing_style.writing_style_for`). The reply
   drafter reads its block just before the received e-mail, the new-mail writer just before its
   language rule, both from one lines file (`writing_style_lines.txt`), only when a profile exists
   (ADR-284). A note to the person's own mailbox and a subject alone read no style.

4. **One writer for a reply's words.** `reply_email_tool` takes `content_instruction`, and its
   `body` is only for words the person dictated exactly: with no words, LIA's reply writer writes
   the reply from the received e-mail (`tools/reply_writing`), exactly as the mailbox reply draft
   does, with what the person already answered (ADR-379). With no instruction either, the
   person's own message says what to answer. What the writer could not do is the tool's refusal
   (a ceiling, no usable answer), never a guess (ADR-303). The planner's e-mail rule says who
   writes what: dictated words go in `body`, what to say goes in `content_instruction`.

5. **The person's switch removes the capability, never the record** (ADR-280).
   `users.writing_style_enabled`, ON for every account, belongs to the reviewed preference
   vocabulary the settings screen (`PATCH /writing-style`) and the assistant's preference tool
   both write. Off, nothing is read, learned or used; what was learned is kept until the person
   forgets it (`DELETE /writing-style`). A learning that arrives after the switch went off writes
   nothing, in the same statement (`WritingStyleRepository.save`).

6. **A failed learning is a draft without style, said in the logs.** The writer drafts as before
   and the failure is logged by its kind; a spending ceiling is the exception — the ceiling the
   draft itself meets — and it is raised.

7. **The registers know it.** The read of the sent folder is filed as `writing_style:email` in a
   turn, and by the assist's own reading in the Tools; the module is a declared direct client
   caller and a declared mail lister that situates nothing (a reply state says nothing of a
   voice); the spend road is the writer's. The profile is purged with the account, exported
   decrypted, and shown to administrators as one more switch.

## What this decision leaves, and says so

- **A forward's note** stays the planner's: the forwarded message is someone else's words, and
  its note, when there is one, is a line.
- **Editing a draft before it is sent** (the draft critique) rewrites what is already written in
  the person's voice; it reads no profile of its own.
- **The profile is not editable by hand.** It is read, switched off or forgotten; editing it
  would turn a learned description into an instruction the person writes for a model.
- **The demonstrator** exposes the routes; with no mailbox to connect, nothing is ever learned
  there and the section says so.

## Consequences

- A reply the person confirms now costs one call of the e-mail slot when they dictated no words
  (the planner's plan is shorter by as much), and is written from the received e-mail rather than
  from what the planner had read of it.
- The first e-mail written for a person reads their sent folder once, and again when the profile
  is due: one search, plus one read per message on Graph.
- An e-mail a person signs « Seb » keeps « Seb » above the signature block a mailbox adds
  (`signed_body`): what the person types and what their mailbox appends are two things, as in
  their own sent mail.

## References

- `apps/api/src/domains/agents/emails/writing_style.py`,
  `apps/api/src/domains/agents/emails/reply_drafting.py`,
  `apps/api/src/domains/agents/emails/content_generation.py`
- `apps/api/src/domains/agents/tools/reply_writing.py`, `apps/api/src/domains/agents/tools/emails_tools.py`
- `apps/api/src/domains/writing_style/` (model, repository, service, routes)
- `apps/api/src/domains/agents/prompts/v1/writing_style_profile_prompt.txt`,
  `apps/api/src/domains/agents/prompts/v1/writing_style_lines.txt`
- `apps/api/alembic/versions/2026_11_13_0900-a57db671b943_writing_styles.py`
- `apps/api/scripts/emails/measure_writing_style.py`
- `apps/web/src/components/settings/WritingStyleSettings.tsx`
- `docs/technical/WRITING_STYLE.md`
