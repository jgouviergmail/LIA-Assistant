"""Personal opt-out manifests never offer administrator server configuration."""

from src.domains.agents.application.shared_mcp_schemas import (
    SharedMCPPreferenceRead,
    SharedMCPPreferenceUpdateRequest,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

SHARED_MCP_READ_MANIFEST = ToolManifest(
    name="get_lia_shared_mcp_preferences_tool",
    agent="setting_agent",
    description="Read this account's enabled choices and tool counts for globally configured shared MCP servers. Follow next_cursor as after_key for all pages. This reads personal preferences only; full tool descriptions, credentials and global configuration are separate surfaces.",
    parameters=[
        ParameterSchema(
            name="query",
            type="object",
            required=False,
            description="Selected server or bounded preference page",
            schema=SharedMCPPreferenceRead.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="servers", type="array", description="Personal shared server choices"
        ),
        OutputFieldSchema(path="total", type="integer", description="Matching server count"),
        OutputFieldSchema(
            path="next_cursor", type="string", description="Next page, null when complete"
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_shared_mcp_preferences",
    semantic_keywords=["my shared MCP servers", "shared server enabled for me"],
    display=DisplayMetadata(emoji="⚙️", i18n_key="get_lia_shared_mcp_preferences", category="tool"),
)
SHARED_MCP_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_shared_mcp_preferences_tool",
    agent="setting_agent",
    description="Prepare human confirmation to enable or disable one configured shared MCP server for this account only. Read the current server key first. No state changes before approval. A disabled platform cannot be overridden; global server configuration and other accounts are never changed.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="Existing shared server and desired personal enabled choice",
            schema=SharedMCPPreferenceUpdateRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_shared_mcp_preferences",
    semantic_keywords=["disable shared MCP for me", "enable shared MCP for me"],
    display=DisplayMetadata(
        emoji="⚙️", i18n_key="update_lia_shared_mcp_preferences", category="tool"
    ),
)
