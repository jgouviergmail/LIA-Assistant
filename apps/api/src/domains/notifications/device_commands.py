"""Current-account notification devices, shared by HTTP and native confirmations."""

import hashlib
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.notifications.models import UserFCMToken
from src.domains.users.repository import UserRepository
from src.infrastructure.notification_devices import (
    NotificationDeviceSnapshot,
    NotificationDeviceUnavailable,
)


def notification_device_snapshot(row: UserFCMToken) -> NotificationDeviceSnapshot:
    if not isinstance(row.token, str) or not row.token:
        raise NotificationDeviceUnavailable("Saved notification device unavailable")
    try:
        return NotificationDeviceSnapshot(
            id=row.id,
            device_type=row.device_type,
            device_name=row.device_name,
            is_active=row.is_active,
            last_used_at=row.last_used_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            token_digest=hashlib.sha256(row.token.encode("utf-8")).hexdigest(),
        )
    except ValidationError:
        raise NotificationDeviceUnavailable("Saved notification device unavailable") from None


async def delete_notification_device(
    db: AsyncSession,
    actor_id: UUID,
    device_id: UUID,
    *,
    expected: NotificationDeviceSnapshot | None = None,
) -> bool:
    """Lock current ownership and exact state; the caller owns transaction commit."""
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    row: UserFCMToken | None = await db.scalar(
        select(UserFCMToken)
        .where(UserFCMToken.id == device_id, UserFCMToken.user_id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None or row.id != device_id or row.user_id != actor_id:
        if expected is not None:
            raise ResourceConflictError("notification device", detail={"error_code": "STALE_STATE"})
        return False
    if expected is not None and notification_device_snapshot(row) != expected:
        raise ResourceConflictError("notification device", detail={"error_code": "STALE_STATE"})
    await db.delete(row)
    await db.flush()
    return True
