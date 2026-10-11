"""Saved notification registrations and confirmed removal, separate from device permission."""

from src.domains.agents.application.notification_schemas import (
    NotificationDeviceRemoveRequest,
    NotificationDevicesRead,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

NOTIFICATION_DEVICES_READ_MANIFEST = ToolManifest(
    name="get_lia_notification_devices_tool",
    agent="setting_agent",
    description="Read the current account's saved notification device registrations: id, name, device type, saved active state and timestamps. Follow next_cursor as after_id for all pages. These records do not grant browser/system permission or guarantee delivery. Push credentials never enter the result.",
    parameters=[
        ParameterSchema(
            name="query",
            type="object",
            required=False,
            description="Owned device selector or bounded page",
            schema=NotificationDevicesRead.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="devices", type="array", description="Saved notification registrations"
        ),
        OutputFieldSchema(path="total", type="integer", description="Matching registration count"),
        OutputFieldSchema(
            path="next_cursor", type="string", description="Next page, null when complete"
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_notification_devices",
    semantic_keywords=["my notification devices", "which devices receive notifications"],
    display=DisplayMetadata(emoji="🔔", i18n_key="get_lia_notification_devices", category="tool"),
)
NOTIFICATION_DEVICE_REMOVE_MANIFEST = ToolManifest(
    name="remove_lia_notification_device_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to remove one current owned notification-device registration selected by its saved id. No deletion before approval. Browser/system permission remains unchanged; register again on that device to restore notifications. Changed or rotated device registration requires a new preview.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="Owned saved device to remove",
            schema=NotificationDeviceRemoveRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="delete",
    binding_unit="lia_notification_devices",
    semantic_keywords=[
        "remove a notification device",
        "stop server notifications on this saved device",
    ],
    display=DisplayMetadata(emoji="🔔", i18n_key="remove_lia_notification_device", category="tool"),
)
