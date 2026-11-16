# ADR-383 — A draft speaks in the person's voice

**Status**: Accepted, 2026-11-13; amended 2026-11-16 (learned when the person asks; the
person's words or LIA's writer — see the amendment below).
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

2. *(Superseded by the amendment of 2026-11-16: the style is learned only when the person
   asks, and never expires.)* **Learned on the run of the first writer that needs it.** No scheduler and no sweep: the
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

## Amendment 2026-11-16 — learned when the person asks; the person's words or LIA's writer

### Context

In production (2026-11-15) an e-mail LIA wrote and sent left the settings saying « nothing
learned yet », on an instance where no account had a profile at all. The turn ran in ReAct and
called `send_email_tool` with a `subject` and a `body` the loop wrote itself: the new-mail
writer runs only when one of them is missing, so the one door that learns and reads the style
was never reached — nothing was learned, nothing was read. The bound schema invited it: `body`
read « Email body content », while `reply_email_tool` and the mailbox drafts already said
« only words the person dictated ». Two flaws, not one: WHEN the style is learned (inside a
draft, invisibly, on the first writer that happens to run) and WHO writes the words (whoever
fills `body`).

Measured before the fix, on production's ReAct family with the real prompt and the real tool
schemas (`scripts/react/measure_email_authorship.py`, fictional addresses only): 14 of 18
requests of intent were written by the loop itself, and 3 of 12 dictations were altered.

### Decision

1. **Learned only when the person asks, and kept until they learn it again or forget it.**
   Their click in the settings (`POST /writing-style/learn`) runs through the assists' door
   (`tool_assists/style_learning.py`, `run_assist`): both spending ceilings asked first, the
   call billed to the account, the read of the sent mail filed, the outcome answered in a
   closed vocabulary (`learned`, `too_few`, `no_mailbox`, `reconnect`, `switched_off`,
   `superseded`) with what it cost. Their word to the assistant prepares an exact card
   (`learn_lia_writing_style_tool`) whose confirmation runs the same learning on the turn —
   the read filed as the turn's consultation, the call billed to the turn. Whichever surface
   asks, it is the account's one learning at a time across workers
   (`writing_style.learn_one_at_a_time`, one `run_shared_flight` claim: a second request waits
   at least as long as the e-mail slot's call and pays nothing), and it replaces the record it
   was asked on and nothing since: a record forgotten or learned again meanwhile is the
   person's later act and stands — `superseded`, checked before anything is read and again in
   the conditioned write (`WritingStyleRepository.save(..., replaces=)`). A profile never
   expires: `WRITING_STYLE_MAX_AGE_DAYS` is gone, and the writers only READ the style
   (`writing_style_for`).
2. **One authorship door for every tool that writes to someone**
   (`agents/emails/authorship.settle_words`: `send_email_tool`, `reply_email_tool`, and the
   mailbox drafts' create, reply and update). The words the person MARKED are kept exactly —
   quoted, introduced by a colon or a line break, or the whole message — by one linear rule
   (`is_dictated`). Any other text the agent proposed becomes what the e-mail must SAY, handed to
   LIA's writer, which keeps every fact, figure, date, name, address, link and quoted passage
   (`email_authorship_lines.txt`); a text too long to be written back whole (over
   `EMAIL_REWRITE_MAX_SHARE` of the writer's output budget) is kept as given rather than cut.
   The tools that set a text verbatim declare why (`TEXTS_LEFT_AS_GIVEN`): a note to oneself, a
   forward's note, a ticket comment, an automatic reply set from the card the person confirms.
3. **One contract, published once.** Each writing tool's manifest, `@tool` schema and docstring
   read the same constants (`emails/catalogue_manifests.py`), and the planner's e-mail rule says
   the same thing; a guard reads what the ReAct loop actually binds.
4. **The assistant at parity with the settings** (application operations `writing_style.read`,
   `.learn`, `.forget`). Learning binds the switch and the record it replaces, up to the write
   that keeps its result; forgetting removes the confirmed record only, in one conditioned
   statement (`WritingStyleRepository.forget`), so a style learned again since the card is kept
   and the card answers a stale state. An open
   settings section reads itself again when the assistant learned or forgot (`writing_style`
   resource) or turned the switch (`profile`).

### Measured

| What | Before | After |
|---|---|---|
| Requests of intent the ReAct loop wrote itself (of 18) | 14 | 1 — handed to the writer |
| Dictations kept exactly (of 12) | 9 | 12 |
| Facts and quoted passages kept when the agent's text becomes what to say (of 22) | — | 22 |
| Voice marks in a new e-mail, without / with the profile (of 44) | 28 | 43 |
| One learning's model call on 50 sent e-mails | — | 4.5–5 s, ≈ 10.6 k tokens, ≈ €0.02 |

The first two rows are production's ReAct family, three runs of eleven requests; the next two
are production's e-mail slot (`scripts/emails/measure_writing_style.py --proposed`). Spend:
about $0.03 on the ReAct family and €0.07 on the e-mail slot, plus the timed learning calls
(≈ €0.02 each).

### What this amendment leaves, and says so

- **A dictation spread over several messages** is not recognised: the rule reads the run's own
  message and, when the run resumes the turn after a question, the request the turn began with
  (`LiaRuntimeContext.turn_request`, from the router's record of the turn) — so « send to Paul:
  “…” » then « which Paul? » keeps the quoted words — but no earlier turn (in Pipeline mode the
  tool sees no state). Such words go to the writer as what to say, their facts kept.
- **When the agent wrote the e-mail, it costs one more call** of the e-mail slot: the price of
  the person's voice.
- **Forgetting from one surface while a learning started on another is still running**: the
  later write wins. The settings section holds its own « Forget » while its learning runs; the
  assistant's turn is sequential.
- **The automatic reply** (`set_vacation_responder_tool`) is set verbatim from the card the
  person confirms; no writer serves that setting.
- **The demonstrator** exposes the learn route: with no mailbox to read, it answers
  `no_mailbox`, asks no model and spends nothing.

### Consequences

- No e-mail waits for a learning any more: a writer's only extra cost is reading one row.
- An account that never asks is written for without a style, exactly as with the switch off;
  the settings say « nothing learned yet » and offer the button.
- Learning reads the latest `WRITING_STYLE_SENT_MAILS` sent e-mails once per request: one
  search, plus one read per message on Graph.

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
- Amendment 2026-11-16: `apps/api/src/domains/agents/emails/authorship.py`,
  `apps/api/src/domains/agents/prompts/v1/email_authorship_lines.txt`,
  `apps/api/src/domains/tool_assists/style_learning.py`,
  `apps/api/src/domains/agents/application/writing_style_learning.py`,
  `apps/api/src/domains/agents/application/writing_style_forgetting.py`,
  `apps/api/src/domains/agents/tools/application_writing_style_tools.py`,
  `apps/api/scripts/react/measure_email_authorship.py`,
  `apps/api/alembic/versions/2026_11_16_0300-6a1f3c9e2b7d_writing_style_learned_on_request.py`
