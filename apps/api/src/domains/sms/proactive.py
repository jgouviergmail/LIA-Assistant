"""Idempotent mention bookkeeping, only after a known successful notification."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.ingestion.authority import lock_active_owner
from src.domains.sms.models import SmsMessage
from src.domains.sms.reads import require_read
from src.domains.sms.summary import SmsSignal


async def mark_sms_mentioned(db: AsyncSession, signal: SmsSignal, chosen: list[UUID]) -> None:
    await db.execute(
        select(func.set_config("statement_timeout", str(settings.sms_search_timeout_ms), True))
    )
    await lock_active_owner(db, signal.owner)
    actor = await require_read(db, signal.owner, assistant=True)
    if (actor.extraction_revision or 0) != signal.revision:
        raise AuthorizationError(detail={"error_code": "STALE_SMS_SOURCE"})
    allowed = {item.id for item in signal.messages}
    selected = allowed.intersection(chosen)
    if not selected:
        return
    await db.execute(
        update(SmsMessage)
        .where(
            SmsMessage.user_id == signal.owner,
            SmsMessage.id.in_(selected),
            SmsMessage.proactive_mentioned_at.is_(None),
        )
        .values(proactive_mentioned_at=datetime.now(UTC))
    )
