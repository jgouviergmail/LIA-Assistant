"""Owner-first, freshly confirmed writers; no direct HTTP mutation bypass."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, delete, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.account_export.invalidation import invalidate_account_exports
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.ingestion.authority import lock_active_owner
from src.domains.ingestion.models import IngestionDelivery, IngestionReceipt
from src.domains.relations.debrief.models import RelationDebrief
from src.domains.sms.cursors import SmsCursor
from src.domains.sms.management_schemas import SmsEraseRequest, SmsEraseSelection
from src.domains.sms.models import SmsMessage
from src.domains.sms.preferences import SmsPreferences
from src.domains.sms.read_schemas import SmsQuery
from src.domains.sms.reads import require_read
from src.domains.sms.repository import message_query
from src.domains.users.extraction_consent import invalidate_extractions
from src.domains.users.preference_cas import PreferenceWriteReceipt


class SmsCompletionUnknown(RuntimeError):
    """Never auto-replay a command whose SQL acknowledgement was lost."""


async def _erase_query(
    db: AsyncSession, owner: UUID, request: SmsEraseRequest, as_of: datetime
) -> Select[tuple[SmsMessage]]:
    query = SmsQuery(**request.model_dump(exclude={"all_messages", "message_ids"}))
    statement = await message_query(
        db, owner, query, SmsCursor(owner=owner, filters="erasure", revision=0, as_of=as_of)
    )
    if request.message_ids:
        statement = statement.where(SmsMessage.id.in_(request.message_ids))
    return statement


async def _fingerprint(db: AsyncSession, statement: Select[tuple[SmsMessage]]) -> tuple[int, str]:
    count, digest = 0, hashlib.sha256()
    result = await db.stream(
        statement.with_only_columns(
            SmsMessage.id,
            SmsMessage.body_encrypted,
            SmsMessage.sender_encrypted,
            SmsMessage.origin,
            SmsMessage.received_at,
            SmsMessage.date_kind,
        )
        .order_by(SmsMessage.id)
        .execution_options(yield_per=128)
    )
    async for row in result:
        digest.update(json.dumps([str(value) for value in row], ensure_ascii=False).encode())
        count += 1
    return count, digest.hexdigest()


async def prepare_sms_erasure(
    db: AsyncSession, owner: UUID, request: SmsEraseRequest
) -> SmsEraseSelection:
    selected = SmsEraseRequest.model_validate(request.model_dump())
    await require_read(db, owner)
    as_of = datetime.now(UTC)
    count, digest = await _fingerprint(db, await _erase_query(db, owner, selected, as_of))
    return SmsEraseSelection(request=selected, as_of=as_of, count=count, digest=digest)


async def cancel_sms_deliveries(
    db: AsyncSession, owner: UUID, receipt_ids: Select[tuple[UUID]] | None = None
) -> None:
    statement = update(IngestionDelivery).where(
        IngestionDelivery.user_id == owner,
        IngestionDelivery.state.in_(("pending", "sending", "unknown", "failed")),
    )
    if receipt_ids is not None:
        statement = statement.where(IngestionDelivery.receipt_id.in_(receipt_ids))
    await db.execute(
        statement.values(
            state="cancelled", fence=IngestionDelivery.fence + 1, lease_owner=None, lease_until=None
        )
    )


async def erase_sms(
    db: AsyncSession,
    owner: UUID,
    expected: SmsEraseSelection,
    receipt: PreferenceWriteReceipt,
    check: Callable[[], Awaitable[None]],
) -> None:
    actor = await lock_active_owner(db, owner)
    await require_capability_fresh(db, PlatformCapability.SMS)
    await check()
    statement = await _erase_query(db, owner, expected.request, expected.as_of)
    count, digest = await _fingerprint(db, statement)
    if (count, digest) != (expected.count, expected.digest):
        raise ResourceConflictError("sms_erasure", detail={"error_code": "STALE_STATE"})
    if count == 0:
        receipt.committed, receipt.no_op, receipt.values = True, True, {"sms_to_delete": None}
        return
    receipt_ids = statement.with_only_columns(SmsMessage.receipt_id)
    await cancel_sms_deliveries(db, owner, receipt_ids)
    await db.execute(
        update(IngestionReceipt)
        .where(IngestionReceipt.user_id == owner, IngestionReceipt.id.in_(receipt_ids))
        .values(verdict="deleted")
    )
    identifiers = statement.with_only_columns(SmsMessage.id)
    deleted = await db.execute(
        delete(SmsMessage).where(SmsMessage.user_id == owner, SmsMessage.id.in_(identifiers))
    )
    affected = getattr(deleted, "rowcount", None)
    if not isinstance(affected, int) or affected != count:
        raise ValueError("sms_erasure_count_not_observed")
    remaining, _ = await _fingerprint(db, statement)
    if remaining:
        raise ValueError("sms_erasure_not_observed")
    await db.execute(delete(RelationDebrief).where(RelationDebrief.user_id == owner))
    await invalidate_account_exports(db, owner)
    invalidate_extractions(actor)
    await db.flush()
    await check()
    await _commit(db)
    receipt.committed = True
    receipt.values = {"sms_to_delete": None}


async def update_sms_preferences(
    db: AsyncSession,
    owner: UUID,
    expected: SmsPreferences,
    selected: SmsPreferences,
    receipt: PreferenceWriteReceipt,
    check: Callable[[], Awaitable[None]],
) -> None:
    actor = await lock_active_owner(db, owner)
    await require_capability_fresh(db, PlatformCapability.SMS)
    await check()
    if SmsPreferences.from_stored(actor.sms_preferences) != expected:
        raise ResourceConflictError("sms_preferences", detail={"error_code": "STALE_STATE"})
    changed = SmsPreferences.model_validate(selected.model_dump())
    actor.sms_preferences = changed.model_dump()
    if not changed.push_enabled or not changed.ingestion_enabled:
        await cancel_sms_deliveries(db, owner)
    if changed.assistant_enabled != expected.assistant_enabled:
        invalidate_extractions(actor)
        await db.execute(delete(RelationDebrief).where(RelationDebrief.user_id == owner))
    await db.flush()
    await check()
    await _commit(db)
    receipt.committed = True
    receipt.no_op = changed == expected
    receipt.values = {"sms_preferences": changed.model_dump()}


async def _commit(db: AsyncSession) -> None:
    try:
        await db.commit()
    except SQLAlchemyError, OSError, TimeoutError:
        raise SmsCompletionUnknown() from None
