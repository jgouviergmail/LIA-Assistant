"""Hide the tools of switched-off capabilities from the turn's catalogue.

Two layers protect a disabled capability: the routes REFUSE it (the enforcing
one), and the turn is never offered its tools (this one). The second layer is
not redundant — it keeps the assistant honest (no plan, no tool call that will
fail at execution), keeps the prompt small (every catalogue entry is tokens on
every model call), and keeps the switch legible in traces.

The exclusion is applied ONCE, where the request builds its catalogue
(``AgentService``): every reader of the turn's tools — the pipeline planner,
the ReAct loop, the router's ranking, the initiative — reads that snapshot.
It used to ride on the planner's own post-filter alone, so the ReAct loop
bound the tools of a capability an operator had switched off and ran them.

Direction of dependency: this module lives in ``domains/agents`` because it
walks the agent catalogue; it only READS the capability domain
(``disabled_agent_names``). The reverse would close a cycle.

Created: 2026-08-06 (live-demonstrator programme, lot 3)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from src.domains.agents.registry import AgentRegistry
    from src.domains.agents.registry.catalogue import ToolManifest
    from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue

logger = structlog.get_logger(__name__)


async def tools_hidden_by_capabilities(registry: AgentRegistry) -> set[str]:
    """Tool names no turn may be offered, given the disabled capabilities.

    Never raises: an unreachable settings store resolves to "nothing hidden".
    Degrading to the whole product beats amputating it on a transient failure,
    and the routes remain the layer that actually refuses.

    Args:
        registry: Agent registry, walked only when something IS disabled.

    Returns:
        The tool names to exclude; empty when every capability is on.
    """
    from src.domains.feature_switches import registry as capability_registry

    try:
        disabled = await capability_registry.disabled_capabilities()
        if not disabled:
            # The common case is free: no switch off, no catalogue walk.
            return set()
        # Two sources, unioned. A capability with an agent hides every manifest
        # that agent carries; one WITHOUT an agent names its tools directly
        # (delegation, the sandbox) — and the early return on « no disabled
        # agent » used to send the planner exactly those, for a capability an
        # operator had switched off.
        hidden = capability_registry.disabled_tool_names(disabled)
        agents = capability_registry.disabled_agent_names(disabled)
        hidden |= {
            manifest.name
            for agent in agents
            for manifest in registry.list_tool_manifests(agent=agent)
        }
        if not hidden:
            # Route- and service-enforced capabilities (speech, uploads) own no
            # catalogue entry; switching them off must not blank anything here.
            return set()
        logger.info(
            "capability_tools_hidden",
            capabilities=sorted(capability.value for capability in disabled),
            tool_count=len(hidden),
        )
        return hidden
    except Exception as exc:  # noqa: BLE001 — a switch never breaks a turn
        logger.error("capability_tool_filter_failed", error_type=type(exc).__name__)
        return set()


async def without_disabled_capability_tools(
    manifests: list[ToolManifest], registry: AgentRegistry
) -> list[ToolManifest]:
    """The turn's catalogue without the tools of a switched-off capability.

    Args:
        manifests: The catalogue the request is building.
        registry: Agent registry, walked only when something IS disabled.

    Returns:
        The same list when nothing is hidden, else the manifests that remain.
    """
    hidden = await tools_hidden_by_capabilities(registry)
    if not hidden:
        return manifests
    return [manifest for manifest in manifests if manifest.name not in hidden]


def apply_tool_exclusions(catalogue: FilteredCatalogue, excluded: set[str] | None) -> None:
    """Apply the user's own exclusions before any native or generative planner."""
    if not excluded:
        return
    original_count = catalogue.tool_count
    catalogue.tools = [tool for tool in catalogue.tools if tool["name"] not in excluded]
    catalogue.tool_count = len(catalogue.tools)
    if catalogue.tool_count < original_count:
        logger.info(
            "smart_planner_tools_excluded",
            excluded=list(excluded),
            original_count=original_count,
            filtered_count=catalogue.tool_count,
        )
