"""Public source and exact replacement identity enter mandatory human confirmation."""

from src.domains.agents.application.plugin_url_import_schemas import PluginUrlImportInput
from src.domains.agents.application.plugin_url_import_spec import PLUGIN_URL_IMPORT_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PLUGIN_URL_IMPORT_MANIFEST = ToolManifest(
    name=PLUGIN_URL_IMPORT_OPERATION.tool_name,
    agent="setting_agent",
    description=(
        "Prepare mandatory confirmation to import one personal Agent Plugins ZIP from a public HTTPS URL. "
        "Read installed plugins first; replacing one requires its exact replace_plugin_id and matching package name. "
        "The preview lists public identity, all files, skills, script presence and supported/skipped MCP transports; "
        "it never publishes instructions, commands, headers or existing credentials. "
        "Fresh application/instance and relevant Skills/MCP capabilities, owner checks, original quotas, "
        "SSRF/no-redirect/transfer limits and the shared account URL rate limit apply. "
        "Source bytes are hashed and fetched again after consent; changes require new confirmation. "
        "Original per-component imports may commit before later components fail: report actual installed/skipped/removed "
        "components and any incomplete result, never claim atomic success. Unknown commit acknowledgement cannot replay. "
        "Imported scripts retain third-party isolation; importing never runs a script or connects to a remote MCP server."
    ),
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Public HTTPS plugin ZIP and optional exact owned replacement",
            schema=PluginUrlImportInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_plugins",
    tool_category="create",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["import plugin URL", "install plugin ZIP"],
    display=DisplayMetadata(emoji="🧩", i18n_key="import_lia_plugin_url", category="tool"),
)
