"""The tools one turn may be offered — built once, read by every execution mode.

The request snapshot (``request_tool_manifests_ctx``) is the authority on which
tools exist for a turn: the pipeline planner, the ReAct loop, the router's
ranking and the initiative all read it, and a delegated sub-agent holds
nothing it does not offer. Every reason a tool is withheld is
therefore applied HERE, in one place, so no mode can offer what another
withholds:

1. the global catalogue, minus the administrator's MCP servers the person
   disabled, plus the person's own MCP tools (``build_request_tool_manifests``);
2. minus the tools of a capability an administrator switched off — those its
   spec names (``CapabilitySpec.agents`` / ``tools``); the ReAct loop used to
   bind them while only the pipeline planner dropped them. A switch that closes
   its routes alone (workboard, peers, MCP, skills) names none;
3. minus the tools no connector of the account would run (RC2.1);
4. minus the application operations the account may not use.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.domains.agents.registry import AgentRegistry
    from src.domains.agents.registry.catalogue import ToolManifest


async def build_turn_catalogue(
    registry: AgentRegistry,
    user_id: UUID,
    active_connector_types: Collection[str] | None,
) -> list[ToolManifest]:
    """The tools this turn may be offered, in catalogue order.

    Must be called AFTER the per-request MCP contexts are set
    (``admin_mcp_disabled_ctx``, ``user_mcp_tools_ctx``), like
    ``build_request_tool_manifests`` it starts from.

    Args:
        registry: The global agent registry.
        user_id: The account the turn serves.
        active_connector_types: The account's active connector types.

    Returns:
        The manifests offered to every reader of the turn.
    """
    # Resolved at call time, as the request path always resolved them: the
    # stream's characterization harness substitutes them on their own modules.
    from src.core.context import build_request_tool_manifests
    from src.domains.agents.application.discovery import filter_application_manifests
    from src.domains.agents.services.planner_capability_filter import (
        without_disabled_capability_tools,
    )
    from src.domains.agents.tools.connector_requirements import without_unconnected_tools

    offered = await without_disabled_capability_tools(
        build_request_tool_manifests(registry), registry
    )
    return await filter_application_manifests(
        without_unconnected_tools(offered, active_connector_types), user_id
    )
