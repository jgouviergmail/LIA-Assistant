"""Bounded saved device reads and effect-free notification removal proposals."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.notification_schemas import (
    NotificationDeviceRemovePatch,
    NotificationDeviceRemoveRequest,
    NotificationDevicesRead,
)
from src.domains.agents.application.preparation import _preference_content
from src.infrastructure.notification_devices import (
    NotificationDevicesProjection,
    get_notification_devices,
)


async def read_notification_devices(
    db: AsyncSession,
    actor_id: UUID,
    request: NotificationDevicesRead,
) -> NotificationDevicesProjection:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return await get_notification_devices().read(
        db,
        actor_id,
        device_id=request.device_id,
        after_id=request.after_id,
        limit=request.limit,
    )


async def prepare_notification_device_removal(
    db: AsyncSession,
    actor_id: UUID,
    request: NotificationDeviceRemoveRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    snapshot = await get_notification_devices().snapshot(db, actor_id, request.device_id)
    return _preference_content(
        actor_id,
        NotificationDeviceRemovePatch(notification_device_to_remove=snapshot),
        {"notification_device_to_remove": snapshot.model_dump(mode="json")},
        command_id=command_id,
    )
