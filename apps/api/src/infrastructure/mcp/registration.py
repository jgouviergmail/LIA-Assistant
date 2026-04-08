"""
MCP Registration Bridge — Registers MCP tools in both AgentRegistry and tool_registry.

CRITICAL: MCP tools must be registered in TWO registries:
1. AgentRegistry (manifests + instances) → used by SmartCatalogueService for filtering
2. tool_registry (instances) → used by parallel_executor for invocation

Admin MCP servers get per-server agents (e.g., "mcp_google_flights_agent") for
targeted domain routing via the query analyzer — homogeneous with user MCP.

Phase: evolution F2 — MCP Support
Created: 2026-02-28
Updated: 2026-03-03 — Per-server agent routing (F2.5)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.constants import (
    MCP_DISPLAY_EMOJI,
    MCP_ITERATIVE_TASK_SUFFIX,
    MCP_REFERENCE_TOOL_NAME,
)
from src.domains.agents.constants import AGENT_MCP, CONTEXT_DOMAIN_MCP
from src.infrastructure.mcp.schemas import MCPDiscoveredTool, MCPServerConfig
from src.infrastructure.mcp.security import resolve_hitl_requirement
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from src.infrastructure.mcp.utils import is_app_only

if TYPE_CHECKING:
    from src.domains.agents.registry.agent_registry import AgentRegistry
    from src.domains.agents.registry.catalogue import ParameterSchema, ToolManifest
    from src.infrastructure.mcp.schemas import MCPServerConfig

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level state for admin MCP domain routing
# Populated at startup by register_mcp_tools(), read per-request by
# collect_all_mcp_domains() in domain_taxonomy.py.
# ---------------------------------------------------------------------------
_admin_mcp_domains: dict[str, str] = {}  # domain_slug → description


def get_admin_mcp_domains() -> dict[str, str]:
    """Return admin MCP per-server domains (populated at startup).

    Returns:
        Copy of domain_slug → description mapping.
        E.g., {"mcp_google_flights": "Search flights, find airports, ..."}
    """
    return dict(_admin_mcp_domains)


def _register_iterative_task_tool(task_tool_name: str) -> None:
    """Register the generic mcp_server_task_tool under a per-server name.

    Each iterative MCP server needs its own entry in ToolRegistry so the
    parallel_executor can find the tool by the per-server manifest name
    (e.g., ``mcp_excalidraw_task``). The actual tool function is the same
    ``mcp_server_task_tool`` — only the registered name differs.

    Args:
        task_tool_name: Per-server tool name (e.g., "mcp_excalidraw_task").
    """
    from src.domains.agents.tools.tool_registry import get_tool, register_external_tool

    # If already registered (e.g., module reload), skip
    if get_tool(task_tool_name):
        return

    try:
        from src.domains.agents.tools.mcp_react_tools import mcp_server_task_tool

        # Create a named copy of the tool with the per-server name.
        # BaseTool.name is a Pydantic field — model_copy creates a shallow copy.
        named_tool = mcp_server_task_tool.model_copy(update={"name": task_tool_name})
        register_external_tool(named_tool)
        logger.info(
            "mcp_iterative_task_tool_registered",
            task_tool_name=task_tool_name,
        )
    except ImportError:
        logger.warning(
            "mcp_iterative_task_tool_import_failed",
            task_tool_name=task_tool_name,
            msg="mcp_react_tools module not available (MCP_REACT_ENABLED=false?)",
        )


def register_mcp_tools(
    registry: AgentRegistry,
    discovered_tools: dict[str, list[MCPDiscoveredTool]],
    adapters: dict[str, MCPToolAdapter],
    server_configs: dict[str, MCPServerConfig],
    global_hitl_required: bool,
    reference_content: dict[str, str] | None = None,
) -> int:
    """
    Register all MCP tools in AgentRegistry and tool_registry.

    Creates one AgentManifest per server (e.g., "mcp_google_flights_agent")
    for targeted domain routing by the query analyzer.

    Args:
        registry: The global AgentRegistry instance
        discovered_tools: Dict of server_name → list of discovered tools
        adapters: Dict of adapter_name → MCPToolAdapter instances
        server_configs: Dict of server_name → MCPServerConfig (for HITL resolution)
        global_hitl_required: Global MCP_HITL_REQUIRED setting
        reference_content: Dict of server_name → read_me content (for filtering)

    Returns:
        Total number of tools registered
    """
    from src.domains.agents.registry.catalogue import AgentManifest
    from src.domains.agents.registry.domain_taxonomy import (
        auto_generate_server_description,
        slugify_mcp_server_name,
    )

    _admin_mcp_domains.clear()
    reference_content = reference_content or {}

    if not adapters:
        logger.info("mcp_registration_no_tools")
        return 0

    registered_count = 0

    for server_name, tools in discovered_tools.items():
        server_config = server_configs.get(server_name)
        domain_slug = slugify_mcp_server_name(server_name)
        agent_name = f"{domain_slug}_agent"

        # Description: from config or auto-generated (shared helper)
        description = None
        if server_config and server_config.description:
            description = server_config.description
        if not description:
            description = auto_generate_server_description(
                [t.description for t in tools], server_name
            )

        # Store for domain routing (read by collect_all_mcp_domains)
        _admin_mcp_domains[domain_slug] = description

        # ADR-062: Iterative mode — delegate to ReAct sub-agent
        is_iterative = (
            server_config
            and getattr(server_config, "iterative_mode", False)
            and settings.mcp_react_enabled
        )

        if is_iterative:
            # Iterative mode: register individual tools in tool_registry only
            # (the ReAct agent needs them), but the CATALOGUE sees a single
            # per-server task tool (the planner delegates to the ReAct agent).
            for tool_item in tools:
                adapter_name = f"mcp_{server_name}_{tool_item.tool_name}"
                adapter = adapters.get(adapter_name)
                if adapter:
                    _register_tool_in_central_registry(adapter)
                    registered_count += 1

            # Per-server task tool name (unique to avoid manifest collision
            # when multiple servers have iterative_mode=true).
            # parallel_executor looks up this name in ToolRegistry.
            task_tool_name = f"mcp_{server_name}{MCP_ITERATIVE_TASK_SUFFIX}"

            # Register the generic mcp_server_task_tool under this per-server
            # name so parallel_executor can find it.
            _register_iterative_task_tool(task_tool_name)

            task_manifest = _build_mcp_react_manifest(
                react_tool_name=task_tool_name,
                agent_name=agent_name,
                server_name=server_name,
                description=description,
            )
            agent_manifest = AgentManifest(
                name=agent_name,
                description=description,
                tools=[task_tool_name],
            )
            registry.register_agent_manifest(agent_manifest)
            registry.register_tool_manifest(task_manifest)

            logger.info(
                "mcp_server_registered_iterative",
                server=server_name,
                domain=domain_slug,
                agent=agent_name,
                individual_tools=registered_count,
            )
            continue

        # Standard mode: register individual tools in catalogue + tool_registry
        server_tool_names = [
            f"mcp_{server_name}_{t.tool_name}"
            for t in tools
            if not is_app_only(t.app_visibility)
            and not (t.tool_name == MCP_REFERENCE_TOOL_NAME and reference_content.get(server_name))
        ]
        agent_manifest = AgentManifest(
            name=agent_name,
            description=description,
            tools=server_tool_names,
        )
        registry.register_agent_manifest(agent_manifest)

        # Register individual tools (manifest + instance + central registry)
        for tool_item in tools:
            # MCP Apps: app-only tools are iframe-only → skip LLM catalogue.
            if is_app_only(tool_item.app_visibility):
                logger.info(
                    "mcp_tool_app_only_skipped",
                    server=server_name,
                    tool_name=tool_item.tool_name,
                )
                continue

            # Skip read_me tool if its content was auto-fetched at discovery.
            # The content is injected into the planner prompt instead.
            if tool_item.tool_name == MCP_REFERENCE_TOOL_NAME and reference_content.get(
                server_name
            ):
                logger.debug(
                    "mcp_tool_reference_skipped",
                    server=server_name,
                    tool_name=MCP_REFERENCE_TOOL_NAME,
                )
                continue

            adapter_name = f"mcp_{server_name}_{tool_item.tool_name}"
            adapter = adapters.get(adapter_name)
            if not adapter:
                logger.warning(
                    "mcp_registration_adapter_missing",
                    adapter_name=adapter_name,
                )
                continue

            # Resolve HITL requirement
            hitl_required = global_hitl_required
            if server_config:
                hitl_required = resolve_hitl_requirement(server_config, global_hitl_required)

            # Create ToolManifest with per-server agent_name
            tool_manifest = _mcp_tool_to_manifest(
                discovered=tool_item,
                adapter_name=adapter_name,
                hitl_required=hitl_required,
                agent_name=agent_name,
            )

            # Register in AgentRegistry
            registry.register_tool_manifest(tool_manifest)
            registry.register_tool_instance(adapter_name, adapter)

            # Register in central tool_registry (for parallel_executor)
            _register_tool_in_central_registry(adapter)

            registered_count += 1

        logger.info(
            "mcp_server_registered",
            server=server_name,
            domain=domain_slug,
            agent=agent_name,
            tools_count=len(server_tool_names),
        )

    logger.info(
        "mcp_tools_registered",
        total=registered_count,
        servers=list(discovered_tools.keys()),
        domains=list(_admin_mcp_domains.keys()),
    )
    return registered_count


def _register_tool_in_central_registry(adapter: MCPToolAdapter) -> None:
    """Register the adapter in the central tool_registry (for parallel_executor)."""
    from src.domains.agents.tools.tool_registry import register_external_tool

    register_external_tool(adapter)


_MCP_DESCRIPTION_MAX_KEYWORDS = 10


def build_mcp_tool_manifest(
    adapter_name: str,
    agent_name: str,
    tool_name: str,
    description: str,
    input_schema: dict[str, Any],
    semantic_keywords: list[str],
    hitl_required: bool,
) -> ToolManifest:
    """Build a ToolManifest for an MCP tool (shared by admin and user MCP).

    Args:
        adapter_name: Prefixed tool name (e.g. "mcp_server_tool" or "mcp_user_xx_tool")
        agent_name: Agent for domain extraction (e.g. "mcp_google_flights_agent")
        tool_name: Raw MCP tool name
        description: Tool description
        input_schema: JSON Schema for the tool's input
        semantic_keywords: Keywords for semantic matching
        hitl_required: Whether HITL approval is required

    Returns:
        ToolManifest instance
    """
    from src.domains.agents.registry.catalogue import (
        CostProfile,
        DisplayMetadata,
        OutputFieldSchema,
        PermissionProfile,
        ToolManifest,
    )

    parameters = json_schema_to_parameters(
        properties=input_schema.get("properties", {}),
        required=input_schema.get("required", []),
    )

    return ToolManifest(
        name=adapter_name,
        agent=agent_name,
        description=description,
        parameters=parameters,
        outputs=[
            OutputFieldSchema(
                path="result",
                type="string",
                description="MCP tool response",
            )
        ],
        cost=CostProfile(
            est_tokens_in=100,
            est_tokens_out=500,
            est_latency_ms=5000,
        ),
        permissions=PermissionProfile(
            hitl_required=hitl_required,
            data_classification="INTERNAL",
        ),
        context_key=CONTEXT_DOMAIN_MCP,
        semantic_keywords=semantic_keywords,
        display=DisplayMetadata(
            emoji=MCP_DISPLAY_EMOJI,
            i18n_key="mcp_tool",
            category="tool",
        ),
        tool_category=None,  # Inferred from tool name (handles read/write MCP tools)
    )


def build_mcp_react_task_manifest(
    tool_name: str,
    agent_name: str,
    server_name: str,
    description: str,
    parameters: list[ParameterSchema],
    semantic_keywords: list[str],
    hitl_required: bool = False,
) -> ToolManifest:
    """Build a ToolManifest for an MCP iterative (ReAct) task tool.

    Shared factory for both admin and user MCP iterative mode manifests.
    When iterative_mode=true, the planner sees this single tool instead of
    individual MCP server tools. The tool delegates to a ReAct sub-agent.

    Args:
        tool_name: Registered tool name (e.g., "mcp_excalidraw_task").
        agent_name: Agent name for domain routing.
        server_name: Human-readable server name (for description text).
        description: Server description for LLM context.
        parameters: List of ParameterSchema for the tool signature.
        semantic_keywords: Keywords for semantic tool scoring.
        hitl_required: Whether HITL approval is required.

    Returns:
        ToolManifest instance for the task delegation tool.
    """
    from src.domains.agents.registry.catalogue import (
        CostProfile,
        DisplayMetadata,
        OutputFieldSchema,
        PermissionProfile,
        ToolManifest,
    )

    return ToolManifest(
        name=tool_name,
        agent=agent_name,
        description=(
            f"Execute a multi-step task on the '{server_name}' MCP server using "
            f"an iterative agent. The agent reads documentation first, then "
            f"executes tools in sequence. Server description: {description}"
        ),
        parameters=parameters,
        outputs=[
            OutputFieldSchema(
                path="result",
                type="string",
                description="Task result from the MCP server",
            )
        ],
        cost=CostProfile(
            est_tokens_in=5000,
            est_tokens_out=5000,
            est_latency_ms=15000,
        ),
        permissions=PermissionProfile(
            hitl_required=hitl_required,
            data_classification="INTERNAL",
        ),
        context_key=CONTEXT_DOMAIN_MCP,
        semantic_keywords=semantic_keywords,
        display=DisplayMetadata(
            emoji=MCP_DISPLAY_EMOJI,
            i18n_key="mcp_tool",
            category="tool",
        ),
        tool_category=None,
    )


def _build_mcp_react_manifest(
    react_tool_name: str,
    agent_name: str,
    server_name: str,
    description: str,
) -> ToolManifest:
    """Build a ToolManifest for an admin MCP iterative task tool.

    Thin wrapper over build_mcp_react_task_manifest() with admin-specific
    parameter schema (server_name + task).

    Args:
        react_tool_name: Registered tool name (e.g., "mcp_excalidraw_task").
        agent_name: Agent name for domain routing.
        server_name: MCP server name (injected as default parameter value).
        description: Server description for LLM context.

    Returns:
        ToolManifest instance for the task delegation tool.
    """
    from src.domains.agents.registry.catalogue import (
        ParameterConstraint,
        ParameterSchema,
    )

    return build_mcp_react_task_manifest(
        tool_name=react_tool_name,
        agent_name=agent_name,
        server_name=server_name,
        description=description,
        parameters=[
            ParameterSchema(
                name="server_name",
                type="string",
                required=True,
                description=f"MCP server name. MUST be exactly '{server_name}'.",
                constraints=[ParameterConstraint(kind="enum", value=[server_name])],
            ),
            ParameterSchema(
                name="task",
                type="string",
                required=True,
                description="Natural language description of the task to accomplish",
            ),
        ],
        semantic_keywords=[server_name, "task", "iterative", "react"],
        hitl_required=False,
    )


_STOP_WORDS = frozenset(
    {
        "with",
        "from",
        "this",
        "that",
        "have",
        "will",
        "been",
        "your",
        "their",
        "about",
        "into",
        "them",
        "then",
        "than",
        "when",
        "which",
        "does",
        "also",
    }
)


def build_semantic_keywords_from_description(description: str) -> list[str]:
    """Extract semantic keywords from an MCP tool description.

    Lowercases words, strips punctuation, filters short words and stop words.
    """
    words = []
    for w in description.lower().split():
        cleaned = w.strip(".,;:!?()[]\"'")
        if len(cleaned) > 3 and cleaned not in _STOP_WORDS:
            words.append(cleaned)
    return words[:_MCP_DESCRIPTION_MAX_KEYWORDS]


def _mcp_tool_to_manifest(
    discovered: MCPDiscoveredTool,
    adapter_name: str,
    hitl_required: bool,
    agent_name: str = AGENT_MCP,
) -> Any:
    """Convert an MCPDiscoveredTool to a ToolManifest (admin MCP).

    Args:
        agent_name: Per-server agent name for domain extraction.
            Defaults to AGENT_MCP for backward compatibility.
    """
    description = discovered.description
    input_schema = discovered.input_schema

    semantic_keywords = [
        discovered.server_name,
        discovered.tool_name,
        *build_semantic_keywords_from_description(description),
    ]

    return build_mcp_tool_manifest(
        adapter_name=adapter_name,
        agent_name=agent_name,
        tool_name=discovered.tool_name,
        description=description,
        input_schema=input_schema,
        semantic_keywords=semantic_keywords,
        hitl_required=hitl_required,
    )


def json_schema_to_parameters(
    properties: dict[str, Any],
    required: list[str],
) -> list[Any]:
    """Convert JSON Schema properties to ParameterSchema list.

    For complex types (array, object), preserves the full JSON Schema in the
    ``schema`` field so the LLM can see the internal structure (items, nested
    properties, enums, etc.) — critical for MCP tools with structured inputs.

    Args:
        properties: JSON Schema properties dict
        required: List of required field names

    Returns:
        List of ParameterSchema instances
    """
    from src.domains.agents.registry.catalogue import ParameterSchema

    parameters: list[ParameterSchema] = []

    type_map = {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "array": "array",
        "object": "object",
    }

    for name, spec in properties.items():
        param_type = type_map.get(spec.get("type", "string"), "string")
        # Preserve full schema for complex types so the LLM can see
        # internal structure (items, nested properties, enums).
        param_schema: dict[str, Any] | None = None
        if param_type in ("array", "object"):
            param_schema = _compact_json_schema(spec)
        parameters.append(
            ParameterSchema(
                name=name,
                type=param_type,
                required=name in required,
                description=spec.get("description", ""),
                schema=param_schema,
            )
        )

    return parameters


def _compact_json_schema(spec: dict[str, Any], depth: int = 0) -> dict[str, Any] | None:
    """Compact a JSON Schema for LLM prompt injection.

    Recursively strips verbose fields (title, $schema, additionalProperties,
    default) while preserving structural information the LLM needs to generate
    correct parameters: type, items, properties, required, enum, format.

    Limits recursion to 5 levels — deep enough for complex MCP schemas
    (e.g., Excalidraw elements: array → object → properties → object → properties)
    while still bounding worst-case expansion. MCP App usage is occasional,
    so the extra tokens are an acceptable trade-off for correct parameter generation.

    Args:
        spec: Raw JSON Schema for one parameter.
        depth: Current recursion depth (stops at 5).

    Returns:
        Compacted schema dict, or None if spec is trivial.
    """
    if depth > 5 or not isinstance(spec, dict):
        return None

    result: dict[str, Any] = {}
    param_type = spec.get("type")
    if param_type:
        result["type"] = param_type

    # Enums are critical for the LLM (e.g., element type: rectangle, ellipse, ...)
    if "enum" in spec:
        result["enum"] = spec["enum"]
    if "format" in spec:
        result["format"] = spec["format"]

    # Array items
    if param_type == "array" and "items" in spec:
        items_compact = _compact_json_schema(spec["items"], depth + 1)
        if items_compact:
            result["items"] = items_compact

    # Object properties
    if param_type == "object" and "properties" in spec:
        compact_props: dict[str, Any] = {}
        for prop_name, prop_spec in spec["properties"].items():
            prop_compact = _compact_json_schema(prop_spec, depth + 1)
            if prop_compact:
                compact_props[prop_name] = prop_compact
            else:
                compact_props[prop_name] = {"type": prop_spec.get("type", "string")}
        if compact_props:
            result["properties"] = compact_props
        if "required" in spec:
            result["required"] = spec["required"]

    # anyOf / oneOf (union types)
    for key in ("anyOf", "oneOf"):
        if key in spec:
            compacted = [_compact_json_schema(s, depth + 1) for s in spec[key]]
            compacted = [c for c in compacted if c]
            if compacted:
                result[key] = compacted

    return result if result else None


# Backward-compatible alias for imports using the old private name
_json_schema_to_parameters = json_schema_to_parameters
