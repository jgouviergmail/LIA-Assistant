"""Plugin group removal retains exact human consent and original lifecycle rules."""

from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.application.plugin_delete_schemas import PluginDeleteInput
from src.domains.agents.application.plugin_delete_spec import PLUGIN_DELETE_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PLUGIN_DELETE_MANIFEST = ToolManifest(
    name=PLUGIN_DELETE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory human confirmation to uninstall ONE owned plugin and ALL its installed skills and MCP servers. Select plugin_id through get_lia_plugins_tool. The complete public plugin/component names are displayed; every private row, credential configuration and bounded complete local file tree is sealed without exposing contents, credentials or paths. Changed group membership/settings/files require new approval. Fresh active account/application/instance-plugin authority is checked under shared owner/group locks and before commit. Original group removal uses reversible non-scanned file staging and one row commit. Unknown acknowledgement retains recoverable bytes and cannot replay; known success reports any file/pool/cache cleanup still pending. System or other-account components refuse. No provider/model call, skill execution or remote import.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned plugin id to remove as a whole group",
            schema=PluginDeleteInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_plugins",
    tool_category="delete",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["uninstall my plugin", "remove plugin and its components"],
    display=DisplayMetadata(emoji="🧩", i18n_key="delete_lia_plugin", category="tool"),
)
