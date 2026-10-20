"""Exact sender policy under the same owner fence as ingestion and erasure."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.core.security.utils import encrypt_data
from src.domains.ingestion.authority import lock_active_owner
from src.domains.ingestion.key_material import initialize_owner_key, key_for_owner
from src.domains.relations.debrief.models import RelationDebrief
from src.domains.sms.management_commands import SmsCompletionUnknown, cancel_sms_deliveries
from src.domains.sms.models import SmsMessage, SmsSenderBlock
from src.domains.sms.reads import require_read
from src.domains.sms.search import blind_digest
from src.domains.sms.sender_policy import normalize_sender
from src.domains.users.extraction_consent import invalidate_extractions
from src.domains.users.preference_cas import PreferenceWriteReceipt


class SmsSenderBlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sender: StrictStr = Field(min_length=1, max_length=settings.sms_max_sender_chars)
    blocked: StrictBool

    @field_validator("sender")
    @classmethod
    def meaningful_sender(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("invalid_sender")
        value.encode("utf-8")
        return value


class SmsSenderBlockSelection(SmsSenderBlockRequest):
    previously_blocked: StrictBool


async def prepare_sender_block(
    db: AsyncSession, owner: UUID, sender: str, *, blocked: bool
) -> SmsSenderBlockSelection:
    request = SmsSenderBlockRequest(sender=sender, blocked=blocked)
    actor = await require_read(db, owner)
    current = False
    if actor.ingestion_key_encrypted is not None:
        digest = blind_digest(owner, "sender", normalize_sender(sender), key=key_for_owner(actor))
        current = bool(
            await db.scalar(
                select(SmsSenderBlock.id).where(
                    SmsSenderBlock.user_id == owner, SmsSenderBlock.sender_hash == digest
                )
            )
        )
    return SmsSenderBlockSelection(**request.model_dump(), previously_blocked=current)


async def update_sender_block(
    db: AsyncSession,
    owner: UUID,
    expected: SmsSenderBlockSelection,
    receipt: PreferenceWriteReceipt,
    check: Callable[[], Awaitable[None]],
) -> None:
    selected = SmsSenderBlockSelection.model_validate(expected.model_dump())
    actor = await lock_active_owner(db, owner)
    await require_read(db, owner)
    await check()
    key = await initialize_owner_key(db, actor)
    digest = blind_digest(owner, "sender", normalize_sender(selected.sender), key=key)
    current = await db.scalar(
        select(SmsSenderBlock).where(
            SmsSenderBlock.user_id == owner, SmsSenderBlock.sender_hash == digest
        )
    )
    if (current is not None) != selected.previously_blocked:
        raise ResourceConflictError("sms_sender_block", detail={"error_code": "STALE_STATE"})
    if selected.blocked and current is None:
        count = int(
            await db.scalar(
                select(func.count())
                .select_from(SmsSenderBlock)
                .where(SmsSenderBlock.user_id == owner)
            )
            or 0
        )
        if count >= settings.sms_max_blocked_senders:
            raise ResourceConflictError(
                "sms_sender_block", detail={"error_code": "SMS_BLOCK_LIMIT"}
            )
        db.add(
            SmsSenderBlock(
                user_id=owner, sender_hash=digest, sender_encrypted=encrypt_data(selected.sender)
            )
        )
    if not selected.blocked and current is not None:
        await db.delete(current)
    if selected.blocked:
        receipts = select(SmsMessage.receipt_id).where(
            SmsMessage.user_id == owner, SmsMessage.sender_hash == digest
        )
        await cancel_sms_deliveries(db, owner, receipts)
    if selected.blocked != selected.previously_blocked:
        invalidate_extractions(actor)
        await db.execute(delete(RelationDebrief).where(RelationDebrief.user_id == owner))
    await db.flush()
    await check()
    try:
        await db.commit()
    except SQLAlchemyError, OSError, TimeoutError:
        raise SmsCompletionUnknown() from None
    receipt.committed = True
    receipt.no_op = selected.blocked == selected.previously_blocked
    receipt.values = {
        "sms_sender_block": selected.model_dump(mode="json", exclude={"previously_blocked"})
    }
