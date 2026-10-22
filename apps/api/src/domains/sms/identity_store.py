"""Short SQL transactions; no contact provider is opened by a registry read."""

import hashlib
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.connectors.models import Connector, ConnectorStatus
from src.domains.connectors.provider_authority import resolve_active_connector_fresh
from src.domains.connectors.service import ConnectorService
from src.domains.ingestion.authority import lock_active_owner
from src.domains.ingestion.key_material import key_for_owner
from src.domains.sms.identity import SenderIdentity
from src.domains.sms.identity_models import SmsIdentityState, SmsSenderIdentity
from src.domains.sms.reads import require_read
from src.domains.sms.search import blind_digest
from src.domains.sms.sender_policy import normalize_sender
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

_IDENTITY = TypeAdapter(SenderIdentity)
_RETRY_DELAY = timedelta(minutes=5)
logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ResolutionScope:
    """What a sender resolution depends on: owner, generation, contact source, revision."""

    owner: UUID
    generation: UUID
    authority: str
    revision: int
    key: bytes = field(repr=False)

    def digest(self, sender: str) -> str:
        """Return the blind, keyed digest of a normalised sender for this owner.

        Args:
            sender: The sender as received.

        Returns:
            The digest under which its resolution is stored.
        """
        return blind_digest(self.owner, "sender", normalize_sender(sender), key=self.key)


async def _authority(db: AsyncSession, owner: UUID) -> str:
    kind = await resolve_active_connector_fresh(owner, "contacts", ConnectorService(db))
    if kind is None:
        return "none"
    connector = await db.scalar(
        select(Connector)
        .where(
            Connector.user_id == owner,
            Connector.connector_type == kind,
            Connector.status == ConnectorStatus.ACTIVE,
        )
        .order_by(Connector.updated_at.desc(), Connector.id.desc())
        .limit(1)
    )
    if connector is None:
        return "none"
    # Grant identity survives token refresh but changes on account replacement.
    # Apple/legacy credentials have no grant: conservatively invalidate on change.
    account = (
        str(connector.oauth_grant_id)
        if connector.oauth_grant_id
        else connector.credentials_encrypted
    )
    return hashlib.sha256(f"{connector.id}:{account}".encode()).hexdigest()


async def _scope(
    db: AsyncSession, owner: UUID, revision: int, *, assistant: bool
) -> ResolutionScope:
    actor = await require_read(db, owner, assistant=assistant)
    if (actor.extraction_revision or 0) != revision:
        raise ResourceConflictError("sms", detail={"error_code": "STALE_STATE"})
    generation = await db.scalar(
        select(SmsIdentityState.generation).where(SmsIdentityState.user_id == owner)
    )
    if generation is None:
        await db.execute(
            insert(SmsIdentityState)
            .values(user_id=owner, generation=uuid4())
            .on_conflict_do_nothing(index_elements=[SmsIdentityState.user_id])
        )
        generation = await db.scalar(
            select(SmsIdentityState.generation).where(SmsIdentityState.user_id == owner)
        )
        if generation is None:
            raise ResourceConflictError("sms", detail={"error_code": "STALE_STATE"})
    return ResolutionScope(
        owner, generation, await _authority(db, owner), revision, key_for_owner(actor)
    )


async def read_resolutions(
    owner: UUID, senders: tuple[str, ...], revision: int, assistant: bool
) -> tuple[ResolutionScope, dict[str, SenderIdentity]]:
    """Read only names belonging to the current account, generation and consent."""
    async with get_db_context() as db:
        scope = await _scope(db, owner, revision, assistant=assistant)
        by_hash = {scope.digest(sender) for sender in senders}
        rows = await db.scalars(
            select(SmsSenderIdentity).where(
                SmsSenderIdentity.user_id == owner,
                SmsSenderIdentity.sender_hash.in_(by_hash),
                SmsSenderIdentity.generation == scope.generation,
                SmsSenderIdentity.authority == scope.authority,
                or_(
                    SmsSenderIdentity.retry_at.is_(None),
                    SmsSenderIdentity.retry_at > datetime.now(UTC),
                ),
            )
        )
        stored = {}
        for row in rows:
            try:
                stored[row.sender_hash] = _IDENTITY.validate_json(
                    decrypt_data(row.identity_encrypted)
                )
            except ValueError:
                logger.warning("sms_identity_snapshot_unreadable")
                stored[row.sender_hash] = SenderIdentity("", "raw", "unavailable")
        identities = {}
        for sender in senders:
            identity = stored.get(scope.digest(sender))
            if identity is not None:
                identities[sender] = (
                    replace(identity, display_name=sender) if identity.source == "raw" else identity
                )
        await db.commit()
        return scope, identities


async def validate_resolutions(
    db: AsyncSession, scope: ResolutionScope, *, assistant: bool
) -> None:
    """Recheck privacy and refresh fences while the caller holds its publication lock."""
    if await _scope(db, scope.owner, scope.revision, assistant=assistant) != scope:
        raise ResourceConflictError("sms", detail={"error_code": "STALE_STATE"})


async def publish_resolutions(
    scope: ResolutionScope, identities: dict[str, SenderIdentity], *, assistant: bool
) -> None:
    """Persist encrypted contact outcomes after rechecking their original scope."""
    async with get_db_context() as db:
        await validate_resolutions(db, scope, assistant=assistant)
        values = {
            scope.digest(sender): {
                "user_id": scope.owner,
                "sender_hash": scope.digest(sender),
                "generation": scope.generation,
                "authority": scope.authority,
                "identity_encrypted": encrypt_data(_IDENTITY.dump_json(identity).decode()),
                "retry_at": (
                    datetime.now(UTC) + _RETRY_DELAY if identity.state == "unavailable" else None
                ),
            }
            for sender, identity in identities.items()
        }
        pending = list(values.values())
        # Bound PostgreSQL bind parameters even for a full Relations sender index.
        for offset in range(0, len(pending), 128):
            statement = insert(SmsSenderIdentity).values(pending[offset : offset + 128])
            await db.execute(
                statement.on_conflict_do_update(
                    index_elements=[SmsSenderIdentity.user_id, SmsSenderIdentity.sender_hash],
                    set_={
                        name: getattr(statement.excluded, name)
                        for name in ("generation", "authority", "identity_encrypted", "retry_at")
                    }
                    | {"updated_at": datetime.now(UTC)},
                )
            )
        await db.commit()


async def reset_resolutions(db: AsyncSession, owner: UUID) -> None:
    """Fence in-flight writers and forget the derived names, never the SMS."""
    await lock_active_owner(db, owner)
    await require_read(db, owner)
    statement = insert(SmsIdentityState).values(user_id=owner, generation=uuid4())
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[SmsIdentityState.user_id],
            set_={"generation": statement.excluded.generation, "updated_at": datetime.now(UTC)},
        )
    )
    await db.execute(delete(SmsSenderIdentity).where(SmsSenderIdentity.user_id == owner))
    await db.commit()
