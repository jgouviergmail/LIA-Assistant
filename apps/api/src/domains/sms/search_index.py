"""Build beside the active index, catch writes under the owner fence, swap once.

The staging table is transaction-local and disappears on commit or rollback.
Readers keep the last committed generation through PostgreSQL MVCC; no index
or content is deleted until the replacement has been validated. Dedicated session.
"""

import hmac
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    LargeBinary,
    Uuid,
    column,
    delete,
    func,
    insert,
    literal,
    select,
    table,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.security.utils import decrypt_data
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.ingestion.authority import lock_active_owner
from src.domains.ingestion.key_material import key_for_owner
from src.domains.sms.constants import SMS_SEARCH_INDEX_VERSION
from src.domains.sms.models import SmsMessage, SmsSearchTerm
from src.domains.sms.search import blind_terms
from src.domains.users.models import User

_STAGE = table(
    "sms_index_rebuild",
    column("message_id", Uuid()),
    column("hashes", ARRAY(LargeBinary(32))),
    column("complete", Boolean()),
    column("logical_bytes", BigInteger()),
)


async def stage_messages(db: AsyncSession, owner: UUID, key: bytes) -> int:
    """Read only rows missing from this transaction's replacement projection."""
    staged = select(_STAGE.c.message_id).where(_STAGE.c.message_id == SmsMessage.id).exists()
    statement = (
        select(SmsMessage.id, SmsMessage.body_encrypted, SmsMessage.sender_encrypted)
        .where(SmsMessage.user_id == owner, ~staged)
        .order_by(SmsMessage.id)
        .execution_options(yield_per=64)
    )
    count = 0
    result = await db.stream(statement)
    try:
        async for partition in result.partitions(64):
            rows = []
            for identifier, cipher, sender_cipher in partition:
                body, sender = decrypt_data(cipher), decrypt_data(sender_cipher)
                terms = blind_terms(owner, body, key=key)
                hashes = [bytes.fromhex(term) for term in terms[: settings.sms_max_index_terms]]
                rows.append(
                    {
                        "message_id": identifier,
                        "hashes": hashes,
                        "complete": len(terms) <= settings.sms_max_index_terms,
                        "logical_bytes": len(body.encode())
                        + len(sender.encode())
                        + 32 * len(hashes),
                    }
                )
            if rows:
                await db.execute(insert(_STAGE), rows)
                count += len(rows)
    finally:
        await result.close()
    return count


async def rebuild_sms_index(db: AsyncSession, owner: UUID) -> int:
    if db.new or db.dirty or db.deleted:
        raise ValueError("index_rebuild_requires_clean_dedicated_session")
    try:
        actor = await db.scalar(
            select(User)
            .where(User.id == owner, User.is_active.is_(True), User.deleted_at.is_(None))
            .execution_options(populate_existing=True)
        )
        if actor is None:
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
        await require_capability_fresh(db, PlatformCapability.SMS)
        key = key_for_owner(actor)
        await db.execute(
            text(
                "CREATE TEMP TABLE sms_index_rebuild (message_id UUID PRIMARY KEY, hashes BYTEA[] NOT NULL, complete BOOLEAN NOT NULL, logical_bytes BIGINT NOT NULL) ON COMMIT DROP"
            )
        )
        await stage_messages(db, owner, key)
        actor = await lock_active_owner(db, owner)
        await require_capability_fresh(db, PlatformCapability.SMS)
        if not hmac.compare_digest(key, key_for_owner(actor)):
            raise ResourceConflictError("sms_index", detail={"error_code": "STALE_STATE"})
        await stage_messages(db, owner, key)
        count = await _swap(db, owner)
        await db.commit()
        return count
    except BaseException:
        await db.rollback()
        raise


async def _swap(db: AsyncSession, owner: UUID) -> int:
    current = _STAGE.join(SmsMessage, SmsMessage.id == _STAGE.c.message_id)
    count = int(
        await db.scalar(
            select(func.count()).select_from(current).where(SmsMessage.user_id == owner)
        )
        or 0
    )
    expected = int(
        await db.scalar(
            select(func.count()).select_from(SmsMessage).where(SmsMessage.user_id == owner)
        )
        or 0
    )
    size = int(
        await db.scalar(
            select(func.sum(_STAGE.c.logical_bytes))
            .select_from(current)
            .where(SmsMessage.user_id == owner)
        )
        or 0
    )
    if count != expected or size > settings.sms_archive_max_logical_bytes:
        raise ResourceConflictError("sms_index", detail={"error_code": "INDEX_REBUILD_INCOMPLETE"})
    await db.execute(delete(SmsSearchTerm).where(SmsSearchTerm.user_id == owner))
    await db.execute(
        insert(SmsSearchTerm.__table__).from_select(
            [
                "id",
                "user_id",
                "message_id",
                "term_hashes",
                "index_version",
                "created_at",
                "updated_at",
            ],
            select(
                func.gen_random_uuid(),
                literal(owner),
                _STAGE.c.message_id,
                _STAGE.c.hashes,
                literal(SMS_SEARCH_INDEX_VERSION),
                func.now(),
                func.now(),
            )
            .select_from(current)
            .where(SmsMessage.user_id == owner),
        )
    )
    await db.execute(
        update(SmsMessage)
        .where(SmsMessage.user_id == owner, SmsMessage.id == _STAGE.c.message_id)
        .values(search_complete=_STAGE.c.complete, logical_bytes=_STAGE.c.logical_bytes)
    )
    return count
