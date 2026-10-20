"""Arrival invalidates existing SMS-derived prose without scheduling a model."""

from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.relations.debrief.models import DebriefState, RelationDebrief
from src.domains.sms.schemas import IngestItemReceipt


async def invalidate_sms_debriefs(
    db: AsyncSession, owner: UUID, receipts: list[IngestItemReceipt]
) -> None:
    if not any(item.verdict == "stored" for item in receipts):
        return
    await db.execute(
        update(RelationDebrief)
        .where(
            RelationDebrief.user_id == owner,
            RelationDebrief.state == DebriefState.READY,
            RelationDebrief.sections_used.contains(["sms"]),
        )
        .values(evidence_digest=None, body=None)
    )
