"""Source issuance is acknowledged before its ephemeral secret may leave the caller."""

from collections.abc import Awaitable, Callable
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.health_metrics.management_lock import lock_health_manager
from src.domains.health_metrics.models import HealthMetricToken
from src.domains.health_metrics.schemas import HealthMetricTokenCreateResponse
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.health_metrics.token_commands import read_owned_health_token
from src.domains.users.preference_cas import PreferenceWriteReceipt


class HealthTokenCreationCompletionUnknown(RuntimeError):
    """Source commit acknowledgement was lost; the secret is discarded, never replayed."""


async def create_managed_health_token(
    db: AsyncSession,
    actor_id: UUID,
    token_id: UUID,
    label: str | None,
    receipt: PreferenceWriteReceipt,
    check: Callable[[], Awaitable[None]],
) -> HealthMetricTokenCreateResponse:
    await lock_health_manager(db, actor_id)
    await check()
    created = await HealthMetricsService(db).create_token(actor_id, label=label, token_id=token_id)
    await db.flush()
    public = await read_owned_health_token(db, actor_id, token_id)
    stored_hash = await db.scalar(
        select(HealthMetricToken.token_hash).where(
            HealthMetricToken.id == token_id, HealthMetricToken.user_id == actor_id
        )
    )
    if (
        (created.id, created.label, created.token_prefix, created.created_at)
        != (public.token.id, public.token.label, public.token.token_prefix, public.token.created_at)
        or created.label != label
        or public.token.revoked_at is not None
        or stored_hash != sha256(created.token.encode()).hexdigest()
    ):
        raise ValueError("Source token issuance was not observed")
    await check()
    try:
        await db.commit()
    except SQLAlchemyError as error:
        raise HealthTokenCreationCompletionUnknown() from error
    receipt.committed, receipt.values = True, {"health_token_created": public.public_scope()}
    return created
