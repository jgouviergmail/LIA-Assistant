"""A pre-authenticated token is checked again under the owner fence before ingestion."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_bearer_auth_failed
from src.domains.health_metrics.management_lock import lock_health_writer
from src.domains.health_metrics.models import HealthMetricToken


async def require_ingestion_authority(db: AsyncSession, token: HealthMetricToken) -> None:
    await lock_health_writer(db, token.user_id)
    active = await db.scalar(
        select(HealthMetricToken.id).where(
            HealthMetricToken.id == token.id,
            HealthMetricToken.user_id == token.user_id,
            HealthMetricToken.token_hash == token.token_hash,
            HealthMetricToken.revoked_at.is_(None),
        )
    )
    if active is None:
        raise_bearer_auth_failed("Health ingestion token is no longer active")
