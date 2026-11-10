"""Shared SQL and decrypted-text bounds for the lexical and display readers."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Never

from sqlalchemy import Select, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.domains.sms.models import SmsMessage


def too_broad() -> Never:
    """A cut is a refusal to claim an exact count, never a partial result."""
    raise ResourceConflictError("sms_search", detail={"error_code": "QUERY_TOO_BROAD"})


@asynccontextmanager
async def search_sql_budget(db: AsyncSession) -> AsyncIterator[None]:
    """Bound expensive archive statements and restore the owning transaction's setting."""
    try:
        previous = await db.scalar(select(func.current_setting("statement_timeout"))) or "0"
        await db.execute(
            select(func.set_config("statement_timeout", str(settings.sms_search_timeout_ms), True))
        )
        try:
            yield
        except asyncio.CancelledError, DBAPIError:
            # The connection may be invalid; never restore a setting before rollback.
            raise
        except BaseException:
            await _restore_sql_budget(db, previous)
            raise
        else:
            await _restore_sql_budget(db, previous)
    except asyncio.CancelledError:
        # asyncpg invalidates a cancelled connection. Restoring SET LOCAL on it
        # would mask cancellation with PendingRollbackError.
        await db.rollback()
        raise
    except DBAPIError as error:
        await db.rollback()
        if getattr(error.orig, "sqlstate", None) == "57014":
            too_broad()
        raise


async def _restore_sql_budget(db: AsyncSession, previous: str) -> None:
    """Restore only a live caller transaction, inside the same cancellation boundary."""
    if db.in_transaction():
        await db.execute(select(func.set_config("statement_timeout", previous, True)))


async def bounded_candidates(
    db: AsyncSession, statement: Select[tuple[SmsMessage]]
) -> list[SmsMessage]:
    """Read at most one more than the verification budget, refusing a larger set."""
    async with search_sql_budget(db):
        rows = list(
            (
                await db.scalars(
                    statement.order_by(SmsMessage.received_at.desc(), SmsMessage.id.desc()).limit(
                        settings.sms_search_max_candidates + 1
                    )
                )
            ).all()
        )
    if len(rows) > settings.sms_search_max_candidates:
        too_broad()
    return rows


class VerificationBudget:
    """One wall-clock and decoded-character allowance for a complete verification pass."""

    def __init__(self) -> None:
        self.deadline = perf_counter() + settings.sms_search_timeout_ms / 1000
        self.decoded = 0

    def charge(self, text: str) -> None:
        """Count content before admitting it; raise rather than silently truncate."""
        self.decoded += len(text)
        if self.decoded > settings.sms_search_max_verified_chars or perf_counter() > self.deadline:
            too_broad()
