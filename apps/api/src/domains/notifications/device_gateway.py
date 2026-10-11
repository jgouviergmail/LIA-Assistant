"""Domain-owned saved device projections and deletion behind an injected typed port."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.notifications.device_commands import (
    delete_notification_device,
    notification_device_snapshot,
)
from src.domains.notifications.models import UserFCMToken
from src.domains.notifications.schemas import TokenInfo
from src.infrastructure.notification_devices import (
    NotificationDeviceSnapshot,
    NotificationDevicesProjection,
    NotificationDeviceValue,
)


def assert_notification_device_coverage() -> None:
    if set(TokenInfo.model_fields) != set(NotificationDeviceValue.model_fields):
        raise AssertionError("New notification device UI fields require explicit projection review")


assert_notification_device_coverage()


class SavedNotificationDevices:
    async def read(
        self,
        db: AsyncSession,
        actor_id: UUID,
        *,
        device_id: UUID | None,
        after_id: UUID | None,
        limit: int,
    ) -> NotificationDevicesProjection:
        filters = [UserFCMToken.user_id == actor_id]
        if device_id is not None:
            filters.append(UserFCMToken.id == device_id)
        total = await db.scalar(select(func.count()).select_from(UserFCMToken).where(*filters))
        query = select(UserFCMToken).where(*filters).order_by(UserFCMToken.id).limit(limit + 1)
        if after_id is not None:
            query = query.where(UserFCMToken.id > after_id)
        rows = list((await db.scalars(query.execution_options(populate_existing=True))).all())
        values = [
            NotificationDeviceValue.model_validate(
                notification_device_snapshot(row).model_dump(
                    mode="json", exclude={"token_digest", "updated_at"}
                )
            )
            for row in rows[:limit]
        ]
        return NotificationDevicesProjection(
            devices=values,
            total=total or 0,
            next_cursor=values[-1].id if len(rows) > limit else None,
        )

    async def snapshot(
        self, db: AsyncSession, actor_id: UUID, device_id: UUID
    ) -> NotificationDeviceSnapshot:
        row: UserFCMToken | None = await db.scalar(
            select(UserFCMToken)
            .where(UserFCMToken.user_id == actor_id, UserFCMToken.id == device_id)
            .execution_options(populate_existing=True)
        )
        if row is None or row.id != device_id or row.user_id != actor_id:
            raise ResourceNotFoundError("notification device", str(device_id))
        return notification_device_snapshot(row)

    async def remove(
        self,
        db: AsyncSession,
        actor_id: UUID,
        device_id: UUID,
        *,
        expected: NotificationDeviceSnapshot,
    ) -> None:
        await delete_notification_device(db, actor_id, device_id, expected=expected)
