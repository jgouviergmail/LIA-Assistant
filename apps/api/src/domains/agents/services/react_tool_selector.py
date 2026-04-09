"""Tool selection and wrapping for ReAct execution mode.

Provides all AVAILABLE tools to the ReAct agent (filtered by active connectors,
capped by max_tools). Unlike the pipeline Planner which further filters by
detected domains, the ReAct agent gets all available tools and decides
autonomously which to use.

Filtering chain (same as pipeline):
1. Global registry tools
2. Minus admin-disabled MCP servers (per user)
3. Plus user-enabled MCP tools
4. Only tools whose manifest is in the per-request available set
   (respects active connectors)

Also builds a hitl_map (tool_name → bool) for the execute_tools node to know
which tools require HITL approval via interrupt().
"""

from typing import Any

import structlog

from src.core.config import settings
from src.core.context import get_request_tool_manifests
from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from src.domains.agents.registry.agent_registry import (
    ToolManifestNotFound,
    get_global_registry,
)
from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper

logger = structlog.get_logger(__name__)


class ReactToolSelector:
    """Select and wrap tools for ReAct execution based on QueryIntelligence.

    Two-step process:
    1. SmartCatalogueService → filtered ToolManifest names (by domains + intent)
    2. ToolRegistry lookup → actual BaseTool instances → ReactToolWrapper wrapping
    """

    def select(
        self,
        intelligence: QueryIntelligence | None,
    ) -> tuple[list[ReactToolWrapper], dict[str, bool]]:
        """Select all AVAILABLE tools for the ReAct agent.

        Uses the same per-request manifest filtering as the pipeline (respects
        active connectors, admin-disabled MCP servers, user MCP tools), then
        maps manifest names to actual BaseTool instances from the registry.

        The ReAct agent gets ALL available tools (not domain-filtered like the
        Planner) so it can autonomously decide which to use.

        Args:
            intelligence: Query intelligence (used for logging, not filtering).

        Returns:
            Tuple of (wrapped_tools, hitl_map).
            - wrapped_tools: List of ReactToolWrapper instances.
            - hitl_map: Dict mapping tool_name → hitl_required (for execute_tools HITL logic).
        """
        from src.domains.agents.tools.tool_registry import get_tool

        # Use per-request manifests (filtered by active connectors + MCP settings)
        # Same source of truth as pipeline: build_request_tool_manifests()
        available_manifests = get_request_tool_manifests()

        agent_registry = get_global_registry()

        wrapped_tools: list[ReactToolWrapper] = []
        hitl_map: dict[str, bool] = {}
        skipped: list[str] = []

        for manifest in available_manifests:
            tool_name = manifest.name
            base_tool = get_tool(tool_name)
            if base_tool is None:
                skipped.append(tool_name)
                continue

            hitl_required = self._get_hitl_required(agent_registry, tool_name)

            wrapper = ReactToolWrapper(
                original_tool=base_tool,
                hitl_required=hitl_required,
            )
            wrapped_tools.append(wrapper)
            hitl_map[tool_name] = hitl_required

        # Cap at max_tools
        max_tools = settings.react_agent_max_tools
        if len(wrapped_tools) > max_tools:
            wrapped_tools = wrapped_tools[:max_tools]
            hitl_map = {k: v for k, v in hitl_map.items() if k in {t.name for t in wrapped_tools}}

        if skipped:
            logger.debug(
                "react_tool_selector_skipped",
                skipped=skipped,
                reason="manifest_without_registered_tool",
            )

        logger.info(
            "react_tool_selector_complete",
            available_manifests=len(available_manifests),
            tool_count=len(wrapped_tools),
            hitl_count=sum(1 for v in hitl_map.values() if v),
            capped=len(available_manifests) > max_tools,
        )

        return wrapped_tools, hitl_map

    @staticmethod
    def _get_hitl_required(agent_registry: Any, tool_name: str) -> bool:
        """Check if a tool requires HITL approval from its manifest.

        Args:
            agent_registry: The global AgentRegistry instance.
            tool_name: Tool name to look up.

        Returns:
            True if the tool's manifest has hitl_required=True.
        """
        try:
            manifest = agent_registry.get_tool_manifest(tool_name)
            if manifest.permissions:
                return bool(manifest.permissions.hitl_required)
        except ToolManifestNotFound:
            pass
        return False
