# ADR-328 — The heartbeat has no daily quota: every tick reaches the decision

**Status:** Accepted — 2026-10-01, owner request: « a 0–8 range is not needed: the
assistant already decides when a notification is relevant, and a proactive
notification must not be missed because the limit of 8 was reached ». Owner
arbitration (option A): every tick is evaluated, with no daily cap and no
probabilistic gate; the larger register volume and model spend are accepted.

**Amends:** ADR-261 (a push wake has no smoothing left to bypass), ADR-281 (neither
has an anticipated moment), ADR-214 §4 (the heartbeat's explicit bounds are its
hour window alone).

## Context

Measured before the change:

1. The heartbeat carried two per-account settings, `heartbeat_min_per_day` and
   `heartbeat_max_per_day` (1 to 8, defaults 1 and 3), enforced twice: a hard
   quota in `EligibilityChecker._check_daily_quota`, and a probabilistic
   « guaranteed minimum » pacing in `ProactiveTaskRunner` that drew, on each
   tick, whether to evaluate at all — aiming at (min + max) / 2 a day.
2. The relevance judgement already belongs to a model: the heartbeat gathers
   its sources and asks the `heartbeat_decision` slot whether anything warrants
   interrupting the person, under explicit skip rules (recent activity, a
   meeting, a repeated topic, a low-value signal) with the content of its own
   recent notifications in the prompt. The quota refused what that decision
   would have sent; the pacing skipped ticks at random, whatever the context
   held.
3. The push wakes (ADR-261) and the anticipated moments (ADR-281) bypassed the
   pacing but not the quota: once the day's maximum was reached, the mail the
   person was waiting for, or the end of a meeting, was refused.
4. `heartbeat_push_enabled` had been read by nothing since 2026-08-05, when push
   started following the global notification opt-in alone.

## Decision

1. **The per-day bounds are optional in `EligibilityChecker`** — both or
   neither, a `ValueError` otherwise. A checker given neither answers
   `has_daily_bounds == False`: no quota refuses it, and `ProactiveTaskRunner`
   never paces it — it does not even count the day. The interests keep theirs.
2. **The heartbeat's checker has none.** Ticks, push wakes and moments share
   it, so every tick inside the window that passes the cooldowns reaches the
   task's own gates (a meeting in progress, the learned rhythm) and then the
   decision. What still bounds how often LIA speaks: the notification window,
   the global cooldown, the cross-type cooldown, the activity cooldown, the
   account's usage limits and the instance's daily budget.
3. **`skip_probabilistic_gate` is removed.** Its two callers were heartbeat
   sweeps, which have nothing left to skip.
4. **The three columns are dropped** (migration `3354f9ba30e2`; the downgrade
   restores them with their former defaults, not the values each account had
   chosen). The settings API no longer publishes them, and an update still
   carrying them is ignored, not refused, so a page that has not reloaded keeps
   saving. The panel loses its « per day » selects, and the 422 « min > max »
   goes with its message in six languages.

## Consequences

- An enabled account is evaluated on every tick of its window outside the
  cooldowns: up to window × 60 / interval decisions a day — 26 for a 9 h to
  22 h window ticking every 30 minutes — where the former pacing let through
  only the ticks its draw selected. Measured on dev before the change: about
  0.0016 € and ten consultation rows per evaluation.
- How many notifications a day is now what the decision and the cooldowns
  produce; no number caps it. The decision prompt is unchanged — its skip rules
  were already the judges of relevance. The real daily count after deployment
  is a measurement still to make, not a figure stated here.
- `EligibilityReason.QUOTA_EXCEEDED` and the `probabilistic_skip` outcome remain
  for the interests and no longer occur for the heartbeat.

## Alternatives rejected

- **Raising the maximum.** Any number refuses a notification on the day it is
  reached; the request was precisely that none be refused that way.
- **Keeping the pacing without the quota.** It skips ticks at random — the one
  that mattered included — to spread a volume nobody configures any more.
- **A « frequency » setting in place of the bounds.** It would be a second judge
  of relevance beside the decision, the very ambiguity the request removes.

## Implementation references

- `apps/api/src/infrastructure/proactive/eligibility.py` — `has_daily_bounds`
- `apps/api/src/infrastructure/proactive/runner.py` — `_paced_decision`
- `apps/api/src/infrastructure/scheduler/heartbeat_notification.py`
- `apps/api/alembic/versions/2026_10_01_1000-3354f9ba30e2_drop_heartbeat_daily_bounds.py`
- `apps/web/src/components/settings/HeartbeatSettings.tsx`
- [Heartbeat technical documentation](../technical/HEARTBEAT_AUTONOME.md)
