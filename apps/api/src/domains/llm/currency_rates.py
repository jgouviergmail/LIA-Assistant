"""Single implementation of currency exchange-rate replacement.

One invariant governs this table: **exactly one row stays active per currency
pair**. It used to be implemented twice — in the admin route and in the daily
scheduler — and the admin copy deactivated only the first of the active rows,
which is how three active ``EUR->USD`` rows appeared in the development
database. Both callers now share this module, and migration ``6e7f8a9b0c1d``
adds a partial unique index so any regression fails loudly instead of silently
duplicating.

Superseded rows are kept (``is_active = False``): they are the audit trail of
what rate applied when.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.models import CurrencyExchangeRate

logger = structlog.get_logger(__name__)


async def replace_active_rate(
    db: AsyncSession,
    *,
    from_currency: str,
    to_currency: str,
    rate: Decimal,
    effective_from: datetime | None = None,
) -> CurrencyExchangeRate:
    """Make ``rate`` the active rate of a pair, retiring every previous one.

    The deactivation is a bulk ``UPDATE`` (not a load-then-mutate of the first
    match) and is flushed **before** the insert. Both details are load-bearing:
    the bulk statement retires every legacy active row, and the explicit flush
    guarantees the UPDATE reaches the database before the INSERT rather than
    relying on SQLAlchemy's unit-of-work ordering, which the partial unique
    index would otherwise turn into an ``IntegrityError``.

    The caller owns the transaction: this function flushes but never commits.

    Args:
        db: Active database session.
        from_currency: Source currency code (ISO 4217, case-insensitive).
        to_currency: Target currency code (ISO 4217, case-insensitive).
        rate: New rate, as ``1 from_currency = rate to_currency``.
        effective_from: Instant the rate becomes effective; defaults to now (UTC).

    Returns:
        The newly created, active :class:`CurrencyExchangeRate`.
    """
    source = from_currency.upper()
    target = to_currency.upper()

    # Read the outgoing rates before retiring them: it costs one indexed query
    # and it is what makes the log honest — an operator reading
    # "rate replaced" wants to know what it replaced, and a pair that had no
    # active rate must not be reported as a replacement at all.
    previous = list(
        await db.scalars(
            select(CurrencyExchangeRate).where(
                CurrencyExchangeRate.from_currency == source,
                CurrencyExchangeRate.to_currency == target,
                CurrencyExchangeRate.is_active,
            )
        )
    )

    await db.execute(
        update(CurrencyExchangeRate)
        .where(
            CurrencyExchangeRate.from_currency == source,
            CurrencyExchangeRate.to_currency == target,
            CurrencyExchangeRate.is_active,
        )
        .values(is_active=False)
    )
    await db.flush()

    new_rate = CurrencyExchangeRate(
        from_currency=source,
        to_currency=target,
        rate=rate,
        effective_from=effective_from or datetime.now(UTC),
        is_active=True,
    )
    db.add(new_rate)

    logger.info(
        "currency_rate_replaced" if previous else "currency_rate_created",
        from_currency=source,
        to_currency=target,
        rate=float(rate),
        retired_rows=len(previous),
        previous_rate=float(previous[0].rate) if len(previous) == 1 else None,
    )
    return new_rate
