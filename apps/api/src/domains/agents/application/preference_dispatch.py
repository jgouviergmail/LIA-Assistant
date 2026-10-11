"""Finite preference adapters compose domain owners; no arbitrary route dispatch."""

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.core.i18n import resolve_language
from src.domains.agents.application.channel_schemas import (
    ChannelBindingUnlinkPatch,
    ChannelBindingUpdatePatch,
)
from src.domains.agents.application.connection_schemas import (
    ConnectorConnectionUnlinkPatch,
)
from src.domains.agents.application.connector_schemas import ConnectorPreferencePatch
from src.domains.agents.application.heartbeat_schemas import HeartbeatPreferencePatch
from src.domains.agents.application.interest_settings_schemas import (
    InterestSettingsPatch,
)
from src.domains.agents.application.live_connector_schemas import (
    LiveConnectorCommandValues,
    LiveConnectorPreferencePatch,
)
from src.domains.agents.application.live_schemas import LivePreferencePatch
from src.domains.agents.application.location_schemas import HomeLocationPatch
from src.domains.agents.application.notification_schemas import (
    NotificationDeviceRemovePatch,
)
from src.domains.agents.application.phone_number_schemas import (
    PhoneNumberCommandValues,
    PhoneNumberPatch,
)
from src.domains.agents.application.phone_preference_schemas import PhonePreferencePatch
from src.domains.agents.application.schemas import PreferencePatch
from src.domains.agents.application.session_revocation_schemas import (
    DeviceSessionRevokePatch,
)
from src.domains.agents.application.shared_mcp_schemas import SharedMCPPreferencePatch
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.auth.preference_commands import (
    AssistantPreferencePatch,
    update_assistant_preferences,
)
from src.domains.auth.session_commands import revoke_owned_device_session
from src.domains.channels.preference_commands import (
    ChannelBindingSnapshot,
    set_channel_binding_state,
    unlink_owned_channel_binding,
)
from src.domains.connectors.preferences.commands import (
    ConnectorPreferenceSnapshot,
    update_owned_connector_preferences,
)
from src.domains.connectors.preferences.schemas import PreferencesRequest
from src.domains.connectors.removal_commands import ConnectorRemovalSnapshot
from src.domains.connectors.service import ConnectorService
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.heartbeat.preference_commands import update_heartbeat_preferences
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.service import UserService
from src.infrastructure.account_preferences import (
    LayoutPreferencePatch,
    update_layout_preferences,
)
from src.infrastructure.live_connector_preferences import get_live_connector_preferences
from src.infrastructure.live_preferences import (
    LivePreferenceSnapshot,
    get_live_preferences,
)
from src.infrastructure.mcp.preferences_contract import SharedMCPPreferenceSnapshot
from src.infrastructure.mcp.preferences_gateway import get_shared_mcp_preferences
from src.infrastructure.notification_devices import (
    NotificationDeviceSnapshot,
    get_notification_devices,
)
from src.infrastructure.phone_number_preferences import get_phone_number_preferences
from src.infrastructure.phone_preferences import (
    PhonePreferenceSnapshot,
    get_phone_preferences,
)

PreferenceIntent = (
    PreferencePatch
    | AssistantPreferencePatch
    | LayoutPreferencePatch
    | HomeLocationPatch
    | HeartbeatPreferencePatch
    | InterestSettingsPatch
    | ChannelBindingUpdatePatch
    | ChannelBindingUnlinkPatch
    | ConnectorPreferencePatch
    | SharedMCPPreferencePatch
    | ConnectorConnectionUnlinkPatch
    | NotificationDeviceRemovePatch
    | LivePreferencePatch
    | LiveConnectorPreferencePatch
    | PhonePreferencePatch
    | PhoneNumberPatch
    | DeviceSessionRevokePatch
)


async def _execute_saved_service_commands(
    db: AsyncSession,
    actor_id: UUID,
    patch: (
        SharedMCPPreferencePatch
        | ConnectorConnectionUnlinkPatch
        | NotificationDeviceRemovePatch
        | LivePreferencePatch
        | LiveConnectorPreferencePatch
        | PhonePreferencePatch
        | PhoneNumberPatch
        | DeviceSessionRevokePatch
    ),
    before: Mapping[str, JsonValue],
    receipt: PreferenceWriteReceipt,
    approved_until: datetime | None,
) -> None:
    if isinstance(patch, DeviceSessionRevokePatch):
        await _execute_session_revocation(db, actor_id, patch, before, receipt, approved_until)
        return
    if isinstance(patch, PhoneNumberPatch):
        await _execute_phone_number(db, actor_id, patch, before, receipt)
        return
    if isinstance(patch, PhonePreferencePatch):
        await _execute_phone_preferences(db, actor_id, patch, before, receipt)
        return
    if isinstance(patch, LiveConnectorPreferencePatch):
        await require_capability_fresh(db, PlatformCapability.LIVE)
        previous_settings = LiveConnectorCommandValues.model_validate(
            before.get("live_connector_settings")
        )
        desired_settings = patch.live_connector_settings
        if desired_settings.expected != previous_settings.expected:
            raise ValueError("A settings command cannot change its connector snapshot")
        context = runtime_context_if_running()
        await get_live_connector_preferences().write(
            db,
            actor_id,
            desired_settings.expected.provider,
            desired_settings.settings.model_dump(mode="json"),
            expected=previous_settings.expected,
            receipt=receipt,
            language=resolve_language(context.language if context else None),
        )
        return
    if isinstance(patch, LivePreferencePatch):
        await require_capability_fresh(db, PlatformCapability.LIVE)
        previous_live = LivePreferenceSnapshot.model_validate(before.get("live_reflexes"))
        desired_live = patch.live_reflexes
        if desired_live.model_copy(update={"values": previous_live.values}) != previous_live:
            raise ValueError("Reflex changes cannot change provider identity or saved-state digest")
        await get_live_preferences().write(
            db, actor_id, desired_live.values, expected=previous_live, receipt=receipt
        )
        return
    if isinstance(patch, NotificationDeviceRemovePatch):
        previous_device = NotificationDeviceSnapshot.model_validate(
            before.get("notification_device_to_remove")
        )
        if patch.notification_device_to_remove != previous_device:
            raise ValueError("A device removal must name the exact displayed device")
        await get_notification_devices().remove(
            db, actor_id, previous_device.id, expected=previous_device
        )
        await db.commit()
        receipt.committed = True
        return
    if isinstance(patch, SharedMCPPreferencePatch):
        await _execute_shared_mcp(db, actor_id, patch, before, receipt)
        return
    previous = ConnectorRemovalSnapshot.model_validate(before.get("connector_to_disconnect"))
    if patch.connector_to_disconnect != previous:
        raise ValueError("An unlink command must name the exact displayed connection")
    await ConnectorService(db).delete_connector(
        actor_id, previous.id, expected=previous, receipt=receipt
    )


async def _execute_shared_mcp(
    db: AsyncSession,
    actor_id: UUID,
    patch: SharedMCPPreferencePatch,
    before: Mapping[str, JsonValue],
    receipt: PreferenceWriteReceipt,
) -> None:
    await require_capability_fresh(db, PlatformCapability.MCP)
    previous = SharedMCPPreferenceSnapshot.model_validate(before.get("shared_mcp_server"))
    desired = patch.shared_mcp_server
    if desired.model_copy(update={"enabled_for_user": previous.enabled_for_user}) != previous:
        raise ValueError("A personal refusal cannot change global server identity or catalogue")
    await get_shared_mcp_preferences().write(
        db,
        actor_id,
        previous.server_key,
        desired.enabled_for_user,
        expected=previous,
        receipt=receipt,
    )


async def _execute_phone_preferences(
    db: AsyncSession,
    actor_id: UUID,
    patch: PhonePreferencePatch,
    before: Mapping[str, JsonValue],
    receipt: PreferenceWriteReceipt,
) -> None:
    previous = PhonePreferenceSnapshot.model_validate(before.get("phone_preferences"))
    desired = patch.phone_preferences
    if desired.model_copy(update={"values": previous.values}) != previous:
        raise ValueError("A phone consent change cannot replace its saved-state snapshot")

    async def check() -> None:
        # A lock wait must not revive an operator's withdrawn authority.
        await require_capability_fresh(db, PlatformCapability.APPLICATION_TOOLS)
        await require_capability_fresh(db, PlatformCapability.TELEPHONY)

    await check()
    await get_phone_preferences().write(
        db,
        actor_id,
        desired.values,
        expected=previous,
        receipt=receipt,
        check=check,
    )


async def _execute_phone_number(
    db: AsyncSession,
    actor_id: UUID,
    patch: PhoneNumberPatch,
    before: Mapping[str, JsonValue],
    receipt: PreferenceWriteReceipt,
) -> None:
    previous = PhoneNumberCommandValues.model_validate(before.get("phone_number"))
    desired = patch.phone_number
    if (
        desired.expected != previous.expected
        or previous.number != previous.expected.values.phone_number
    ):
        raise ValueError("A number change cannot replace its saved-state snapshot")

    async def check() -> None:
        await require_capability_fresh(db, PlatformCapability.APPLICATION_TOOLS)
        await require_capability_fresh(db, PlatformCapability.TELEPHONY)

    await check()
    await get_phone_number_preferences().write(
        db,
        actor_id,
        desired.number,
        expected=previous.expected,
        receipt=receipt,
        check=check,
    )


_PREFERENCE_MODELS: dict[str, type[PreferenceIntent]] = {
    "interest_settings.update": InterestSettingsPatch,
    "device_session.revoke": DeviceSessionRevokePatch,
    "phone_number.update": PhoneNumberPatch,
    "phone_preferences.update": PhonePreferencePatch,
    "live_connector_preferences.update": LiveConnectorPreferencePatch,
    "live_preferences.update": LivePreferencePatch,
    "notification_device.remove": NotificationDeviceRemovePatch,
    "connector_connection.unlink": ConnectorConnectionUnlinkPatch,
    "preferences.update": PreferencePatch,
    "assistant_preferences.update": AssistantPreferencePatch,
    "layout_preferences.update": LayoutPreferencePatch,
    "home_location.update": HomeLocationPatch,
    "heartbeat_preferences.update": HeartbeatPreferencePatch,
    "channel_binding.update": ChannelBindingUpdatePatch,
    "channel_binding.unlink": ChannelBindingUnlinkPatch,
    "connector_preferences.update": ConnectorPreferencePatch,
    "shared_mcp_preferences.update": SharedMCPPreferencePatch,
}


async def _execute_session_revocation(
    db: AsyncSession,
    actor_id: UUID,
    patch: DeviceSessionRevokePatch,
    before: Mapping[str, JsonValue],
    receipt: PreferenceWriteReceipt,
    approved_until: datetime | None,
) -> None:
    previous = DeviceSessionRevokePatch.model_validate(before)
    context = runtime_context_if_running()
    if patch != previous or approved_until is None:
        raise ValueError("A revocation requires its exact selection and approval deadline")
    if context is None or context.user_id != actor_id:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})

    async def check() -> None:
        await require_capability_fresh(db, PlatformCapability.APPLICATION_TOOLS)

    await check()
    await revoke_owned_device_session(
        db,
        actor_id,
        patch.session_to_revoke,
        context.application_origin,
        receipt,
        check=check,
        approved_until=approved_until,
    )


def preference_model(operation_id: str) -> type[PreferenceIntent]:
    try:
        return _PREFERENCE_MODELS[operation_id]
    except KeyError:
        raise ValueError("Unknown preference operation") from None


async def execute_preference_patch(
    db: AsyncSession,
    actor_id: UUID,
    operation_id: str,
    intent: object,
    before: Mapping[str, JsonValue],
    receipt: PreferenceWriteReceipt,
    *,
    approved_until: datetime | None = None,
) -> None:
    patch = preference_model(operation_id).model_validate(intent)
    if isinstance(
        patch,
        SharedMCPPreferencePatch
        | ConnectorConnectionUnlinkPatch
        | NotificationDeviceRemovePatch
        | LivePreferencePatch
        | LiveConnectorPreferencePatch
        | PhonePreferencePatch
        | PhoneNumberPatch
        | DeviceSessionRevokePatch,
    ):
        await _execute_saved_service_commands(db, actor_id, patch, before, receipt, approved_until)
        return
    if isinstance(patch, PreferencePatch):
        await UserService(db).update_user(
            actor_id, patch, expected_preferences=before, receipt=receipt
        )
    elif isinstance(patch, AssistantPreferencePatch):
        await update_assistant_preferences(db, actor_id, patch, expected=before, receipt=receipt)
    elif isinstance(patch, LayoutPreferencePatch):
        await update_layout_preferences(db, actor_id, patch, expected=before, receipt=receipt)
    elif isinstance(patch, HeartbeatPreferencePatch):
        await update_heartbeat_preferences(db, actor_id, patch, expected=before, receipt=receipt)
    elif isinstance(patch, ChannelBindingUpdatePatch):
        await require_capability_fresh(db, PlatformCapability.CHANNELS)
        previous = ChannelBindingSnapshot.model_validate(before.get("channel_binding"))
        if patch.channel_binding.model_copy(update={"is_active": previous.is_active}) != previous:
            raise ValueError("A channel state command cannot change the binding identity")
        await set_channel_binding_state(
            db,
            actor_id,
            previous.id,
            patch.channel_binding.is_active,
            expected=previous,
            receipt=receipt,
        )
    elif isinstance(patch, ChannelBindingUnlinkPatch):
        await require_capability_fresh(db, PlatformCapability.CHANNELS)
        previous = ChannelBindingSnapshot.model_validate(before.get("channel_binding"))
        if patch.channel_binding != previous:
            raise ValueError("An unlink command must name the exact displayed binding")
        await unlink_owned_channel_binding(
            db,
            actor_id,
            previous.id,
            expected=previous,
            receipt=receipt,
        )
    elif isinstance(patch, ConnectorPreferencePatch):
        previous_connector = ConnectorPreferenceSnapshot.model_validate(
            before.get("connector_preferences")
        )
        desired_connector = patch.connector_preferences
        if (
            desired_connector.model_copy(update={"preferences": previous_connector.preferences})
            != previous_connector
        ):
            raise ValueError("A preference command cannot change connector identity or status")
        await update_owned_connector_preferences(
            db,
            actor_id,
            previous_connector.id,
            PreferencesRequest.model_validate(desired_connector.preferences),
            expected=previous_connector,
            receipt=receipt,
        )
    else:
        await _execute_home_location(db, actor_id, patch, before, receipt)


async def _execute_home_location(
    db: AsyncSession,
    actor_id: UUID,
    patch: PreferenceIntent,
    before: Mapping[str, JsonValue],
    receipt: PreferenceWriteReceipt,
) -> None:
    if not isinstance(patch, HomeLocationPatch):
        raise ValueError("This preference requires its dedicated application executor")
    if patch.home_location is None:
        await UserService(db).clear_home_location(
            actor_id, expected_locations=before, receipt=receipt
        )
    else:
        await UserService(db).set_home_location(
            actor_id,
            patch.home_location,
            resolved=True,
            expected_locations=before,
            receipt=receipt,
        )
