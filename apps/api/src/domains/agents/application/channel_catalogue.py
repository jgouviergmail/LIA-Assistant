"""Channel catalogue schemas expose selection and desired state, never binding credentials."""

from src.domains.agents.application.channel_schemas import (
    ChannelBindingUnlinkRequest,
    ChannelBindingUpdateRequest,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

CHANNELS_READ_MANIFEST = ToolManifest(
    name="get_lia_channel_bindings_tool",
    agent="setting_agent",
    description="Read this account's displayed external messaging channel identities and saved active state. Includes the bot username discovered at startup. Never returns an OTP, a credential or another account's bindings; active is a saved state, not a live provider health test.",
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="channels", type="object", description="Current account channel settings list"
        ),
        OutputFieldSchema(path="total", type="integer", description="Returned binding count"),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_channels",
    semantic_keywords=["is Telegram enabled", "which messaging channels are linked"],
    display=DisplayMetadata(emoji="⚙️", i18n_key="get_lia_channel_bindings", category="tool"),
)
CHANNEL_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_channel_binding_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to enable or disable one existing owned channel binding. Select its binding id from a current read and specify the desired enabled boolean, never a blind toggle. No state changes before approval; a changed binding requires another preview. Linking and OTP participation remain secure interface flows.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="Existing owned binding and desired state",
            schema=ChannelBindingUpdateRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_channels",
    semantic_keywords=["disable Telegram", "enable my linked messaging channel"],
    display=DisplayMetadata(emoji="⚙️", i18n_key="update_lia_channel_binding", category="tool"),
)

CHANNEL_UNLINK_MANIFEST = ToolManifest(
    name="unlink_lia_channel_binding_tool",
    agent="setting_agent",
    description="Prepare explicit human confirmation to remove one current owned external messaging binding. Read its binding id first. The preview names the exact binding and its removal; nothing is deleted before approval. A changed binding requires a new preview. Subsequent linking requires the secure application interface; never request or expose an OTP.",
    parameters=[
        ParameterSchema(
            name="binding",
            type="object",
            required=True,
            description="Current owned binding selected for removal",
            schema=ChannelBindingUnlinkRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending removal confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="delete",
    binding_unit="lia_channels",
    semantic_keywords=["unlink Telegram", "remove my linked messaging channel"],
    display=DisplayMetadata(emoji="⚙️", i18n_key="unlink_lia_channel_binding", category="tool"),
)
