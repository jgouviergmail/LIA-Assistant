"""Owned, fenced credentials; callers provide exact approved command identity.

No HTTP mutation bypass is exposed. The application continuation owns the browser
session, expiry and one-use secret delivery; these functions own the SQL effect.
"""

import json
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, ResourceNotFoundError, raise_invalid_input
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.ingestion.authority import lock_active_owner
from src.domains.ingestion.key_material import initialize_owner_key
from src.domains.ingestion.models import (
    IngestionDelivery,
    IngestionReceipt,
    IngestionSource,
    IngestionToken,
)
from src.domains.ingestion.registry import IngestionResource, policy_for
from src.domains.ingestion.schemas import (
    IngestionTokenRow,
    IngestionTokenSecret,
    IngestionTokenSelection,
)
from src.domains.ingestion.token_auth import hash_token
from src.domains.users.preference_cas import PreferenceWriteReceipt


class IngestionTokenCompletionUnknown(RuntimeError):
    """The secret must be discarded if a source commit is not acknowledged."""


async def read_owned_token(
    db: AsyncSession, actor_id: UUID, token_id: UUID
) -> IngestionTokenSelection:
    result = (
        await db.execute(
            select(IngestionToken, IngestionSource)
            .join(IngestionSource, IngestionSource.id == IngestionToken.source_id)
            .where(
                IngestionToken.id == token_id,
                IngestionToken.user_id == actor_id,
                IngestionSource.user_id == actor_id,
            )
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if result is None:
        raise ResourceNotFoundError("ingestion_token", token_id)
    token, source = result
    try:
        label = decrypt_data(source.label_encrypted)
    except ValueError:
        label = None
    public = IngestionTokenRow(
        id=token.id,
        source_id=source.id,
        resource=IngestionResource(source.resource),
        label=label,
        token_prefix=token.token_prefix,
        scopes=tuple(token.scopes),
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        revoked_at=token.revoked_at,
    )
    identity = {
        **public.model_dump(mode="json", exclude={"last_used_at", "revoked_at"}),
        "token_hash": token.token_hash,
        "source_label": source.label_encrypted,
        "source_revoked_at": source.revoked_at.isoformat() if source.revoked_at else None,
    }
    return IngestionTokenSelection(
        token=public, digest=hash_token(json.dumps(identity, sort_keys=True))
    )


async def create_managed_token(
    db: AsyncSession,
    actor_id: UUID,
    token_id: UUID,
    label: str,
    source_id: UUID | None,
    receipt: PreferenceWriteReceipt,
    check: Callable[[], Awaitable[None]],
    *,
    resource: IngestionResource = IngestionResource.SMS,
) -> IngestionTokenSecret:
    policy = policy_for(resource)
    if not policy.managed_tokens:
        raise_invalid_input("Resource uses its legacy credential adapter")
    if not label.strip() or len(label) > 128 or "\x00" in label:
        raise_invalid_input("Invalid ingestion source label")
    owner = await lock_active_owner(db, actor_id)
    await require_capability_fresh(db, PlatformCapability(resource.value))
    await check()
    await initialize_owner_key(db, owner)
    if await db.get(IngestionToken, token_id) is not None:
        raise IngestionTokenCompletionUnknown(
            "Token command already observed; secret cannot be replayed"
        )
    active = (
        await db.scalar(
            select(func.count())
            .select_from(IngestionToken)
            .where(IngestionToken.user_id == actor_id, IngestionToken.revoked_at.is_(None))
        )
        or 0
    )
    if active >= settings.ingestion_max_active_tokens_per_user:
        raise ResourceConflictError(
            "ingestion_token", detail={"error_code": "INGESTION_TOKEN_LIMIT"}
        )
    source = await _source(db, actor_id, source_id, resource, label)
    raw = policy.token_prefix + secrets.token_urlsafe(32)
    db.add(
        IngestionToken(
            id=token_id,
            user_id=actor_id,
            source_id=source.id,
            token_hash=hash_token(raw),
            token_prefix=raw[:11],
            scopes=[policy.write_scope],
        )
    )
    await db.flush()
    observed = await read_owned_token(db, actor_id, token_id)
    stored = await db.scalar(select(IngestionToken.token_hash).where(IngestionToken.id == token_id))
    if stored != hash_token(raw) or observed.token.revoked_at is not None:
        raise ValueError("Ingestion token issuance was not observed")
    await check()
    try:
        await db.commit()
    except SQLAlchemyError, OSError, TimeoutError:
        raise IngestionTokenCompletionUnknown() from None
    receipt.committed, receipt.values = True, {"ingestion_token_created": observed.public_scope()}
    return IngestionTokenSecret(**observed.token.model_dump(), token=raw)


async def _source(
    db: AsyncSession,
    actor_id: UUID,
    source_id: UUID | None,
    resource: IngestionResource,
    label: str,
) -> IngestionSource:
    if source_id is not None:
        source = await db.scalar(
            select(IngestionSource).where(
                IngestionSource.id == source_id,
                IngestionSource.user_id == actor_id,
                IngestionSource.resource == resource.value,
                IngestionSource.revoked_at.is_(None),
            )
        )
        if source is None:
            raise ResourceNotFoundError("ingestion_source", source_id)
        if decrypt_data(source.label_encrypted) != label:
            raise ResourceConflictError("ingestion_source", detail={"error_code": "STALE_STATE"})
        return source
    source = IngestionSource(
        id=uuid4(), user_id=actor_id, resource=resource.value, label_encrypted=encrypt_data(label)
    )
    db.add(source)
    await db.flush()
    return source


async def revoke_managed_token(
    db: AsyncSession,
    actor_id: UUID,
    expected: IngestionTokenSelection,
    receipt: PreferenceWriteReceipt,
    check: Callable[[], Awaitable[None]],
) -> None:
    await lock_active_owner(db, actor_id)
    await check()
    current = await read_owned_token(db, actor_id, expected.token.id)
    if current.digest != expected.digest or current.token.revoked_at != expected.token.revoked_at:
        raise ResourceConflictError("ingestion_token", detail={"error_code": "STALE_STATE"})
    if current.token.revoked_at is not None:
        receipt.committed, receipt.no_op, receipt.values = (
            True,
            True,
            {"ingestion_token_to_revoke": current.public_scope()},
        )
        return
    await db.execute(
        update(IngestionToken)
        .where(IngestionToken.id == expected.token.id, IngestionToken.user_id == actor_id)
        .values(revoked_at=datetime.now(UTC))
    )
    # A last credential withdrawal closes queued publications for that source;
    # rotation with another live credential keeps its stable receipt namespace.
    active = await db.scalar(
        select(func.count())
        .select_from(IngestionToken)
        .where(
            IngestionToken.source_id == current.token.source_id,
            IngestionToken.revoked_at.is_(None),
            IngestionToken.user_id == actor_id,
        )
    )
    if not active:
        receipts = select(IngestionReceipt.id).where(
            IngestionReceipt.source_id == current.token.source_id,
            IngestionReceipt.user_id == actor_id,
        )
        await db.execute(
            update(IngestionDelivery)
            .where(
                IngestionDelivery.receipt_id.in_(receipts),
                IngestionDelivery.user_id == actor_id,
                IngestionDelivery.state.in_(("pending", "sending", "unknown")),
            )
            .values(
                state="cancelled",
                fence=IngestionDelivery.fence + 1,
                lease_owner=None,
                lease_until=None,
            )
        )
    observed = await read_owned_token(db, actor_id, current.token.id)
    if observed.token.revoked_at is None or observed.digest != current.digest:
        raise ValueError("Ingestion token revocation was not observed")
    await check()
    try:
        await db.commit()
    except SQLAlchemyError, OSError, TimeoutError:
        raise IngestionTokenCompletionUnknown() from None
    receipt.committed, receipt.values = True, {"ingestion_token_to_revoke": observed.public_scope()}
