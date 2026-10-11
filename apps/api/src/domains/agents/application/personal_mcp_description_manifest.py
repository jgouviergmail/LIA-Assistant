"""Cached metadata regeneration warns about the original accounted platform LLM."""

from src.domains.agents.application.personal_mcp_description_schemas import (
    PersonalMCPDescriptionInput,
)
from src.domains.agents.application.personal_mcp_description_spec import (
    PERSONAL_MCP_DESCRIPTION_OPERATION,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PERSONAL_MCP_DESCRIPTION_MANIFEST = ToolManifest(
    name=PERSONAL_MCP_DESCRIPTION_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory explicit confirmation to regenerate ONE owned personal MCP server's routing description from its already cached tool metadata. Select exact server_id through get_lia_personal_mcp_servers_tool. Cached tools are required. Preparation performs no model call; confirmation warns the operation may use the platform mcp_description model and overwrite the saved description. Original account/instance spend limits, actual token/cost accounting, paid-failure accounting and deterministic fallback apply. Metadata is an untrusted bounded sample. Provider work holds no account/server row lock; fresh authority, expiry and full-row CAS are checked again under locks before saving. A concurrent edit or revocation can refuse saving after an accounted model call. Final receipt contains only the observed saved description and tool count. No MCP connection, discovery, remote tool execution, credentials or administrative shared-server change. Unknown commits cannot replay.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned personal MCP server with cached tools",
            schema=PersonalMCPDescriptionInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_personal_mcp",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["regenerate personal MCP description", "describe personal MCP capabilities"],
    display=DisplayMetadata(
        emoji="🔌", i18n_key="regenerate_lia_personal_mcp_description", category="tool"
    ),
)
