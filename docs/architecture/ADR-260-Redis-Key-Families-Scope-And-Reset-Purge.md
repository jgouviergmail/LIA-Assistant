# ADR-260 — Redis key families declare their scope; the reset purges by family

**Date**: 2026-09-03
**Status**: Accepted
**Context**: A production audit of three silent loops (Google push, learned
habits, proposals inbox) found one plumbing cause under all three.
`reset_conversation` deleted every Redis key matching `*:{user_id}:*`,
`*:{user_id}` and `{user_id}:*` (plus the same three on the conversation id,
which equals the user id for every row in production). The purge was written
when Redis held only caches and was never re-read after ADR-140, ADR-214,
ADR-232 and the Gmail delta anchor (lot G) started storing *learning* there.
Measured on the primary account: 161 resets in 56 days (34 on 2026-09-02),
each wiping the recurrence ledger (20/20 keys), the Gmail history anchor, the
per-user adaptive threshold and the briefing's last-known-good values, and
deleting a rate-limit key (`user:{uid}:contacts_search`) and the SSE
connection registry as a side effect. Loki showed the ledger seed — which
only runs on an *empty* ledger — firing 39 seconds after three resets, while
the ledger of a user who never resets had survived 13 days in the same Redis
(AOF on, persistent volume, zero evictions). A recurrence lock needs 14
distinct days: no proposal could ever exist.

## Decision

1. **Every Redis key family declares a scope** in
   `infrastructure/cache/key_families.py`: `CONVERSATION` (HITL, active run,
   tool contexts), `USER_CACHE` (per-user TTL caches), `USER_LEARNING`
   (recurrence ledger, Gmail delta anchor, adaptive thresholds, last-known-good
   briefing values, presence, psyche state), `USER_RUNTIME` (sessions, rate
   limits, SSE registries, one-time tokens) or `GLOBAL`. The match is
   longest-prefix on `:` segments, so `briefing:v2:lastgood` (learning) wins
   over `briefing:v2` (cache).
2. **The conversation reset purges by family, never by pattern alone.** The
   six historical SCAN patterns are unchanged — no key that used to be
   matched escapes the scan — but a matched key is deleted only when its
   family is `CONVERSATION` or `USER_CACHE`. Learning and runtime keys are
   kept and counted (`conversation_reset_keys_kept_total{scope}`); an
   **undeclared family is never purged** and is counted
   (`reset_undeclared_family_total{family}`), because silent deletion is
   exactly how learning died invisibly. The purge lives in
   `domains/conversations/reset_purge.py`; the frozen service keeps one call.
3. **Two guards make the registry complete by construction.** The boot gate
   `assert_key_families_complete` refuses to start when a `core.constants`
   prefix names an undeclared family; the source scan
   `tests/unit/test_redis_key_family_guard.py` does the same for keys built
   from literal f-strings (`heartbeat:birthdays`, `meetings:start`,
   `relations:context:v2` had escaped the constants). On first run the two
   guards surfaced three more undeclared families (`hitl_rate_limit`, `bm25`,
   `health_metrics_ingest`).
4. **The forget surfaces own the learning keys.** Account deletion deletes
   every family declared user-scoped through the same scan (it is the one
   surface that removes learning and runtime keys); « Tout oublier » in the
   habits settings deletes the recurrence ledger it used to leave behind.

## Alternatives rejected

- **A deny-list of protected prefixes** on top of the pattern purge. A new
  learning family would be purged by default until someone remembered the
  list — the failure mode this ADR exists to close. The allow-list inverts
  the default: unknown means kept, and counted.
- **Renaming learning keys away from the user id** (e.g. `learning:{uid}`)
  so the patterns miss them. It hides the decision in a naming convention no
  guard can check, and account deletion would then miss them too.
- **Removing the Redis purge from the reset altogether.** HITL state, active
  run markers and per-user caches genuinely belong to the conversation the
  user asked to forget; the reset must still clear them.

## Consequences

- A reset no longer resets a rate limit, drops an SSE registry entry under a
  live stream, or discards the briefing's fallback values.
- The recurrence ledger, the Gmail anchor and the adaptive controller now
  accumulate across resets. Combined with ADR-214's amendment on human-turn
  sources (same programme), this is what lets a proposal exist.
- Systemic rule (CLAUDE.md, Persistence): any Redis key named by a user id
  declares its family's scope; the guards fail the build otherwise.
- Dashboards: « Conversation Reset (ADR-260) » row in
  `09-conversations-users.json` (deleted by family, kept by scope, undeclared
  families) with `or vector(0)` so a green zero renders as zero.
