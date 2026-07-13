"""Telephony background reapers (spec P4.3).

- ``telephony_stale_call_reaper``: sweeps ``dialing``/``in_progress`` calls that
  never received a terminal webhook (process crash / vendor never called back) to
  ``failed`` — so a user is never stuck behind a phantom "in progress" call and
  the one-active-call slot (F12) is freed.
- ``telephony_retention_reaper``: clears ``summary``/``structured_data`` past
  their retention TTL (D-8). The row is kept for audit; only its content is
  purged.

Both are registered flag-guarded in ``startup/schedulers.py`` and run under the
scheduler leader election, so exactly one instance sweeps at a time.
"""

from __future__ import annotations

import structlog

from src.core.config import settings
from src.domains.telephony.repository import TelephonyRepository
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


async def telephony_stale_call_reaper() -> None:
    """Mark in-flight calls with no terminal webhook as failed (crash recovery)."""
    async with get_db_context() as db:
        count = await TelephonyRepository(db).recover_stale(
            settings.telephony_stale_call_timeout_minutes
        )
        await db.commit()
    if count:
        logger.info("telephony_stale_calls_reaped", count=count)


async def telephony_retention_reaper() -> None:
    """Purge call summary/structured_data past their retention TTL (D-8)."""
    async with get_db_context() as db:
        count = await TelephonyRepository(db).purge_expired()
        await db.commit()
    if count:
        logger.info("telephony_calls_purged", count=count)
