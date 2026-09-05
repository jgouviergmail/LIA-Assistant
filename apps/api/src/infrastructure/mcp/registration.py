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
from src.domains.agents.constants import AGENT_MCP
from src.domains.agents.registry.catalogue import POLICIES_REQUIRING_REASON
from src.infrastructure.mcp.json_schema import (
    DEFAULT_TYPE,
    as_property_spec,
    compact_schema,
    constraints_of,
    description_of,
    properties_of,
    required_of,
    resolve_property,
)
from src.infrastructure.mcp.schemas import MCPDiscoveredTool, MCPServerConfig
from src.infrastructure.mcp.security import resolve_hitl_requirement
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from src.infrastructure.mcp.utils import is_app_only
from src.infrastructure.observability.metrics_mcp import (
    mcp_tool_registration_failures_total,
)

if TYPE_CHECKING:
    from src.domains.agents.registry.agent_registry import AgentRegistry
    from src.domains.agents.registry.catalogue import (
        MutationPolicy,
        ParameterSchema,
        ToolCategory,
        ToolManifest,
    )
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


def _register_iterative_task_tool(task_tool_name: str, server_name: str, description: str) -> None:
    """Register the generic mcp_server_task_tool under a per-server name.

    Each iterative MCP server needs its own entry in ToolRegistry so the
    parallel_executor can find the tool by the per-server manifest name
    (e.g., ``mcp_excalidraw_task``). The actual tool function is the same
    ``mcp_server_task_tool`` — the registered name AND the model-facing
    description differ: ``bind_tools`` serializes the instance, so a
    name-only copy leaves a ReAct model with no idea what the server does
    (2026-09-02 incident, user-MCP variant).

    Args:
        task_tool_name: Per-server tool name (e.g., "mcp_excalidraw_task").
        server_name: Human-readable server name for the description.
        description: The server's domain description.
    """
    from src.domains.agents.tools.tool_registry import get_tool, register_external_tool

    # If already registered (e.g., module reload), skip
    if get_tool(task_tool_name):
        return

    try:
        from src.domains.agents.tools.mcp_react_tools import (
            iterative_task_tool_description,
            mcp_server_task_tool,
        )

        # Create a named copy of the tool with the per-server name.
        # BaseTool.name is a Pydantic field — model_copy creates a shallow copy.
        named_tool = mcp_server_task_tool.model_copy(
            update={
                "name": task_tool_name,
                "description": iterative_task_tool_description(server_name, description),
            }
        )
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


def record_tool_registration_failure(
    *,
    scope: str,
    server: str,
    tool_name: str,
    exc: BaseException,
    user_id: str | None = None,
) -> None:
    """Report an MCP tool that could not be registered — the only trace it leaves.

    Registration runs per tool and swallows per tool, by design: one unusable
    declaration must not cost its siblings. The price is silence — the tool is
    simply absent from the catalogue, the model never sees it, and the user is
    told the assistant cannot do the thing. Production ran 72 h in that state
    (2026-09-01), losing 30 of one server's 40 tools on every single turn, with
    only a warning nobody queries to show for it.

    Every registration path reports here so one panel and one log query cover
    all of them.

    Args:
        scope: Which registration path dropped the tool — ``"admin"``,
            ``"user_standard"`` or ``"user_iterative"``. A bounded vocabulary,
            hence a metric label.
        server: Identifies the server in the LOG only — a per-server metric
            label would add one series per user per server. Pass the configured
            name for admin servers and the id for user servers: a user-chosen
            server name is user content and does not belong at WARNING.
        tool_name: The dropped tool. Log only, same reason.
        exc: The exception that prevented the build. Its class names the
            ``error_type`` label and its own traceback is logged — reading the
            ambient ``sys.exc_info()`` instead would attach whichever exception
            happened to be in flight.
        user_id: Owner of a per-user server, so support can tell WHICH user
            lost the capability. Ids are allowed at this level; contents are not.
    """
    error_type = type(exc).__name__
    mcp_tool_registration_failures_total.labels(scope=scope, error_type=error_type).inc()
    logger.warning(
        "mcp_tool_registration_failed",
        scope=scope,
        server=server,
        tool_name=tool_name,
        error_type=error_type,
        user_id=user_id,
        exc_info=exc,
    )


def build_mcp_adapters(
    discovered_tools: dict[str, list[MCPDiscoveredTool]],
) -> dict[str, MCPToolAdapter]:
    """Build one adapter per discovered admin MCP tool, skipping the unbuildable.

    Parity with the per-user registration paths, which have caught per tool
    since F2.1. The admin loop used to live inline in ``init_mcp``, inside that
    step's single try/except, so ONE tool this codebase could not adapt aborted
    ``register_mcp_tools`` entirely: every admin MCP capability disappeared and
    a single ``mcp_initialization_failed`` line was the only trace. A tool lost
    is a capability the user no longer has — it must cost its own tool and
    nothing else.

    Args:
        discovered_tools: Dict of server_name → tools that server reported.

    Returns:
        Dict of adapter name → adapter for every tool that could be built.
    """
    adapters: dict[str, MCPToolAdapter] = {}
    for server_name, tools in discovered_tools.items():
        for tool in tools:
            try:
                adapter = MCPToolAdapter.from_mcp_tool(
                    server_name=server_name,
                    tool_name=tool.tool_name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    app_resource_uri=tool.app_resource_uri,
                )
            except Exception as exc:
                record_tool_registration_failure(
                    scope="admin",
                    server=server_name,
                    tool_name=tool.tool_name,
                    exc=exc,
                )
                continue
            adapters[adapter.name] = adapter
    return adapters


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
            _register_iterative_task_tool(task_tool_name, server_name, description)

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


def declared_tool_category(annotations: Any) -> ToolCategory | None:
    """Derive a catalogue category from a server behaviour hint — tightening only.

    The MCP specification is normative here:

        "For trust & safety and security, clients MUST consider tool
         annotations to be untrusted unless they come from trusted servers."

    So the asymmetry below is a requirement, not caution. A declared MUTATION is
    acted upon: the worst a lying server buys itself is one confirmation too
    many. A declared ``readOnlyHint: true`` is NOT, because a declared category
    WINS over the name heuristic in ``_declared_mutation_flag`` — believing it
    would remove the tool from the invalid-mutation safety net, from HITL scope
    detection and from the read-only requirement of the initiative phase, on the
    word of a third party.

    Returning None is therefore the safe answer, not a failure: it leaves
    ``MUTATION_TOOL_PATTERNS`` in charge exactly as before.

    What this buys, measured on one real server: none of ``cancel_subscription``,
    ``upgrade``, ``disconnect_institution`` or ``forget`` carries one of the nine
    mutation verbs, so every one of them is classified read-only by the name
    heuristic today.

    Args:
        annotations: Normalised hints from :func:`extract_tool_annotations`, of
            any shape.

    Returns:
        ``"delete"`` for a declared destructive tool, ``"update"`` for one
        declared as performing only additive updates, or None when the
        declaration says nothing this codebase may safely act on.
    """
    if not isinstance(annotations, dict):
        return None
    destructive = annotations.get("destructive_hint")
    read_only = annotations.get("read_only_hint")
    if destructive is True:
        return "delete"
    if read_only is False:
        # Spec: destructiveHint defaults to TRUE, and "If false, the tool
        # performs only additive updates" — both are mutations either way.
        return "update" if destructive is False else "delete"
    return None


def declares_destructive_tool(annotations: Any) -> bool:
    """Whether a server declares THIS tool destructive.

    Read where a per-tool decision has to be made from a per-SERVER setting. In
    iterative (ReAct) mode every tool of a server shares one HITL flag, so a
    user who turned confirmation off for a mostly read-only server would have
    its few destructive tools run unconfirmed too.

    Only a destructive declaration is acted upon, not a mere "not read-only":
    an additive update would otherwise put a prompt in front of every ordinary
    write. Tightening only, as :func:`declared_tool_category` explains.

    Args:
        annotations: Normalised hints from :func:`extract_tool_annotations`.

    Returns:
        True when the server declared the tool destructive.
    """
    return declared_tool_category(annotations) == "delete"


def derive_mcp_mutation_policy(hitl_required: bool, annotations: Any) -> MutationPolicy | None:
    """Derive the confirmation a third-party MCP tool owes (ADR-263).

    Never more permissive than what is known, and asymmetric for the same
    reason as :func:`declared_tool_category`: a declared mutation is acted upon,
    a declared read-only is not believed.

    - the server's HITL setting is the USER's decision and wins outright;
    - a declared destructive tool, or one declared "not read-only" with nothing
      said about destruction (the spec defaults ``destructiveHint`` to true),
      gets ``confirm``;
    - one explicitly declared "not read-only AND not destructive" — the spec's
      "performs only additive updates" — gets ``reversible``;
    - anything else yields None: no policy is derived, and the name heuristic
      keeps its job exactly as before.

    Args:
        hitl_required: Resolved per-server HITL requirement (per-server override
            or the global ``MCP_HITL_REQUIRED``).
        annotations: Normalised hints from :func:`extract_tool_annotations`, of
            any shape — a third party is not obliged to be well-formed.

    Returns:
        The derived policy, or None when nothing may safely be concluded.
    """
    if hitl_required:
        return "confirm"
    category = declared_tool_category(annotations)
    if category == "delete":
        return "confirm"
    if category == "update":
        return "reversible"
    return None


def derive_mcp_mutation_policy_reason(policy: MutationPolicy | None) -> str | None:
    """The written justification a derived exempting policy owes (ADR-263).

    ``reversible`` skips the confirmation, so the completeness doctrine demands
    a reason. For a third-party tool the reason is not ours to invent: it is
    what the SERVER declared, quoted as such.

    Args:
        policy: The derived policy, or None.

    Returns:
        The reason for a policy that requires one, else None.
    """
    if policy in POLICIES_REQUIRING_REASON:
        return (
            "The server declares this tool non-destructive and additive-only "
            "(MCP annotations); LIA never loosens that declaration."
        )
    return None


def build_mcp_tool_manifest(
    adapter_name: str,
    agent_name: str,
    tool_name: str,
    description: str,
    input_schema: dict[str, Any],
    semantic_keywords: list[str],
    hitl_required: bool,
    annotations: dict[str, Any] | None = None,
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
        annotations: Server-declared behaviour hints, read through
            :func:`declared_tool_category` — which believes a declared
            mutation and never a declared read-only claim.

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
        properties=properties_of(input_schema),
        required=sorted(required_of(input_schema)),
        root=input_schema,
    )

    # ADR-263: what this tool owes the user, derived from what the SERVER
    # declares (never asserted — a third party names its tools as it wants).
    _derived_policy = derive_mcp_mutation_policy(hitl_required, annotations)

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
        # No context_key on purpose: "mcps" was never a registered context
        # type (MCP result shapes are heterogeneous per server), so the wave
        # auto-save error-logged "Context type 'mcps' not registered" on
        # every MCP tool result once MCP-domain turns reached the pipeline.
        # CONTEXT_DOMAIN_MCP keeps its DISPLAY role (registry item domain,
        # result cards) — only the context-save claim was false.
        context_key=None,
        semantic_keywords=semantic_keywords,
        display=DisplayMetadata(
            emoji=MCP_DISPLAY_EMOJI,
            i18n_key="mcp_tool",
            category="tool",
        ),
        # A server-declared MUTATION is believed; everything else stays None so
        # the name heuristic keeps deciding, exactly as before.
        tool_category=declared_tool_category(annotations),
        mutation_policy=_derived_policy,
        mutation_policy_reason=derive_mcp_mutation_policy_reason(_derived_policy),
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
        # No context_key on purpose: "mcps" was never a registered context
        # type (MCP result shapes are heterogeneous per server), so the wave
        # auto-save error-logged "Context type 'mcps' not registered" on
        # every MCP tool result once MCP-domain turns reached the pipeline.
        # CONTEXT_DOMAIN_MCP keeps its DISPLAY role (registry item domain,
        # result cards) — only the context-save claim was false.
        context_key=None,
        semantic_keywords=semantic_keywords,
        display=DisplayMetadata(
            emoji=MCP_DISPLAY_EMOJI,
            i18n_key="mcp_tool",
            category="tool",
        ),
        tool_category=None,
        # ADR-263: the iterative tool opens a whole ReAct loop over the
        # server's toolbox. Its category stays None (the loop is not one
        # operation), but what it OWES follows the server's HITL setting: with
        # confirmation on, the loop asks before it starts; without, the tools it
        # calls carry their own derived policies.
        mutation_policy="confirm" if hitl_required else None,
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
        discovered: The tool as the server reported it, including the behaviour
            hints the manifest derives its category from.
        adapter_name: Prefixed tool name registered in the tool registry.
        hitl_required: Resolved HITL requirement for the owning server.
        agent_name: Per-server agent name for domain extraction.
            Defaults to AGENT_MCP for backward compatibility.

    Returns:
        The ToolManifest the planner catalogue exposes for this tool.
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
        annotations=discovered.annotations,
    )


def json_schema_to_parameters(
    properties: dict[str, Any],
    required: list[str],
    root: dict[str, Any] | None = None,
) -> list[Any]:
    """Convert JSON Schema properties to ParameterSchema list.

    For complex types (array, object), preserves the full JSON Schema in the
    ``schema`` field so the LLM can see the internal structure (items, nested
    properties, enums, etc.) — critical for MCP tools with structured inputs.

    Declarations are read through :func:`resolve_property`, the SAME reduction
    the LangChain adapter uses. Two readings of one declaration is exactly how
    the planner catalogue and the tool signature came to disagree about the
    same parameter.

    Args:
        properties: JSON Schema properties dict
        required: List of required field names
        root: The whole ``inputSchema``, so a property declared with ``$ref``
            can be resolved against its ``$defs``. Optional: a caller that has
            only the properties still gets everything else.

    Returns:
        List of ParameterSchema instances
    """
    from src.domains.agents.registry.catalogue import ParameterConstraint, ParameterSchema

    parameters: list[ParameterSchema] = []

    for name, raw_spec in properties.items():
        spec = as_property_spec(raw_spec)
        resolved = resolve_property(spec, root if root is not None else {})
        # An undecidable declaration still names a parameter the planner may
        # need to fill; "string" is the manifest's own historical fallback.
        param_type = resolved.name or DEFAULT_TYPE
        # Preserve full schema for complex types so the LLM can see
        # internal structure (items, nested properties, enums). The EFFECTIVE
        # spec is compacted, so a $ref'd or anyOf-wrapped object shows its real
        # properties instead of the wrapper.
        param_schema: dict[str, Any] | None = None
        if param_type in ("array", "object"):
            param_schema = compact_schema(resolved.spec)
        parameters.append(
            ParameterSchema(
                name=name,
                type=param_type,
                required=name in required,
                description=description_of(spec) or description_of(resolved.spec),
                # ADR-184: a bound the planner cannot see is a trap. These map
                # onto the catalogue's own vocabulary, so an MCP parameter gets
                # the same rendering, validation and numeric clamping a native
                # one has always had.
                constraints=[
                    ParameterConstraint(kind=kind, value=value)
                    for kind, value in constraints_of(resolved.spec).items()
                ],
                schema=param_schema,
            )
        )

    return parameters


# Backward-compatible aliases for imports using the old private names. The
# compaction moved to json_schema so the planner manifest and the tool
# signature share ONE description of a nested object.
_json_schema_to_parameters = json_schema_to_parameters
_compact_json_schema = compact_schema
