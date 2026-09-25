# ADR-314 — An e-mail to oneself needs no confirmation, and a routine can send it

**Status**: accepted — 2026-09-24 (owner request: no HITL and no draft for e-mails sent to the user's own address — like the personal phone call — so a routine can mail the user; owner arbitration Q1: the connected mailbox's own address, and without a connected mailbox the account's address through LIA's own mail; Q2: a typed own address is NOT detected)
**Amends**: ADR-263 / ADR-276 (the effect gate LEDGERS a `reversible` action where it refuses a draft), ADR-290 (the `call_me` precedent), ADR-303 (failures returned, classified), ADR-304 (the send's content generation keeps the turn's config)

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
