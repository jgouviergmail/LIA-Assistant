"""Current saved heartbeat snapshots and concrete, effect-free proposals."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.heartbeat_schemas import (
    HeartbeatPreferenceField,
    HeartbeatPreferencePatch,
    HeartbeatPreferenceProjection,
    HeartbeatPreferenceRead,
)
from src.domains.agents.application.preparation import _preference_content
from src.domains.heartbeat.preference_commands import (
    heartbeat_preference_values,
    heartbeat_settings_response,
)
from src.domains.heartbeat.source_availability import compute_available_sources
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.system_settings.registry import decode_bool


async def read_heartbeat_preferences(
    db: AsyncSession, actor_id: UUID, request: HeartbeatPreferenceRead
) -> HeartbeatPreferenceProjection:
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    fields = request.fields if request.fields is not None else list(HeartbeatPreferenceField)
    values = heartbeat_preference_values(actor, (field.value for field in fields))
    validated = HeartbeatPreferencePatch.model_validate(values)
    raw: str | None = await db.scalar(
        select(SystemSetting.value).where(
            SystemSetting.key == SystemSettingKey.CAPABILITY_HEARTBEAT_ENABLED
        )
    )
    platform_enabled = settings.heartbeat_enabled and (raw is None or decode_bool(raw))
    return HeartbeatPreferenceProjection(
        values=validated.model_dump(mode="json", exclude_unset=True),
        platform_enabled=platform_enabled,
        delivery_enabled=platform_enabled and actor.heartbeat_enabled,
        source_status=heartbeat_settings_response(
            actor, await compute_available_sources(actor, db)
        ),
    )


async def prepare_heartbeat_content(
    db: AsyncSession,
    actor_id: UUID,
    patch: HeartbeatPreferencePatch,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = HeartbeatPreferencePatch.model_validate(patch.model_dump(exclude_unset=True))
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    before = heartbeat_preference_values(actor, validated.model_fields_set)
    HeartbeatPreferencePatch.model_validate(before)
    return _preference_content(actor_id, validated, before, command_id=command_id)
