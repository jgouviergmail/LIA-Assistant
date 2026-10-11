"""The assistant can request a local package picker; only its browser may supply bytes."""

from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.application.plugin_file_upload_schemas import PluginFileUploadInput
from src.domains.agents.application.plugin_file_upload_spec import PLUGIN_FILE_UPLOAD_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PLUGIN_FILE_UPLOAD_MANIFEST = ToolManifest(
    name=PLUGIN_FILE_UPLOAD_OPERATION.tool_name,
    agent="setting_agent",
    description=(
        "Prepare mandatory confirmation to import one personal Agent Plugins ZIP selected in the originating browser. "
        "The model supplies only an optional exact replace_plugin_id read from get_lia_plugins_tool, never local paths or bytes. "
        "The exact previous plugin and its skills/MCP servers are shown; replacing requires the same package name, "
        "and components absent from the new package will be removed. After HITL the person must choose and explicitly confirm the local ZIP. "
        "Original package/size/quotas and shared per-component guards apply, with fresh account/application/component capabilities "
        "and sealed replacement state. Import never runs a script or connects to a remote MCP server. "
        "File selection is unavailable from non-browser transports or another browser session. "
        "Report actual successful/skipped/removed and partial outcomes; unknown commits cannot replay. "
        "Local import does not require URL imports to be enabled."
    ),
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Optional exact owned plugin replacement",
            schema=PluginFileUploadInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_plugins",
    tool_category="create",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["import local plugin", "upload plugin ZIP"],
    display=DisplayMetadata(emoji="🧩", i18n_key="import_lia_plugin_file", category="tool"),
)
