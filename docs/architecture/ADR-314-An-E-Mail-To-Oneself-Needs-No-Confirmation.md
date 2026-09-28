# ADR-314 — An e-mail to oneself needs no confirmation, and a routine can send it

**Status**: accepted — 2026-09-24 (owner request: no HITL and no draft for e-mails sent to the user's own address — like the personal phone call — so a routine can mail the user; owner arbitration Q1: the connected mailbox's own address, and without a connected mailbox the account's address through LIA's own mail; Q2: a typed own address is NOT detected); amended 2026-09-27 (a draft send refused in a routine names this tool)
**Amends**: ADR-263 / ADR-276 (the effect gate LEDGERS a `reversible` action where it refuses a draft), ADR-290 (the `call_me` precedent), ADR-303 (failures returned, classified), ADR-304 (the send's content generation keeps the turn's config); the 2026-09-27 amendment also ADR-310 (the ladder's first rung) and ADR-085 (a boot check)

## Context

`send_email_tool` always builds a DRAFT the person confirms. That is right when the
recipient is someone else and wrong when it is the person themselves: « every morning,
e-mail me the weather » could not run in a routine — the effect gate refuses a draft
unattended — and in a conversation the person was asked to confirm a message to their
own mailbox. ADR-290 already answered the same question for the telephone: `call_me`
calls the verified number of the account holder, is `reversible`, and a routine may run
it.

Detecting « the recipient happens to be my address » inside `send_email_tool` was
rejected with the owner (Q2): a recipient parameter that sometimes skips confirmation is
a parameter an injected instruction can aim at.

## Decision

1. **A tool of its own, `send_email_to_me_tool`** (`email_agent`), whose recipient is
   NOT a parameter. `mutation_policy="reversible"`, with the written reason the boot
   assert requires: the message lands with the person who asked for it, who can delete
   it. The gate therefore LEDGERS it, in a conversation and in a routine alike.
2. **Where it goes (Q1).** A connected, ACTIVE mailbox sends to its OWN address, as the
   provider states it — `EmailClientProtocol.get_own_address` on the three clients
   (Gmail's profile, Graph `/me` with `mail` then an address-shaped
   `userPrincipalName`, the Apple ID), pinned by the parity contract. A mailbox that
   states no address refuses rather than guesses. Without a mailbox, LIA's own mail
   relay sends to the account's address — only when that address is VERIFIED, or an
   account opened with somebody else's address would make LIA a relay aimed at them. A
   mailbox that is connected but broken is not usable: the relay delivers and the
   « Reconnect » notice says why the message did not come from it.
3. **One content resolution for both send tools** (`agents/emails/content_generation.py`):
   subject and body, or a creative instruction, or the person's own message as the
   instruction. The note-to-self case writes a note, never a letter to a third party
   (`NOTE_TO_SELF_RECIPIENT`, rule 6 of the versioned content prompt). The generation
   receives the run's config, so the turn's tracker bills it, and its spend road moved
   with it (`LLM_SPEND_ROADS`).
4. **The relay never renders model text as markup**: a plain body is HTML-escaped into
   the relay's HTML part, an HTML body gets a readable plain part.
5. **Nothing reads as sent unless a provider or the relay accepted it**; every failure is
   returned classified (ADR-303), never raised.
6. The planner and the e-mail agent learn when to choose it (their versioned prompts),
   and the skill generator's catalogue documents it.

## Consequences

- « E-mail me X every morning » runs unattended, ledgered like a phone call to oneself.
- Found on the way and fixed: `send_email_tool` logged the instruction and the subject
  at INFO, Outlook logged recipients and subject — counts only now; dead classes and a
  phantom `attachment` keyword left the e-mail module (its size cap fell from 1 253 to
  1 033 logical lines).
- A typed own address in `send_email_tool` still asks for confirmation — by decision.

## Amendment 2026-09-27 — a draft send refused in a routine names this tool

### Context

Measured on production on 2026-09-27: one account's morning routines were told to
e-mail their result to the person. Four called `send_email_to_me_tool`; the fifth
called `send_email_tool`, although every tool of the account was bound (223) and the
e-mail domain detected, and although the draft tool's own schema says that an e-mail to
the user themselves goes through `send_email_to_me_tool`. The routine's instruction
carries no address (checked on the row, without reading its words). The gate refused
the draft — rightly: nobody can confirm in a routine — with « report that the action is
waiting for the user, and never announce it as done »; the loop obeyed, and nothing was
sent. ADR-310's ladder starts with « the loop's own call corrected », and nothing told
the loop which call would work.

### Decision

1. **A confirmation-free tool declares the draft it stands in for, and in which case**:
   `ToolManifest.stands_in_unattended_for = UnattendedStandIn(tool, when)`.
   `send_email_to_me_tool` declares `send_email_tool`, « the recipient is the user
   themselves ». The manifest is where a tool says what it owes (ADR-263); a table in the
   gate would be a second one.
2. **The unattended refusal names it** (`effects/runtime.py::_nameable_stand_in`, text
   `effects/gate.py::unattended_refusal_message`): if the case holds and the tool is among
   the model's tools, call it instead — it needs no confirmation; otherwise report that
   the action waits for the user. The wording is conditional because the gate, installed
   on the capability, never sees the turn's tool list, and the model does. Nothing else
   moves: the draft is still refused, recorded and counted, and « Nothing was performed »
   is still said.
3. **Only a loop is told** (`ClaimRequest.execution_mode == "react"`). The pipeline's
   response node calls no tool, so a name there invites an answer announcing work the
   turn will never do (ADR-248, invariant 1); a pipeline routine keeps the former message.
4. **The boot refuses a declaration that cannot help** (`assert_unattended_stand_ins`, in
   `startup/agents.py::_assert_effect_completeness`): a stand-in for a tool that does not
   exist or is never refused unattended (neither `confirm` nor `draft`), a stand-in that
   needs a confirmation itself (the loop would be refused twice in one turn), a missing
   case, two stand-ins for one draft (the refusal names one).
5. `effect_refused` logs the stand-in it named, a tool name.

### Alternatives rejected

- Letting `send_email_tool` skip its draft when `to` is the person's own address: Q2
  above, unchanged — a recipient that sometimes skips confirmation is an injection target.
- Publishing the bound tool list to the gate for one sentence: an ambient variable the
  node at its size cap would have to feed, where a conditional clause the model can check
  costs nothing.
- Rewording the draft tool's description or the ReAct prompt: the schema the loop binds
  already says it, and the planner reads it in the self-send tool's description. The
  model chose wrong once in five with the information in front of it; what was missing
  was the way back.

### Consequences

- A routine that reaches for the draft send to e-mail the person themselves can correct
  its call in the same turn.

### Measured (2026-09-27, `task react:recovery:measure`, 0.27 USD)

The `stand_in_*` scenarios open on the refused draft — the news searched, the draft send
refused with the gate's own text — and bind the two send tools under their real names,
descriptions and schemas; `--bind-catalogue` adds every registered tool (142, 48 381 schema
tokens — production bound 223) for a production-sized prefix. Runs where the self-send was
called, and, for an e-mail to a third party, where it was wrongly called:

| Prefix | Model family | Named (this change) | Unnamed (before) | Third party, wrongly |
|---|---|---|---|---|
| 3 tools | deepseek-flash | 5/5 | 5/5 | 0/5 |
| 3 tools | gpt-6-luna | 5/5 | 5/5 | 0/5 |
| 3 tools | gemini-3.7-flash | 5/5 | 5/5 | 0/5 |
| 3 tools | qwen3.7-flash | 5/5 | 3/5 | 0/5 |
| catalogue | deepseek-flash | 5/5 | 5/5 | 0/5 |
| catalogue | qwen3.7-flash | 5/5 | 1/5 | 0/5 |

The named stand-in was followed in 30 runs of 30 and never taken for a third party (0 of
30), which is the conditional wording doing its job: the third party's mail is reported as
waiting. Without the name a model family already recovers most of the time on a small
prefix and falls to 1 in 5 on a production-sized one. The production turn itself (the
account's thread, its context blocks, 223 tools) is not reproduced: the model that gave up
there recovers in every harness run.
