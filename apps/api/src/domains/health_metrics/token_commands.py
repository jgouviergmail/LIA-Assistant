"""Owned source token identity stays private; incidental successful-use dates do not retarget it."""

import json
from collections.abc import Awaitable, Callable
from hashlib import sha256
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.health_metrics.management_lock import lock_health_manager
from src.domains.health_metrics.models import HealthMetricToken
from src.domains.health_metrics.schemas import HealthMetricTokenRow
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.users.preference_cas import PreferenceWriteReceipt


class HealthTokenSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    token: HealthMetricTokenRow
    digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self) -> dict[str, JsonValue]:
        return self.token.model_dump(mode="json")


async def read_owned_health_token(
    db: AsyncSession, actor_id: UUID, token_id: UUID
) -> HealthTokenSelection:
    row = (
        (
            await db.execute(
                select(*HealthMetricToken.__table__.columns).where(
                    HealthMetricToken.id == token_id, HealthMetricToken.user_id == actor_id
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ResourceNotFoundError("health_token", token_id)
    # Exposure is incidental; revocation is compared separately and may change at execution.
    identity = {
        name: value
        for name, value in row.items()
        if name not in {"last_used_at", "updated_at", "revoked_at"}
    }
    digest = sha256(
        json.dumps(identity, sort_keys=True, default=str, allow_nan=False).encode()
    ).hexdigest()
    return HealthTokenSelection(token=HealthMetricTokenRow.model_validate(dict(row)), digest=digest)


class HealthTokenRevocationCompletionUnknown(RuntimeError):
    """A missing SQL acknowledgement cannot establish revocation."""


async def revoke_managed_health_token(
    db: AsyncSession,
    actor_id: UUID,
    expected: HealthTokenSelection,
    receipt: PreferenceWriteReceipt,
    check: Callable[[], Awaitable[None]],
) -> None:
    await lock_health_manager(db, actor_id)
    await check()
    current = await read_owned_health_token(db, actor_id, expected.token.id)
    if current.digest != expected.digest or current.token.revoked_at != expected.token.revoked_at:
        raise ResourceConflictError("health_token", detail={"error_code": "STALE_STATE"})
    if current.token.revoked_at is not None:
        receipt.committed, receipt.no_op, receipt.values = (
            True,
            True,
            {"health_token_to_revoke": current.public_scope()},
        )
        return
    changed = await HealthMetricsService(db).revoke_token(actor_id, expected.token.id)
    observed = await read_owned_health_token(db, actor_id, expected.token.id)
    if not changed or observed.token.revoked_at is None or observed.digest != current.digest:
        raise ValueError("Source token revocation was not observed")
    await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise HealthTokenRevocationCompletionUnknown from exc
    receipt.committed, receipt.values = True, {"health_token_to_revoke": observed.public_scope()}
