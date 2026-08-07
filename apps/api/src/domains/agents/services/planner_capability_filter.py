"""Hide the tools of switched-off capabilities from the planner.

Two layers protect a disabled capability: the routes REFUSE it (the enforcing
one), and the planner is never offered its tools (this one). The second layer
is not redundant — it keeps the assistant honest (no plan that will fail at
execution), keeps the prompt small (every catalogue entry is tokens on every
planning call), and keeps the switch legible in traces.

The exclusion rides on ``exclude_tools``, the post-filter that already exists
for sub-agent rejection (F6). One mechanism rather than two.

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

logger = structlog.get_logger(__name__)


async def tools_hidden_by_capabilities(registry: AgentRegistry) -> set[str]:
    """Tool names the planner must not see, given the disabled capabilities.

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
        agents = capability_registry.disabled_agent_names(disabled)
        if not agents:
            # Route-enforced capabilities (speech, uploads) own no catalogue
            # entry; switching them off must not blank anything here.
            return set()
        hidden = {
            manifest.name
            for agent in agents
            for manifest in registry.list_tool_manifests(agent=agent)
        }
        logger.info(
            "planner_capability_tools_hidden",
            capabilities=sorted(capability.value for capability in disabled),
            tool_count=len(hidden),
        )
        return hidden
    except Exception as exc:  # noqa: BLE001 — a switch never breaks planning
        logger.error("planner_capability_filter_failed", error_type=type(exc).__name__)
        return set()


async def merge_capability_exclusions(
    registry: AgentRegistry, exclude_tools: set[str] | None
) -> set[str] | None:
    """Merge capability exclusions into the caller's own exclusion set.

    A user rejection (F6) and an operator switch are independent reasons to
    drop a tool: both survive the merge.

    Args:
        registry: Agent registry.
        exclude_tools: Exclusions the caller already computed, if any.

    Returns:
        The union, or ``None`` when there is nothing to exclude at all — the
        caller's fast path checks truthiness, and an empty set would walk the
        whole tool list for nothing.
    """
    hidden = await tools_hidden_by_capabilities(registry)
    merged = set(exclude_tools or set()) | hidden
    return merged or None
