# ADR-261 — Push-driven heartbeat wake and incremental Drive sync

**Date**: 2026-09-03
**Status**: Accepted
**Context**: Lot H (2026-08) opened Google push channels — Calendar
`events.watch`, Drive `changes.watch`, Gmail `users.watch` through Pub/Sub —
and the audit of 2026-09-03 measured them alive (802 Gmail notifications
processed in 15 days, 0 bad tokens, channels renewed) and functionally
inert: their only consumer was `invalidate_for_provider`, which drops the
matching briefing section and the Gmail search caches. Nothing event-driven
followed. The heartbeat kept reading mail on its own 30-minute tick through
`history.list`; the Drive `page_token` stored at channel opening was never
read; a changed agenda never refreshed the departure advice. A push that
buys freshness for a card the user may not open is a push that changes
nothing the user notices.

## Decision

1. **A processed notification queues a wake, and the webhook stays dumb.**
   After the existing invalidation, `PushChannelService` enqueues
   `(user, provider)` with what it already holds (the Gmail history id it
   just saw, the Drive page token) — `SET NX EX` on
   `heartbeat:wake:payload:{user}:{provider}` (a storm is ONE wake, dated by
   the first) plus `SADD heartbeat:wake:pending` — and answers 200. Flag
   `PUSH_WAKE_ENABLED` (OFF by default); failures cost a wake, never a
   webhook.
2. **A short leader-elected sweep serves the queue under the FULL
   eligibility checker.** Every `PUSH_WAKE_SWEEP_INTERVAL_SECONDS` (120,
   jittered per ADR-254), `heartbeat_wake_sweep` pops users (`SPOP`: two
   workers never serve the same one), then in order: staleness bound, wake
   cooldown (`SET NX`), the user's source preference (`source_policy` — a
   refused source never wakes), the fresh delta, the deterministic
   pre-filter, and finally the heartbeat task **for that user only** through
   the existing `ProactiveTaskRunner`. The runner gains `user_ids` and
   `skip_probabilistic_gate`: a wake answers an event, so the "guaranteed
   minimum" smoothing is bypassed — and nothing else. Notification window,
   daily quota, global and cross-type cooldowns, activity cooldown all
   apply. Measured before deciding: without the bypass, a legitimate wake
   was refused at random by `probabilistic_skip`.
3. **The Gmail delta is previewed, never consumed, until the wake is
   served.** The sweep reads `history.list` from the heartbeat's own
   consumption anchor WITHOUT storing anything; a refused wake therefore
   leaves the mail for the next tick. When the wake is served, the payload
   carries the metadata the pre-filter fetched into the aggregator, which
   uses it instead of the delta fast-path and advances the anchor on the
   tick's behalf. The two anchors stay distinct on purpose: the channel's
   `last_history_id` is the last event *seen*, the heartbeat's is the last
   mail *consumed*; merging them would drop every mail between a consumed
   tick and a later push. The heartbeat anchor is a `USER_LEARNING` key
   (ADR-260), so a conversation reset no longer erases it.
4. **The pre-filter is deterministic and published.** Mail wakes only when a
   new INBOX message carries a required label (Google's own `IMPORTANT` by
   default), none of the excluded categories (promotions, social, forums)
   and is not list mail (`List-Unsubscribe`, bulk/list `Precedence`). A
   calendar change wakes only for an event starting within the lookahead,
   updated in the last minutes, by someone other than the user or with the
   user's answer still pending. Every rule is a `PUSH_WAKE_*` setting, every
   verdict a bounded reason. **No "favourite sender" rule**: neither
   `relation_favorites` nor `relation_aliases` carries an e-mail address
   (measured), so the rule would have been improvised; it is a stated
   evolution, not a silent approximation.
5. **The decision knows why it was woken.** `HeartbeatContext.wake_trigger`
   renders a FRESH line at the top of the decision prompt; the audit row
   persists `trigger = push | tick` and the API publishes it, so the
   timeline can say a notification answered an e-mail or an invitation
   rather than a clock.
6. **Drive push reindexes exactly what changed.** A Drive wake is not a
   decision: the sweep drains `changes.list` from the channel's token, keeps
   the changes whose file sits directly under a linked folder
   (`rag_drive_sources`), and — per source, under the same sync lock the
   manual sync uses — ingests the changed files and removes the trashed
   ones, then advances the token. The per-file ingestion was extracted from
   `drive_sync.py` into `drive_ingest.py` so the full sync and the push
   reindex share ONE implementation (ADR-255: two readings diverge).
7. **A changed agenda invalidates the departure advice** (`heartbeat:
   departure:{user}:*`), so the next pass recomputes it from fresh events.

## Alternatives rejected

- **Deciding in the webhook.** It must answer 200 fast and reveal nothing;
  a decision there would also run outside the leader election and the
  eligibility checker.
- **A separate "urgent" notification path bypassing the heartbeat budget.**
  The owner's budget (window, quota, cooldowns) is the contract; the wake
  only changes WHEN a decision is taken, never how many may fire.
- **Merging the two Gmail anchors.** Explained above: different meanings.
- **An LLM pre-filter.** The point of the pre-filter is to avoid spending a
  decision on noise; spending an LLM call to decide whether to spend an LLM
  call is the noise.

## Consequences

- A notification can now follow an important mail or a fresh invitation
  within minutes instead of "≤ 30 min if the tick falls well" — at a lower
  cost per decision (a smaller, fresher context) and under the same budget.
- New metrics, all on the proactive dashboard: `push_wakes_total{provider,
  outcome}`, `push_wake_latency_seconds`, `rag_drive_push_reindex_total
  {outcome}`.
- New settings block `PUSH_WAKE_*` in `.env.example`; production ships with
  the flag OFF until the first served wake is read on the dashboard.
- Startup: the push jobs (sync + sweep) live in
  `infrastructure/startup/scheduler_push.py`, listed in the jitter guard and
  the first-run guard next to `schedulers.py` (frozen file).

## Amendment 2026-10-01 — nothing left to bypass (ADR-328)

The heartbeat has no daily quota and no probabilistic pacing any more, so a wake
runs under exactly the checker a tick runs under, and `skip_probabilistic_gate`
is gone. In point 2, « daily quota » leaves the list of gates; the notification
window and the global, cross-type and activity cooldowns still apply.

## Amendment 2026-11-11 — a mail wake announces unread mail only

**Finding.** The pre-filter asked whether a new inbox message was important, never
whether it was still unread, and the aggregator listed every message of a wake or of
a Gmail delta under « UNREAD EMAILS ». A message the person had opened, and answered,
between its arrival and the sweep could therefore wake the decision and be announced
with an offer to reply. Proved on 2026-11-11 by running the real aggregator against a
mailbox holding one opened message: it was listed on both roads.

**Decision.** Unread is the DEFINITION of the heartbeat's mail source, not a tunable,
so point 4's « every rule is a setting » does not extend to it. `mail_passes` refuses
an opened message last, under the bounded reason `already_read`; the aggregator keeps
only the messages the mailbox still marks unread on its three roads (search, delta,
wake). What a decision looks at is bounded apart from what it lists
(`PUSH_WAKE_MAIL_MAX_MESSAGES` new messages, `HEARTBEAT_CONTEXT_EMAILS_MAX` listed), so
an opened message never takes the place of an unread one behind it. The verdict reads
each message FRESH at the sweep and on the delta: a copy cached when the mail arrived
would still say « unread » of a message opened since. The label has one reading
(`core.mail_vocabulary.is_unread`), fail-closed: a message carrying no labels is not
unread. A mail watch is untouched: it waits for an arrival, and still arms on an
opened message.

**Proof.** `tests/unit/domains/heartbeat/test_mail_context.py`,
`tests/unit/domains/push_channels/test_wake_filter.py`,
`tests/unit/infrastructure/scheduler/test_wake_mail_watches.py`.

**Since.** Unread is not unanswered either: the same source now leaves out a mail the
person already answered and says when an answer sits unsent in their drafts
([ADR-379](ADR-379-A-Listed-Mail-Says-Whether-It-Was-Answered.md)). The source lives
in `domains/heartbeat/mail_context.py`.
