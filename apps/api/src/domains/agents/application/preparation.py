"""Preparation resolves concrete values; it never writes application preferences."""

from uuid import UUID

from pydantic import JsonValue, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.assistant_queries import read_assistant_preferences
from src.domains.agents.application.assistant_schemas import (
    AssistantPreferenceField,
    AssistantPreferenceRead,
)
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.channel_schemas import (
    ChannelBindingUnlinkPatch,
    ChannelBindingUpdatePatch,
)
from src.domains.agents.application.connection_schemas import ConnectorConnectionUnlinkPatch
from src.domains.agents.application.connector_schemas import ConnectorPreferencePatch
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.heartbeat_schemas import HeartbeatPreferencePatch
from src.domains.agents.application.interest_settings_schemas import InterestSettingsPatch
from src.domains.agents.application.layout_queries import read_layout_preferences
from src.domains.agents.application.layout_schemas import (
    LayoutPreferenceField,
    LayoutPreferenceRead,
)
from src.domains.agents.application.live_connector_schemas import LiveConnectorPreferencePatch
from src.domains.agents.application.live_schemas import LivePreferencePatch
from src.domains.agents.application.location_schemas import HomeLocationPatch
from src.domains.agents.application.notification_schemas import NotificationDeviceRemovePatch
from src.domains.agents.application.phone_number_schemas import PhoneNumberPatch
from src.domains.agents.application.phone_preference_schemas import PhonePreferencePatch
from src.domains.agents.application.preference_dispatch import PreferenceIntent
from src.domains.agents.application.preference_fields import PreferenceField
from src.domains.agents.application.queries import read_preferences
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.schemas import (
    PreferenceChangeRequest,
    PreferencePatch,
    PreferenceRead,
)
from src.domains.agents.application.session_revocation_schemas import DeviceSessionRevokePatch
from src.domains.agents.application.shared_mcp_schemas import SharedMCPPreferencePatch
from src.domains.agents.effects.digest import payload_digest
from src.domains.auth.preference_commands import AssistantPreferencePatch, stt_remote_available
from src.infrastructure.account_preferences import LayoutPreferencePatch, require_layout_scope
from src.infrastructure.personalization import require_selectable_personality

_INTEGER: TypeAdapter[int] = TypeAdapter(int)


async def prepare_layout_content(
    db: AsyncSession,
    actor_id: UUID,
    patch: LayoutPreferencePatch,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = LayoutPreferencePatch.model_validate(patch.model_dump(exclude_unset=True))
    before = await read_layout_preferences(
        db,
        actor_id,
        LayoutPreferenceRead(
            fields=[
                field
                for field in LayoutPreferenceField
                if field.value in validated.model_fields_set
            ]
        ),
    )
    require_layout_scope(await load_actor(db, actor_id), validated)
    return _preference_content(actor_id, validated, before.values, command_id=command_id)


async def prepare_assistant_content(
    db: AsyncSession,
    actor_id: UUID,
    patch: AssistantPreferencePatch,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = AssistantPreferencePatch.model_validate(patch.model_dump(exclude_unset=True))
    request = AssistantPreferenceRead(
        fields=[
            field for field in AssistantPreferenceField if field.value in validated.model_fields_set
        ]
    )
    before = await read_assistant_preferences(db, actor_id, request)
    if validated.voice_stt_mode == "remote" and not stt_remote_available():
        raise ValueError("Remote STT is not configured")
    return _preference_content(actor_id, validated, before.values, command_id=command_id)


def preference_schema_fingerprint() -> str:
    return payload_digest(PreferencePatch.model_json_schema())


def font_step_patch(current: int, step: int) -> PreferencePatch:
    if type(current) is not int or type(step) is not int or step not in {-1, 1}:
        raise ValueError("Font size adjustment requires one whole-pixel UI step")
    return PreferencePatch(font_size=current + step)


async def prepare_preference_content(
    db: AsyncSession, actor_id: UUID, patch: PreferencePatch, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    # Revalidation also closes model_copy / checkpoint paths, which bypass validators.
    validated = PreferencePatch.model_validate(patch.model_dump(exclude_unset=True))
    request = PreferenceRead(
        fields=[field for field in PreferenceField if field.value in validated.model_fields_set]
    )
    before = await read_preferences(db, actor_id, request)
    if "personality_id" in validated.model_fields_set:
        await require_selectable_personality(db, validated.personality_id)
    return _preference_content(actor_id, validated, before.values, command_id=command_id)


async def prepare_preference_change(
    db: AsyncSession, actor_id: UUID, change: PreferenceChangeRequest
) -> ApplicationActionDraftContent:
    parsed = PreferenceChangeRequest.model_validate(change)
    request = PreferenceChangeRequest.model_validate(parsed.model_dump(exclude_unset=True))
    if request.mode == "set":
        if request.patch is None:
            raise ValueError("A concrete patch is required")
        return await prepare_preference_content(db, actor_id, request.patch)
    before = await read_preferences(
        db, actor_id, PreferenceRead(fields=[PreferenceField.FONT_SIZE])
    )
    current = _INTEGER.validate_python(before.values["font_size"], strict=True)
    patch = font_step_patch(current, 1 if request.mode == "increase_font" else -1)
    return _preference_content(actor_id, patch, before.values)


def _preference_content(
    actor_id: UUID,
    validated: PreferenceIntent,
    before: dict[str, JsonValue],
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    after = validated.model_dump(mode="json", exclude_unset=True)
    operation_id = {
        PreferencePatch: "preferences.update",
        AssistantPreferencePatch: "assistant_preferences.update",
        LayoutPreferencePatch: "layout_preferences.update",
        HomeLocationPatch: "home_location.update",
        HeartbeatPreferencePatch: "heartbeat_preferences.update",
        InterestSettingsPatch: "interest_settings.update",
        ChannelBindingUpdatePatch: "channel_binding.update",
        ChannelBindingUnlinkPatch: "channel_binding.unlink",
        ConnectorPreferencePatch: "connector_preferences.update",
        SharedMCPPreferencePatch: "shared_mcp_preferences.update",
        ConnectorConnectionUnlinkPatch: "connector_connection.unlink",
        NotificationDeviceRemovePatch: "notification_device.remove",
        LivePreferencePatch: "live_preferences.update",
        LiveConnectorPreferencePatch: "live_connector_preferences.update",
        PhonePreferencePatch: "phone_preferences.update",
        PhoneNumberPatch: "phone_number.update",
        DeviceSessionRevokePatch: "device_session.revoke",
    }[type(validated)]
    desired: dict[str, JsonValue] = (
        {next(iter(after)): None}
        if isinstance(
            validated,
            ChannelBindingUnlinkPatch
            | ConnectorConnectionUnlinkPatch
            | NotificationDeviceRemovePatch
            | DeviceSessionRevokePatch,
        )
        else after
    )
    return build_action_content(
        actor_id,
        APPLICATION_OPERATIONS.get(operation_id),
        validated,
        before,
        desired,
        command_id=command_id,
    )
