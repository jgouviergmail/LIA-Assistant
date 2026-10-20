"""One owner-first fence for token/source changes and resource ingestion.

Writers/management acquire the active owner exclusively, then inspect source and
credential. They perform no provider or push I/O while holding this transaction lock.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, raise_bearer_auth_failed
from src.domains.ingestion.models import IngestionSource, IngestionToken
from src.domains.ingestion.principal import IngestionPrincipal
from src.domains.ingestion.registry import IngestionResource, policy_for
from src.domains.users.models import User


async def lock_active_owner(db: AsyncSession, user_id: UUID) -> User:
    with db.no_autoflush:
        owner = await db.scalar(
            select(User)
            .where(User.id == user_id, User.is_active.is_(True), User.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    if owner is None:
        raise_bearer_auth_failed("Inactive ingestion owner")
    return owner


async def require_authority(
    db: AsyncSession, principal: IngestionPrincipal, resource: IngestionResource
) -> tuple[User, IngestionSource, IngestionToken]:
    policy = policy_for(resource)
    if policy.write_scope not in principal.scopes or principal.source_id is None:
        raise AuthorizationError(detail={"error_code": "INGESTION_SCOPE_DENIED"})
    owner = await lock_active_owner(db, principal.user_id)
    source = await db.scalar(
        select(IngestionSource)
        .where(
            IngestionSource.id == principal.source_id,
            IngestionSource.user_id == principal.user_id,
            IngestionSource.resource == resource.value,
            IngestionSource.revoked_at.is_(None),
        )
        .execution_options(populate_existing=True)
    )
    token = await db.scalar(
        select(IngestionToken)
        .where(
            IngestionToken.id == principal.token_id,
            IngestionToken.user_id == principal.user_id,
            IngestionToken.source_id == principal.source_id,
            IngestionToken.revoked_at.is_(None),
        )
        .execution_options(populate_existing=True)
    )
    if source is None or token is None or policy.write_scope not in token.scopes:
        raise_bearer_auth_failed("Ingestion credential is no longer active")
    return owner, source, token
