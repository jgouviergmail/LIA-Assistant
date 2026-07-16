"""Systemic guard for the scheduler-lock timing invariant (audit class B / F003).

``SchedulerLock.__aexit__`` intentionally does NOT release the lock — it lets it
expire via TTL. That is safe only when the job's interval is strictly LONGER than
the lock TTL. When ``TTL >= interval`` the lock is still held when the next tick
fires, so the job is silently throttled to roughly one run per TTL. F003 was the
worst case: ``scheduled_action_executor`` (60 s interval, 300 s TTL) ran once per
five minutes; it was fixed by removing its now-redundant lock (leader election +
``max_instances=1`` + FOR UPDATE SKIP LOCKED already guarantee single execution),
so it no longer appears below.

This guard enforces ``lock_ttl < interval`` for every interval-triggered job that
still uses a ``SchedulerLock`` at the default TTL. ``KNOWN_THROTTLED`` holds the
jobs that violate it TODAY at default settings (accepted debt: they keep the lock
for failover safety and lack a DB-level idempotency guard). The allowlist is a
ratchet — it may only SHRINK. A second test fails if an allowlisted job is no
longer throttled, forcing its removal once fixed.

Mapping note: this list mirrors the ``add_job(trigger="interval", ...)`` calls in
``startup/schedulers.py`` whose bodies wrap work in ``SchedulerLock``. A new such
job that ticks faster than the lock TTL fails this guard by design.
"""

from src.core.config import settings
from src.core.constants import SCHEDULER_LOCK_DEFAULT_TTL_SECONDS

# job_id -> callable returning its interval in SECONDS from settings.
SCHEDULER_LOCK_INTERVAL_JOBS = {
    "interest_notification": lambda s: s.interest_notification_interval_minutes * 60,
    "token_refresh": lambda s: s.oauth_proactive_refresh_interval_minutes * 60,
    "oauth_health": lambda s: s.oauth_health_check_interval_minutes * 60,
    "heartbeat_notification": lambda s: s.heartbeat_notification_interval_minutes * 60,
}

# Jobs that violate ``TTL < interval`` at DEFAULT settings. Accepted throttle debt
# (they retain the lock for failover safety and have no DB-level idempotency
# guard like the executor's FOR UPDATE SKIP LOCKED). Ratchet: only ever shrink —
# fix a job (remove the redundant lock, or give SchedulerLock owner-token release)
# and delete its entry.
KNOWN_THROTTLED: set[str] = {"oauth_health", "interest_notification"}


def test_interval_jobs_are_not_throttled_by_their_lock_ttl():
    """Every non-allowlisted interval SchedulerLock job must tick faster than its TTL."""
    ttl = SCHEDULER_LOCK_DEFAULT_TTL_SECONDS
    violations = []
    for job, interval_fn in SCHEDULER_LOCK_INTERVAL_JOBS.items():
        if job in KNOWN_THROTTLED:
            continue
        interval = interval_fn(settings)
        if ttl >= interval:
            violations.append(f"{job}: TTL {ttl}s >= interval {interval}s (throttled)")
    assert not violations, "Scheduler-lock timing violations (F003 class):\n" + "\n".join(
        violations
    )


def test_allowlist_only_holds_still_throttled_jobs():
    """Ratchet: an allowlisted job that no longer violates must be removed from it."""
    ttl = SCHEDULER_LOCK_DEFAULT_TTL_SECONDS
    stale = []
    for job in KNOWN_THROTTLED:
        interval = SCHEDULER_LOCK_INTERVAL_JOBS[job](settings)
        if ttl < interval:
            stale.append(f"{job}: TTL {ttl}s < interval {interval}s — remove from KNOWN_THROTTLED")
    assert not stale, "\n".join(stale)


def test_allowlist_jobs_are_declared():
    """Guard against a typo in the allowlist that would silently disable the ratchet."""
    unknown = KNOWN_THROTTLED - set(SCHEDULER_LOCK_INTERVAL_JOBS)
    assert not unknown, f"KNOWN_THROTTLED references undeclared jobs: {unknown}"
