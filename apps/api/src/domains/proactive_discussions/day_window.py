"""Civil-day quota bounds reuse the shared half-open date contract."""

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.date_contract import period_bounds
from src.domains.proactive_discussions.models import DiscussionOpeningRecord


def local_day_utc_bounds(now: datetime, timezone: str) -> tuple[datetime, datetime]:
    """Return the person's current civil day as a half-open UTC interval.

    Args:
        now: The instant, timezone-aware.
        timezone: The person's IANA timezone.

    Returns:
        The UTC instants at which the local day starts (included) and ends
        (excluded).

    Raises:
        RuntimeError: The shared date contract did not resolve explicit bounds.
    """
    zone = ZoneInfo(timezone)
    day = now.astimezone(zone).date().isoformat()
    start, end = period_bounds(day, day, zone, now=now, default_days=None)
    if start is None or end is None:
        raise RuntimeError("explicit day bounds did not resolve")
    return start.astimezone(UTC), end.astimezone(UTC)


async def count_today(db: AsyncSession, owner: UUID, *, now: datetime, timezone: str) -> int:
    """Count the openings LIA made today, on the person's own clock.

    Args:
        db: The session to read with.
        owner: The account.
        now: The current instant.
        timezone: The person's IANA timezone.

    Returns:
        The number of openings created during the local day containing ``now``.
    """
    start, end = local_day_utc_bounds(now, timezone)
    return int(
        await db.scalar(
            select(func.count())
            .select_from(DiscussionOpeningRecord)
            .where(
                DiscussionOpeningRecord.user_id == owner,
                DiscussionOpeningRecord.created_at >= start,
                DiscussionOpeningRecord.created_at < end,
            )
        )
        or 0
    )
