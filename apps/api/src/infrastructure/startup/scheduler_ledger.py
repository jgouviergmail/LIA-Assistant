"""Startup step: the ledger notary (ADR-263, lot 5).

A separate module because ``schedulers.py`` is frozen at its audited size, and
next to ``scheduler_push.py`` because it obeys the same three rules: the flag
is re-checked in the job body, the id comes from a constant, and the interval
carries ``jitter`` (ADR-254 — six jobs sharing a divisor fire on the same
second for the life of the process).

The notary runs under leader election like every other write-side job: two
instances passing at once would not corrupt anything — ``UNIQUE (user_id, seq)``
sees to that — but one of them would spend its tick losing races.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from src.core.config import settings
from src.infrastructure.startup.scheduler_jitter import jitter_seconds_for

logger = structlog.get_logger(__name__)


async def run_ledger_notary() -> None:
    """One notary pass, on its own session.

    Best-effort by design: the registers stay complete and readable whether or
    not this ran. What a failure must never do is stay quiet, so it is counted
    and logged rather than swallowed.
    """
    if not getattr(settings, "ledger_chain_enabled", False):
        return

    from src.domains.agents.effects.notary import run_notary_pass
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            report = await run_notary_pass(db)
    except Exception:
        logger.exception("ledger_notary_pass_failed")
        return

    if report.entries:
        logger.info(
            "ledger_notary_pass",
            accounts=report.accounts,
            entries=report.entries,
            chains_opened=report.chains_opened,
            failed=report.failed,
        )


def register_ledger_jobs(scheduler: Any) -> None:
    """Register the notary pass.

    Args:
        scheduler: The APScheduler instance (jobs are added before start).
    """
    if not getattr(settings, "ledger_chain_enabled", False):
        return

    from src.core.constants import (
        LEDGER_NOTARY_INITIAL_DELAY_SECONDS,
        SCHEDULER_JOB_LEDGER_NOTARY,
    )

    interval = settings.ledger_chain_interval_seconds
    scheduler.add_job(
        run_ledger_notary,
        trigger="interval",
        seconds=interval,
        jitter=jitter_seconds_for(seconds=interval),
        # The first pass runs shortly after boot rather than one full interval
        # later: on an instance that has just enabled the flag, every existing
        # register row is pending, and the operator who turned it on is
        # entitled to see the chains open (ADR-178 starvation, same shape).
        next_run_time=datetime.now(UTC) + timedelta(seconds=LEDGER_NOTARY_INITIAL_DELAY_SECONDS),
        id=SCHEDULER_JOB_LEDGER_NOTARY,
        name="Notarise the transparency registers",
        replace_existing=True,
        # A pass that overruns its tick must not have a second one behind it:
        # the loser would spend its whole run losing races on the unique index.
        max_instances=1,
        misfire_grace_time=interval,
    )
    logger.info("ledger_notary_scheduled", interval_seconds=interval)


__all__ = ["register_ledger_jobs", "run_ledger_notary"]
