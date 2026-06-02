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

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.constants import MCP_ITERATIVE_TASK_SUFFIX, MCP_USER_TOOL_NAME_PREFIX
from src.core.context import get_request_tool_manifests, user_mcp_tools_ctx
from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper
from src.domains.agents.tools.tool_resolution import resolve_tool_instance

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

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
        # Use per-request manifests (filtered by active connectors + MCP settings)
        # Same source of truth as pipeline: build_request_tool_manifests()
        available_manifests = get_request_tool_manifests()

        wrapped_tools: list[ReactToolWrapper] = []
        hitl_map: dict[str, bool] = {}
        skipped: list[str] = []

        for manifest in available_manifests:
            tool_name = manifest.name

            # ReAct already IS an iterative loop, so the per-server "task tool"
            # indirection (designed for the single-shot pipeline planner) only
            # hides the descriptive individual tools from the LLM, which then
            # falls back to generic web search. For iterative USER MCP servers,
            # expose the individual tools directly so the model can recognise and
            # pick them by description — EXCEPT MCP App servers, which keep the
            # task tool (they need the dedicated MCP-app prompt + model).
            expanded = self._expand_iterative_user_mcp(manifest)
            if expanded is not None:
                for ind_name, ind_tool, ind_hitl in expanded:
                    wrapped_tools.append(
                        ReactToolWrapper(original_tool=ind_tool, hitl_required=ind_hitl)
                    )
                    hitl_map[ind_name] = ind_hitl
                continue

            # Resolve across the global registry AND the per-request user MCP
            # ContextVar — same two-step lookup as the pipeline executor, so user
            # MCP tools (instances live only in the ContextVar) are not dropped.
            base_tool = resolve_tool_instance(tool_name)
            if base_tool is None:
                skipped.append(tool_name)
                continue

            # Read HITL straight from the in-hand manifest. The agent_registry
            # does not know user MCP tools, so looking it up there would silently
            # disable approval gates on user MCP mutation tools.
            permissions = getattr(manifest, "permissions", None)
            hitl_required = bool(permissions and permissions.hitl_required)

            wrapper = ReactToolWrapper(
                original_tool=base_tool,
                hitl_required=hitl_required,
            )
            wrapped_tools.append(wrapper)
            hitl_map[tool_name] = hitl_required

        # Cap at max_tools. Measured on the RESOLVED tool count, not the manifest
        # count: iterative expansion can emit more tools than there are manifests
        # (one task manifest → N individual tools), so the cap must be evaluated
        # (and reported) on what is actually bound.
        max_tools = settings.react_agent_max_tools
        resolved_count = len(wrapped_tools)
        if resolved_count > max_tools:
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
            resolved_count=resolved_count,
            tool_count=len(wrapped_tools),
            hitl_count=sum(1 for v in hitl_map.values() if v),
            capped=resolved_count > max_tools,
        )

        return wrapped_tools, hitl_map

    @staticmethod
    def _expand_iterative_user_mcp(
        manifest: Any,
    ) -> list[tuple[str, BaseTool, bool]] | None:
        """Expand an iterative user MCP task manifest into its individual tools.

        Iterative user MCP servers expose a single opaque ``mcp_user_{id}_task``
        manifest to the planner, while their individual tools live in the
        per-request ``user_mcp_tools_ctx``. In ReAct mode the individual tools are
        surfaced directly (their descriptions let the LLM pick them), except for
        MCP App servers, which keep the task tool for the dedicated app workflow.

        Args:
            manifest: The candidate tool manifest being processed by ``select``.

        Returns:
            A list of ``(tool_name, instance, hitl_required)`` for the server's
            individual tools, or ``None`` when expansion is disabled by feature
            flag, when the manifest is not an iterative user MCP task tool, when
            the server is an MCP App, or when no individual tools are available
            (all of which fall back to normal single-manifest resolution).
        """
        if not settings.react_mcp_expand_iterative_enabled:
            return None

        tool_name = getattr(manifest, "name", "")
        if not (
            tool_name.startswith(f"{MCP_USER_TOOL_NAME_PREFIX}_")
            and tool_name.endswith(MCP_ITERATIVE_TASK_SUFFIX)
        ):
            return None

        user_ctx = user_mcp_tools_ctx.get()
        if user_ctx is None:
            return None

        # Strip the "_task" suffix to get the per-server instance-name prefix.
        prefix = tool_name[: -len(MCP_ITERATIVE_TASK_SUFFIX)]
        individual: list[tuple[str, BaseTool]] = []
        is_app_server = False
        for name, instance in user_ctx.tool_instances.items():
            if name == tool_name or not name.startswith(f"{prefix}_"):
                continue
            if getattr(instance, "app_resource_uri", None):
                is_app_server = True
            individual.append((name, instance))

        # No hidden individual tools, or an MCP App server → keep the task tool
        # (return None routes back to the normal single-manifest resolution).
        if not individual or is_app_server:
            return None

        permissions = getattr(manifest, "permissions", None)
        server_hitl = bool(permissions and permissions.hitl_required)
        return [(name, instance, server_hitl) for name, instance in individual]
