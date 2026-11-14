# ADR-386 — A signed call starts a routine

**Status**: Accepted, 2026-11-13.
**Date**: 2026-11-13

**Relates to**:
[ADR-322](ADR-322-One-Clock-Per-Routine.md) — a routine runs on ONE clock;
[ADR-265](ADR-265-Routine-Week-Timeline-And-Run-History.md) — one row per run, written at the result;
[ADR-280](ADR-280-Complete-Capability-Control.md) — a switch removes the capability, never the
record;
[ADR-304](ADR-304-No-Transaction-Across-A-Network-Call.md) — nothing held across a wait;
[ADR-286](ADR-286-Tool-Result-Projected-Per-Item-Under-A-Token-Budget.md) — what comes from outside is
data, wrapped as such.

## Context

A routine runs on a schedule, or on a condition the system checks (ADR-322). Many events happen
first in another system: a door sensor in a home automation box, a release in a code forge, a
form submitted, a build that failed. LIA cannot poll them all, and most of them can call an
address. Lot 22 of the programme drawn from hermes-agent (an inbound webhook starts a scheduled
job, signed by HMAC, deliveries coalesced), approved by the owner with wave 5.

## Decision

1. **A third clock: an outside call.** A `webhook` routine has neither a recurrence nor a
   condition: it runs when its address is called. The one rule that pairs a routine's fields with
   its clock (`schemas.trigger_mode_refusal`) and the table's `CHECK`
   (`ck_scheduled_actions_one_clock`) gain the third pair; a second `CHECK`
   (`ck_scheduled_actions_webhook_address`) gives such a routine, and only it, an address and a
   secret. A webhook routine never proposes first: a proposal hands the run to the chat, which
   would never read the calls it serves.

2. **The address and its secret are the server's, and the secret is shown once.** Starting to run
   on calls — at creation, or by a switch of clock — draws a random key (the address) and a random
   secret; the secret is stored encrypted (`encrypt_data`), because checking an HMAC needs it in
   clear, and leaves the server in ONE answer: the request that drew it. The form shows it in a
   dialog that says so; a routine created by the assistant shows none, and its owner draws one
   (`POST /scheduled-actions/{id}/webhook-secret`), which retires the previous one at once. This
   is the precedent of the ingestion tokens (shown once). Neither the key nor the secret travels
   in a log, a chat message or the account export (`_REDACTED_COLUMNS`); leaving the clock erases
   both, and the calls still waiting with them.

3. **The call is signed, and nothing else authenticates it.** `POST /api/v1/hooks/routines/{key}`
   takes no session. Its body (at most `ROUTINE_WEBHOOK_MAX_BODY_BYTES`, refused from its declared
   length or while it streams) is signed with HMAC-SHA256 under the routine's secret, in
   `X-LIA-Signature-256: sha256=<hex>` — `X-Hub-Signature-256`, the same scheme under the name code
   forges send, is read alike — and compared in constant time on the decoded digest. The answers:
   202 (accepted, or a delivery already accepted), 403 (no valid signature —
   `raise_invalid_webhook_signature`, like the other inbound webhooks; or the capability closed,
   by its guard), 404 (no webhook routine at this address, or a paused one: the same answer, so an
   address tells a stranger nothing), 413 (too large), 429 (a client's window, the address's own
   window, or as many calls waiting as a routine may keep). The answer never waits for the run.

4. **Nothing is held across a wait.** The routine is READ by its address and the read ends before
   the address's call window is asked in Redis; the WRITE then takes the routine's row lock for the
   duplicate check, the backlog bound, the insert and the arming, and commits before the 202. A
   run's settle takes the same lock, so neither can slip between the other's steps.

5. **A delivery is written before it is acknowledged, and served from an explicit success.** Each
   accepted call is a row (`routine_webhook_deliveries`: when, the sender's delivery id when it
   gives one, the declared media type, the size, the body read as UTF-8 text and encrypted). A
   delivery id seen again for the same routine is answered as a duplicate and not stored twice (a
   partial unique index, `ON CONFLICT DO NOTHING`). The call wakes a sleeping routine for the
   scheduler's next pass — within a minute; an instant already armed stands, so a call arriving
   during a failed run's back-off (decision 7) waits for it with the others, and calls arriving
   together are coalesced into one run. The run takes
   at most `ROUTINE_WEBHOOK_MAX_PER_RUN` waiting calls, oldest first, and marks them served in the
   transaction of the routine's own settle, under the same fence as a condition's ledger, only
   when it answered: the body is erased then, and the row stays
   `ROUTINE_WEBHOOK_SERVED_RETENTION_DAYS` so the same delivery, sent again, is recognised.

6. **What the caller sent is data, never an instruction.** The run's request is the routine's own
   instruction, followed by a note naming each call — dated in the routine's zone, sized, its
   body wrapped as another system's words (`wrap_external_content`) and cut at
   `ROUTINE_WEBHOOK_PROMPT_CHARS` with the cut stated; an empty body and an unreadable one are said.
   The media type a call declares is named beside it only when its header is a media type and
   nothing more (`declared_media_type`: a registered top-level type, a restricted name, no
   parameter) — the header is the caller's words too, unsigned, and read outside the envelope.
   The note's words are a versioned lines file (`routine_webhook_lines`). A body cannot change
   what the routine does; it can only be what the routine reads.

7. **The clock re-arms itself honestly.** The plan of a webhook routine (`TriggerPlan`) looks
   again at the next pass after any tick — its gate serves what still waits, or settles asleep
   (`next_trigger_at` NULL) under the routine's lock, where a call that slipped in since the read
   re-arms it at once — on the switch the tick read before taking that lock, since nothing is
   asked of a store while the row is held (ADR-304). After a FAILED run it backs off
   `ROUTINE_WEBHOOK_FAILURE_RETRY_SECONDS` (the run already retried inside itself), so a provider
   down for minutes is not a model call a minute and a pause after five. A stand-aside (a busy
   account, a pending question, the usage ceiling) writes no run row — its calls wait — and a
   webhook routine is never closed as finished: its NULL trigger is a sleep, not an end. A
   routine started by calls is not run by hand: there is nothing to run without a call.

8. **Bounded on every side.** `ROUTINE_WEBHOOK_MAX_PENDING` calls waiting per routine,
   `ROUTINE_WEBHOOK_RATE_PER_MINUTE` calls a minute per address (failing open, like every throttle
   of ours), `RATE_LIMIT_ROUTINE_WEBHOOK_PER_IP_PER_MINUTE` a minute per client across every
   address, `ROUTINE_WEBHOOK_MAX_PER_RUN` calls a run.

9. **One switch, three places.** `PlatformCapability.ROUTINE_WEBHOOKS` (ceiling
   `ROUTINE_WEBHOOKS_ENABLED`, the operator's switch inside it): the public address refuses, a
   routine cannot start running on calls (`require_capability_fresh`, a write) nor draw a new
   secret, and a run serves nothing — while the routines, their addresses and the calls already
   accepted stay recorded (ADR-280); calls waiting behind a closed switch are looked at again after
   the back-off, so a switch that reopens finds them served. The router is mounted by its own
   ceiling, so the web reads the capability map alone (`CAPABILITY_CEILING: null`). The
   demonstrator keeps it off.

## Consequences

- Every reader of a routine's clock knows the third one: the For-you card, the assistant's
  listing, the hub and the alert sort announce a next run for a SCHEDULE only; the portrait says
  « when another system calls it »; a discussion's planned routines exclude it; the form offers the
  clock where the capability is open and keeps it on a routine that runs on it.
- `routine_webhook_calls_total{outcome}` counts what each call became and
  `routine_webhook_calls_served_total` what runs served, on the proactive dashboard; one log line
  per call a routine was found for (`routine_webhook_call`) carries the routine's id, the outcome
  and the size, never a body, a key or a sender's words.
- The deliveries are not exported: transient inputs of a run, erased once served and purged a week
  later; the runs they started and their answers are.

## What this decision leaves, and says so

- A sender that cannot sign (a bare URL in a third-party form) cannot start a routine: an
  unsigned address would be a public trigger of the person's assistant.
- A delivery is not answered back to its sender: the routine's result goes where every routine's
  goes (the chat, a notification).
- A body is read as UTF-8 text; bytes that are not are replaced. A binary payload is not a use
  case: the run is a model reading what it was sent.
- Rotating the secret without a gap (two valid at once) is not offered: drawing a new one retires
  the old at once, and the dialog says so before it happens.
- Served exactly once holds while the routine's reservation holds — the same fence as a
  condition's ledger; a run whose reservation the recovery took from it (a run outliving its
  worst case) leaves its calls to the next tick.

## References

- `apps/api/src/domains/scheduled_actions/webhooks.py` — keys, secrets, signatures, headers, the run's note
- `apps/api/src/domains/scheduled_actions/webhook_service.py` — the door's decision
- `apps/api/src/domains/scheduled_actions/webhook_router.py` — the public route
- `apps/api/src/domains/scheduled_actions/webhook_repository.py` — the deliveries
- `apps/api/src/domains/scheduled_actions/webhook_address.py` — the address on a clock change
- `apps/api/src/infrastructure/scheduler/routine_webhook_gate.py` — what a tick serves, when it rests
- `apps/web/src/components/settings/RoutineWebhookSecretDialog.tsx` — the secret shown once
- [ROUTINE_WEBHOOKS.md](../technical/ROUTINE_WEBHOOKS.md) — the mechanism, the sender's side, the limits
