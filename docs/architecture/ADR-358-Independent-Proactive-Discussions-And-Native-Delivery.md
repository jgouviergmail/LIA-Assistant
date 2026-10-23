# ADR-358 — Independent proactive discussions and native delivery

**Status:** Accepted — implemented on the native application contracts; qualification boundaries below.
**Date:** 2026-10-20
**Deciders:** Product owner, with inline engineering analysis.
**Scope:** Personal conversational initiative, publication and continuity in the existing chat.

## Context and problem statement

Proactive notifications already identify facts worth bringing to the person's
attention. A personal conversation can be welcome without an alert, deadline or
practical task. Making the notification prompt more sociable would mix these two
purposes, their cadence and their acceptance criteria. It could also consume an
alert's allowance or interrupt an ongoing human exchange.

The person approved a separate feature, the same distribution as current
proactive notifications, the active conversational style, and complete settings
and internal-tool coverage. This is not permission for autonomous business
mutations or a change to existing notification behavior.

## Decision drivers

- Preserve the notification engine and its existing sources, timing and quotas.
- Prefer a useful or pleasant opportunity over a requirement to fill a quota.
- Keep identity, archive, effects, consent and accounting on native contracts.
- Give human turns, pending approvals and alerts priority over this optional work.
- Make the decision and its publication independently testable without a live model.

## Considered options

| Option | Assessment |
|---|---|
| Extend the heartbeat prompt and counters | Less initial wiring, but couples alert eligibility, conversational pressure and regression risk; rejected. |
| Run the ordinary LangGraph agent on a synthetic human message | Reuses orchestration but invents a human turn and exposes unnecessary action capabilities; rejected. |
| Separate bounded domain, native archive and delivery | Additional coordination and persistence, with explicit policy and test seams; selected. |

## Decision outcome

Create the [proactive discussions domain](../../apps/api/src/domains/proactive_discussions/).
It owns opt-in, local activity hours, optional daily opening limit, pause, source
choices and sensitive-topic choices. The notification policy remains independent;
in particular this feature does not restore an alert quota removed by
[ADR-328](ADR-328-Heartbeat-Without-A-Daily-Quota.md).

The domain orchestrates bounded read-only context, a structured `skip`, `defer`
or `engage` decision, and a separate wording step. It does not add a graph node
to the interactive turn. Abstention is a normal result; silence is neither a
failure nor a negative opinion attributed to the person. The active style and
language affect wording, while sarcasm cannot override topic sensitivity or
human directives.

Use owner-bound runs, revision checks, leases and fencing tokens. Revalidate the
current clock, civil-day allowance, source authority, context generation, human
activity, approval state and competing alerts before publication. Unknown
attention state defers this discretionary feature. A discussion must not update
a shared cooldown in a way that suppresses an existing alert.

An opening is one native **assistant** archive message, one logical opening and
one durable outbox intent, atomically persisted. A replay cannot change its
content or increment the daily allowance again. The
[publication repository](../../apps/api/src/domains/proactive_discussions/publication_repository.py)
uses the [shared archive contract](../../apps/api/src/domains/shared/discussion_archive.py)
and [native persistence adapter](../../apps/api/src/infrastructure/proactive/discussion_persistence.py).
Prepare the conversation outside the publication transaction: the existing
conversation creation service may commit internally.

Reuse eligible native SSE, push and external-channel delivery. Do not create a
second archive per transport or equate transport acknowledgement with physical
display. Inherit applicable source privacy; SMS-derived context remains subject
to [ADR-357](ADR-357-Phone-Ingestion-And-Personal-SMS-Archive.md). A retry carries
the same opening identity; an uncertain external effect cannot justify an
unbounded replay. Publication and network delivery remain separate, following
[ADR-304](ADR-304-No-Transaction-Across-A-Network-Call.md).

The person's reply references the actual opening when that relationship is
known, then uses the ordinary conversation flow. Do not attach an unrelated late
reply to whichever opening is currently pending. Radio and briefing readers
must not repeat the new conversational question as a fresh alert or evidence.

Authenticated settings and context management remain available when initiative
is disabled. Internal tools in Pipeline and ReAct share the same typed owner
commands and server-enforced approval contracts for their mutations. Ordinary
settings controls follow the native settings UX; the model never self-approves
a write. The interface uses existing primitives, all supported locales,
mobile reflow, keyboard focus and accessible asynchronous feedback.

## Consequences

The feature can be disabled, budgeted and qualified separately, and the existing
notification flow remains a regression oracle. The cost is an explicit attention
coordinator, publication fencing and outbox lifecycle. Account export, erasure,
conversation reset, source withdrawal and pending-opening expiry must all have
defined behavior before an active producer is installed.

This decision authorizes an architecture, not a production activation or a
claim of conversational quality. Human evaluation of tone and relevance remains
necessary alongside deterministic tests.

## Implementation state and verification

The independent scheduler is wired through [scheduler startup](../../apps/api/src/infrastructure/startup/scheduler_discussions.py) and the [native runner](../../apps/api/src/infrastructure/proactive/discussion_runner.py). Paid production requires explicit operator budgets and personal opt-in. A native conversation lease protects final publication; the assistant archive, logical opening and outbox commit atomically. Delivery retains stable identities, fresh source authority, native privacy and acknowledgement uncertainty.

Session API, settings, context/history controls and Pipeline/ReAct tools are installed. The ordinary chat preserves the opening when the person replies; memory extraction consumes genuine replies and complete procedural directives. The new opening is excluded from Radio journal extraction. Existing notification admission and counters are unchanged.

[Producer-flow tests](../../apps/api/tests/integration/domains/proactive_discussions/test_producer_flow.py), [outbox tests](../../apps/api/tests/integration/domains/proactive_discussions/test_outbox.py), [claim races](../../apps/api/tests/integration/domains/proactive_discussions/test_claims.py) and [local-day tests](../../apps/api/tests/unit/domains/proactive_discussions/test_local_day.py) exercise the native persistence and orchestration contracts with fictional providers. The [browser journey](../../apps/web/e2e/smoke/proactive-discussions.spec.ts) defines the settings, exclusion and purge checks. Actual device display and perceived conversational quality remain product-pilot qualifications, not consequences inferred from a successful transport receipt.

## Amendment 2026-10-21 — cold review before release

Each point closes a defect found by reading or measuring the staged lot.

- **ADR-357 holds for discussions.** A run that READ an SMS — a fact, or a
  context item resting on one — offered it to a model, so its opening is private
  whatever it cites: the push is masked, no external channel forwards it, Radio never
  airs it, and later decision windows never offer its words back. Before, only a
  sensitive topic made an opening private. *(Withdrawn on 2026-10-23 by the amendment
  of [ADR-357](ADR-357-Phone-Ingestion-And-Personal-SMS-Archive.md): an SMS is personal
  data like a mail, and only a sensitive topic makes an opening private again.)*
- **Delivery starts when the opening is committed**, outside the run's deadline
  ([runner](../../apps/api/src/infrastructure/proactive/discussion_runner.py)): the tick used to
  dispatch only after its whole batch, longer than the delivery authority's proof
  window, so a published opening could lose its push. The tick's sweep remains
  the fallback. Device tokens are settled like the batch sender's (stamped when
  accepted, retired when invalid), and swallowed delivery faults are logged.
- **The tick draws only owners it can serve** ([selection](../../apps/api/src/infrastructure/scheduler/proactive_discussions.py)):
  a requested rebuild first, whatever the hour, then owners whose window is open
  by the policy's own predicate. An owner outside its hours no longer takes a
  place in the batch nor has its controls read for nothing. One owner's fault is
  logged and never stops the batch or the retention maintenance.
- **Every run is counted** by `proactive_discussion_runs_total{kind, outcome}`
  ([metric](../../apps/api/src/infrastructure/observability/metrics_proactive_discussions.py)),
  drawn on dashboard 13. Expected abstentions are logged with a bounded reason code.
- **The openings appear in the notifications hub**, badged before any unfold from
  [the history page's own filter](../../apps/api/src/domains/proactive_discussions/openings.py)
  (ADR-185), and shown only while the capability is on (ADR-061).
- **A blank conversation turn is no statement**: it is filtered in SQL rather than
  failing validation and closing the whole conversation source.
- **The IMAP translator reads epoch instants**: the e-mail source spells its window
  as Gmail does, which an Apple mailbox read as no date at all (`(ALL)`, measured);
  an instant now widens to the day that holds it.
- **The sources' words for the model live in the prompt store**: each adapter's
  excerpt frame and usage nuance is a line of `discussion_evidence_lines.txt`, read
  through `core` by [one shared loader](../../apps/api/src/domains/shared/discussion_lines.py)
  (ADR-284). The rendered text is byte-identical, so no fact was re-versioned.
- **What a model reads as a schema is unchanged**: the structured-output contracts
  and the discussion tools' parameters carry comments, never docstrings or field
  descriptions, since both would become schema text and change every request.

## Amendment 2026-10-21 b — measured on the owner's production account

A rebuild the owner requested on production read its sources, interpreted nothing,
settled `completed`, and the settings announced « today's ceiling is reached » with
€0.0085 spent of €4.46. Every cause was measured on that account before a line moved
(context and spend: ADR-359 and ADR-360 amendments b); this ADR records the rest.

- **Owner decisions.** A new account consents to every sensitive topic
  (`DISCUSSION_DEFAULT_SENSITIVE_TOPICS`, the five by default) and withdraws any of
  them. A row nobody edited receives the default; an edited row keeps its list, an
  empty one included, because an empty list may be a refusal and consent to a
  sensitive topic is never inferred from one ([migration](../../apps/api/alembic/versions/2026_10_21_1110-6b2c4e8f0a17_discussion_sensitive_topics_default.py);
  production: one row, edited, already naming its topics). A recent proactive
  notification or interest alert no longer holds an opening back
  (`DISCUSSION_ATTENTION_ALERT_GAP_MINUTES=0`); openings keep their own gap.
- **Every operator bound is a setting** ([module](../../apps/api/src/core/config/proactive_discussions.py)),
  declared in the « PROACTIVE DISCUSSIONS » section of every env template (guarded by
  `test_env_template_structure_guard.py`); contradictory bounds refuse the boot
  (deadline below the lease, one read's call limit within the run's, the run ceiling
  within both day ceilings). The pause length is one of them, and an opening stamps
  the hours its « not now » label promised (`discussion_pause_hours` in its metadata),
  so a later change never breaks a promise already shown.
- **A run says why it ended.** `discussion_runs.reason` holds one code of a closed
  vocabulary ([run types](../../apps/api/src/domains/proactive_discussions/run_types.py)),
  each with its sentence in the six languages (`test_run_reason_sentences.py`), and
  `discussion_runs.stats` what it read and interpreted, in counts only. A rebuild that
  interpreted nothing settles `skipped` with its reason, never `completed`; the
  settings draw both.
- **Every source a run opens is filed** under the run's id: the runner opens a
  consultation collector (before, every row was dropped for want of one), a rebuild's
  reads are the person's (surface `proactive_discussion_rebuild`, authored `user`),
  and the delivery check files its own reads.
- **A legacy OAuth connector reads under its account**: connectors created before
  OAuth grants are bound like mailboxes ([binding](../../apps/api/src/domains/connectors/legacy_oauth_binding.py)).
  The calendar had no account identity, so every discussion read of it was refused;
  and a refusal is now stated as « provider unavailable » unless the person made it
  (consent) or the operator (feature) — told « consent », the context model read a
  refusal the person never made ([mapping](../../apps/api/src/domains/proactive_discussions/source_failures.py)).

## Amendment 2026-10-22 — the tick's capacity is the operator's too

A cold review found bounds this decision already covered still written in the code.
The tick served four owners, two at once, among two hundred examined: at the default
interval, about 384 runs a day for the whole instance, whatever its size, with no
lever but a release. They are now `DISCUSSION_TICK_OWNERS`,
`DISCUSSION_TICK_CONCURRENCY` and `DISCUSSION_TICK_CANDIDATES` (fewer candidates than
owners refuses the boot), beside the delivery sweep, the maintenance pass, the purge
batch and the default backoff (`DISCUSSION_DELIVERY_BATCH_SIZE`,
`DISCUSSION_MAINTENANCE_BATCH_SIZE`, `DISCUSSION_CONTEXT_PURGE_BATCH_SIZE`,
`DISCUSSION_BACKOFF_MINUTES`), as the other proactive producers already did, and
beside the reply guards' budget (`DISCUSSION_REPLY_GUARD_MAX_ROWS`,
`DISCUSSION_REPLY_GUARD_MAX_TOKENS`), past which every run defers — the directives'
own budget already was a setting. And a
delivery attempt is settled as uncertain once its proofs are stale
(`DISCUSSION_DELIVERY_PROOF_MAX_AGE_MINUTES`): the code held a second constant equal to
it, so raising the freshness cut a slow delivery's remaining pushes at five minutes.

## References

- [How a run works, and what its context keeps](../technical/PROACTIVE_DISCUSSIONS.md)
- [Approved design](../superpowers/specs/2026-10-19-proactive-discussions-design.md)
- [Sequenced TDD plan](../superpowers/plans/2026-10-19-proactive-discussions.md)
- [Longitudinal context and user control](ADR-359-Longitudinal-Discussion-Context-And-User-Control.md)
- [Bounded research and accounting](ADR-360-Bounded-Discussion-Research-And-Accounted-Abstention.md)
