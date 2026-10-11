"""Application declarations compose native catalogue and execution identities."""

from pydantic import BaseModel

from src.domains.agents.application.assistant_schemas import AssistantPreferenceRead
from src.domains.agents.application.channel_schemas import (
    ChannelBindingsRead,
    ChannelBindingUnlinkPatch,
    ChannelBindingUpdatePatch,
)
from src.domains.agents.application.connection_schemas import (
    ConnectorConnectionsProjection,
    ConnectorConnectionsRead,
    ConnectorConnectionUnlinkPatch,
)
from src.domains.agents.application.connector_schemas import (
    ConnectorPreferencePatch,
    ConnectorPreferencesProjection,
    ConnectorPreferencesRead,
)
from src.domains.agents.application.heartbeat_schemas import (
    HeartbeatPreferencePatch,
    HeartbeatPreferenceProjection,
    HeartbeatPreferenceRead,
)
from src.domains.agents.application.layout_schemas import LayoutPreferenceRead
from src.domains.agents.application.live_connector_schemas import LiveConnectorPreferencePatch
from src.domains.agents.application.live_options_schemas import LiveOptionsRead
from src.domains.agents.application.live_schemas import (
    LivePreferencePatch,
    LivePreferenceProjection,
    LivePreferenceRead,
)
from src.domains.agents.application.location_schemas import HomeLocationPatch, LocationRead
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.notification_schemas import (
    NotificationDeviceRemovePatch,
    NotificationDevicesRead,
)
from src.domains.agents.application.operation_spec import (
    ApplicationEmptyRead,
    ApplicationOperationSpec,
    OperationKind,
    OperationRegistry,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.phone_spec import PHONE_OPERATIONS
from src.domains.agents.application.preference_fields import PREFERENCE_FIELDS, PreferenceField
from src.domains.agents.application.schemas import (
    ApplicationProjection,
    PreferencePatch,
    PreferenceRead,
)
from src.domains.agents.application.security_schemas import SecurityRead
from src.domains.agents.application.session_revocation_schemas import DeviceSessionRevokePatch
from src.domains.agents.application.session_schemas import DeviceSessionsRead
from src.domains.agents.application.shared_mcp_schemas import (
    SharedMCPPreferencePatch,
    SharedMCPPreferenceProjection,
    SharedMCPPreferenceRead,
)
from src.domains.auth.preference_commands import AssistantPreferencePatch
from src.domains.auth.security_queries import AccountSecurityProjection
from src.domains.auth.session_queries import DeviceSessionsProjection
from src.domains.channels.schemas import ChannelBindingListResponse
from src.domains.feature_switches.registry import PlatformCapability
from src.infrastructure.account_exports import AccountExportProjection
from src.infrastructure.account_preferences import LayoutPreferencePatch
from src.infrastructure.live_connector_preferences import (
    LiveConnectorPreferenceProjection,
    LiveOptionsPage,
)
from src.infrastructure.notification_devices import NotificationDevicesProjection

APPLICATION_OPERATIONS = OperationRegistry()
for native_operation in NATIVE_OPERATIONS:
    APPLICATION_OPERATIONS.register(native_operation)
APPLICATION_OPERATIONS.register(
    ApplicationOperationSpec(
        operation_id="device_session.revoke",
        tool_name="revoke_lia_device_session_tool",
        sections=("security-devices",),
        input_model=DeviceSessionRevokePatch,
        output_model=ApplicationExecutionOutcome,
        kind=OperationKind.ACTION,
    )
)
for phone_operation in PHONE_OPERATIONS:
    APPLICATION_OPERATIONS.register(phone_operation)
APPLICATION_OPERATIONS.register(
    ApplicationOperationSpec(
        operation_id="device_sessions.read",
        tool_name="get_lia_device_sessions_tool",
        sections=("security-devices",),
        input_model=DeviceSessionsRead,
        output_model=DeviceSessionsProjection,
        kind=OperationKind.READ,
    )
)
APPLICATION_OPERATIONS.register(
    ApplicationOperationSpec(
        operation_id="account_export.read",
        tool_name="get_lia_account_export_tool",
        sections=("security-export",),
        input_model=ApplicationEmptyRead,
        output_model=AccountExportProjection,
        kind=OperationKind.READ,
    )
)
APPLICATION_OPERATIONS.register(
    ApplicationOperationSpec(
        operation_id="security.read",
        tool_name="get_lia_security_settings_tool",
        sections=("security-auth",),
        input_model=SecurityRead,
        output_model=AccountSecurityProjection,
        kind=OperationKind.READ,
    )
)
for operation_id, tool_name, input_model, output_model, operation_kind in (
    (
        "live_connector_preferences.read",
        "get_lia_live_connector_settings_tool",
        LivePreferenceRead,
        LiveConnectorPreferenceProjection,
        OperationKind.READ,
    ),
    (
        "live_connector_preferences.update",
        "update_lia_live_connector_settings_tool",
        LiveConnectorPreferencePatch,
        ApplicationExecutionOutcome,
        OperationKind.ACTION,
    ),
    (
        "live_options.read",
        "get_lia_live_options_tool",
        LiveOptionsRead,
        LiveOptionsPage,
        OperationKind.READ,
    ),
):
    APPLICATION_OPERATIONS.register(
        ApplicationOperationSpec(
            operation_id=operation_id,
            tool_name=tool_name,
            sections=("live-mode",),
            input_model=input_model,
            output_model=output_model,
            kind=operation_kind,
            required_capabilities=(PlatformCapability.LIVE,),
        )
    )
for operation_id, tool_name, live_model, live_kind in (
    (
        "live_preferences.read",
        "get_lia_live_preferences_tool",
        LivePreferenceRead,
        OperationKind.READ,
    ),
    (
        "live_preferences.update",
        "update_lia_live_preferences_tool",
        LivePreferencePatch,
        OperationKind.ACTION,
    ),
):
    APPLICATION_OPERATIONS.register(
        ApplicationOperationSpec(
            operation_id=operation_id,
            tool_name=tool_name,
            sections=("live-mode",),
            input_model=live_model,
            output_model=(
                LivePreferenceProjection
                if live_kind == OperationKind.READ
                else ApplicationExecutionOutcome
            ),
            kind=live_kind,
            required_capabilities=(PlatformCapability.LIVE,),
        )
    )
for operation_id, tool_name, notification_model, notification_kind in (
    (
        "notification_devices.read",
        "get_lia_notification_devices_tool",
        NotificationDevicesRead,
        OperationKind.READ,
    ),
    (
        "notification_device.remove",
        "remove_lia_notification_device_tool",
        NotificationDeviceRemovePatch,
        OperationKind.ACTION,
    ),
):
    APPLICATION_OPERATIONS.register(
        ApplicationOperationSpec(
            operation_id=operation_id,
            tool_name=tool_name,
            sections=("notifications",),
            input_model=notification_model,
            output_model=(
                NotificationDevicesProjection
                if notification_kind == OperationKind.READ
                else ApplicationExecutionOutcome
            ),
            kind=notification_kind,
        )
    )
for operation_id, tool_name, connection_model, connection_kind in (
    (
        "connector_connections.read",
        "get_lia_connectors_tool",
        ConnectorConnectionsRead,
        OperationKind.READ,
    ),
    (
        "connector_connection.unlink",
        "disconnect_lia_connector_tool",
        ConnectorConnectionUnlinkPatch,
        OperationKind.ACTION,
    ),
):
    APPLICATION_OPERATIONS.register(
        ApplicationOperationSpec(
            operation_id=operation_id,
            tool_name=tool_name,
            sections=("connectors",),
            input_model=connection_model,
            output_model=(
                ConnectorConnectionsProjection
                if connection_kind == OperationKind.READ
                else ApplicationExecutionOutcome
            ),
            kind=connection_kind,
        )
    )
for operation_id, tool_name, shared_model, shared_kind in (
    (
        "shared_mcp_preferences.read",
        "get_lia_shared_mcp_preferences_tool",
        SharedMCPPreferenceRead,
        OperationKind.READ,
    ),
    (
        "shared_mcp_preferences.update",
        "update_lia_shared_mcp_preferences_tool",
        SharedMCPPreferencePatch,
        OperationKind.ACTION,
    ),
):
    APPLICATION_OPERATIONS.register(
        ApplicationOperationSpec(
            operation_id=operation_id,
            tool_name=tool_name,
            sections=("admin-mcp-servers",),
            input_model=shared_model,
            output_model=(
                SharedMCPPreferenceProjection
                if shared_kind == OperationKind.READ
                else ApplicationExecutionOutcome
            ),
            kind=shared_kind,
            required_capabilities=(PlatformCapability.MCP,),
        )
    )
for operation_id, tool_name, connector_model, connector_kind in (
    (
        "connector_preferences.read",
        "get_lia_connector_preferences_tool",
        ConnectorPreferencesRead,
        OperationKind.READ,
    ),
    (
        "connector_preferences.update",
        "update_lia_connector_preferences_tool",
        ConnectorPreferencePatch,
        OperationKind.ACTION,
    ),
):
    APPLICATION_OPERATIONS.register(
        ApplicationOperationSpec(
            operation_id=operation_id,
            tool_name=tool_name,
            sections=("connectors",),
            input_model=connector_model,
            output_model=(
                ConnectorPreferencesProjection
                if connector_kind == OperationKind.READ
                else ApplicationExecutionOutcome
            ),
            kind=connector_kind,
        )
    )
for operation_id, tool_name, channel_model, channel_kind in (
    (
        "channel_bindings.read",
        "get_lia_channel_bindings_tool",
        ChannelBindingsRead,
        OperationKind.READ,
    ),
    (
        "channel_binding.update",
        "update_lia_channel_binding_tool",
        ChannelBindingUpdatePatch,
        OperationKind.ACTION,
    ),
    (
        "channel_binding.unlink",
        "unlink_lia_channel_binding_tool",
        ChannelBindingUnlinkPatch,
        OperationKind.ACTION,
    ),
):
    APPLICATION_OPERATIONS.register(
        ApplicationOperationSpec(
            operation_id=operation_id,
            tool_name=tool_name,
            sections=("channels",),
            input_model=channel_model,
            output_model=(
                ChannelBindingListResponse
                if channel_kind == OperationKind.READ
                else ApplicationExecutionOutcome
            ),
            kind=channel_kind,
            required_capabilities=(PlatformCapability.CHANNELS,),
        )
    )
for operation_id, tool_name, heartbeat_model, heartbeat_kind in (
    (
        "heartbeat_preferences.read",
        "get_lia_heartbeat_preferences_tool",
        HeartbeatPreferenceRead,
        OperationKind.READ,
    ),
    (
        "heartbeat_preferences.update",
        "update_lia_heartbeat_preferences_tool",
        HeartbeatPreferencePatch,
        OperationKind.ACTION,
    ),
):
    APPLICATION_OPERATIONS.register(
        ApplicationOperationSpec(
            operation_id=operation_id,
            tool_name=tool_name,
            sections=("heartbeat",),
            input_model=heartbeat_model,
            output_model=(
                HeartbeatPreferenceProjection
                if heartbeat_kind == OperationKind.READ
                else ApplicationExecutionOutcome
            ),
            kind=heartbeat_kind,
        )
    )
for operation_id, tool_name, location_model, location_kind in (
    ("locations.read", "get_lia_locations_tool", LocationRead, OperationKind.READ),
    (
        "home_location.update",
        "update_lia_home_location_tool",
        HomeLocationPatch,
        OperationKind.ACTION,
    ),
):
    APPLICATION_OPERATIONS.register(
        ApplicationOperationSpec(
            operation_id=operation_id,
            tool_name=tool_name,
            sections=("location",),
            input_model=location_model,
            output_model=(
                ApplicationProjection
                if location_kind == OperationKind.READ
                else ApplicationExecutionOutcome
            ),
            kind=location_kind,
        )
    )
model: type[BaseModel]
for operation_id, tool_name, model, kind in (
    (
        "layout_preferences.read",
        "get_lia_layout_preferences_tool",
        LayoutPreferenceRead,
        OperationKind.READ,
    ),
    (
        "layout_preferences.update",
        "update_lia_layout_preferences_tool",
        LayoutPreferencePatch,
        OperationKind.ACTION,
    ),
):
    APPLICATION_OPERATIONS.register(
        ApplicationOperationSpec(
            operation_id=operation_id,
            tool_name=tool_name,
            sections=("briefing-grid", "chat-shortcuts", "my-shortcuts"),
            input_model=model,
            output_model=(
                ApplicationProjection if kind == OperationKind.READ else ApplicationExecutionOutcome
            ),
            kind=kind,
        )
    )
APPLICATION_OPERATIONS.register(
    ApplicationOperationSpec(
        operation_id="preferences.read",
        tool_name="get_lia_preferences_tool",
        sections=tuple(dict.fromkeys(PREFERENCE_FIELDS.values())),
        input_model=PreferenceRead,
        output_model=ApplicationProjection,
        kind=OperationKind.READ,
    )
)
for operation_id, tool_name, model, kind in (
    (
        "assistant_preferences.read",
        "get_lia_assistant_preferences_tool",
        AssistantPreferenceRead,
        OperationKind.READ,
    ),
    (
        "assistant_preferences.update",
        "update_lia_assistant_preferences_tool",
        AssistantPreferencePatch,
        OperationKind.ACTION,
    ),
):
    APPLICATION_OPERATIONS.register(
        ApplicationOperationSpec(
            operation_id=operation_id,
            tool_name=tool_name,
            sections=(
                "memories",
                "health-metrics",
                "usage-preferences",
                "location",
                "voice-mode",
                "notifications",
                "security-auth",
                "debug-panel",
                "display-mode",
            ),
            input_model=model,
            output_model=(
                ApplicationProjection if kind == OperationKind.READ else ApplicationExecutionOutcome
            ),
            kind=kind,
        )
    )
APPLICATION_OPERATIONS.register(
    ApplicationOperationSpec(
        operation_id="preferences.update",
        tool_name="update_lia_preferences_tool",
        sections=tuple(dict.fromkeys(field.section for field in PreferenceField if field.writable)),
        input_model=PreferencePatch,
        output_model=ApplicationExecutionOutcome,
        kind=OperationKind.ACTION,
    )
)
