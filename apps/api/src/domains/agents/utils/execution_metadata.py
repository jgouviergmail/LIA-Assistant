"""
Execution Metadata Helper - Extract display metadata for SSE events.

This module provides utilities to extract display metadata from existing registries
(ToolManifest, AgentManifest) for progressive UI rendering of execution steps.

Architecture:
- Leverages existing catalogue system (single source of truth)
- No new registries or configuration files needed
- Zero-configuration when adding new agents (if display metadata provided in manifest)
- Fallback to sensible defaults if display metadata missing

Usage:
    from src.domains.agents.utils.execution_metadata import get_tool_display_metadata

    # In streaming code, when tool is executed:
    metadata = get_tool_display_metadata("search_contacts_tool")
    if metadata and metadata.visible:
        yield {
            "type": "execution_step",
            "category": metadata.category,
            "emoji": metadata.emoji,
            "i18n_key": metadata.i18n_key,
            "step_name": "search_contacts_tool",
        }
"""

from dataclasses import dataclass
from typing import Literal

from src.core.field_names import FIELD_STATUS
from src.domains.agents.registry.catalogue import DisplayMetadata
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Default Display Metadata (Fallbacks)
# ============================================================================


@dataclass(frozen=True)
class DefaultDisplayMetadata:
    """Default display metadata for nodes without explicit configuration."""

    emoji: str
    i18n_key: str
    visible: bool = True
    category: Literal["system", "agent", "tool", "context"] = "system"


# Default metadata for LangGraph nodes (system-level operations)
DEFAULT_NODE_METADATA: dict[str, DefaultDisplayMetadata] = {
    # Router node
    "router": DefaultDisplayMetadata(
        emoji="🧭",
        i18n_key="router_decision",
        visible=True,
        category="system",
    ),
    # Planner node
    "planner": DefaultDisplayMetadata(
        emoji="📋",
        i18n_key="planner_generation",
        visible=True,
        category="system",
    ),
    # Semantic validator node (Phase 2 OPTIMPLAN - Issue #60)
    "semantic_validator": DefaultDisplayMetadata(
        emoji="🔎",
        i18n_key="semantic_validation",
        visible=True,
        category="system",
    ),
    # Clarification node (Phase 2 OPTIMPLAN - Issue #60)
    "clarification": DefaultDisplayMetadata(
        emoji="❓",
        i18n_key="clarification_request",
        visible=True,
        category="system",
    ),
    # Approval gate node
    "approval_gate": DefaultDisplayMetadata(
        emoji="✅",
        i18n_key="approval_gate",
        visible=True,
        category="system",
    ),
    # Task orchestrator node
    "task_orchestrator": DefaultDisplayMetadata(
        emoji="⚡",
        i18n_key="task_orchestration",
        visible=True,
        category="system",
    ),
    # Response node
    "response": DefaultDisplayMetadata(
        emoji="💬",
        i18n_key="response_generation",
        visible=True,
        category="system",
    ),
}


# ============================================================================
# Public API
# ============================================================================


def get_tool_display_metadata(tool_name: str) -> DisplayMetadata | None:
    """
    Retrieve display metadata for a tool from the catalogue.

    This function queries the existing catalogue system to extract display metadata
    without requiring any additional configuration files or registries.

    Args:
        tool_name: Name of the tool (e.g., "search_contacts_tool")

    Returns:
        DisplayMetadata if found and configured, None otherwise

    Example:
        >>> metadata = get_tool_display_metadata("search_contacts_tool")
        >>> if metadata:
        ...     print(f"{metadata.emoji} {metadata.i18n_key}")
        🔍 search_contacts
    """
    try:
        # Get global registry instance
        from src.domains.agents.registry.agent_registry import get_global_registry

        registry = get_global_registry()
        tool_manifest = registry.get_tool_manifest(tool_name)

        if tool_manifest and tool_manifest.display:
            logger.debug(
                "tool_display_metadata_found",
                tool_name=tool_name,
                emoji=tool_manifest.display.emoji,
                i18n_key=tool_manifest.display.i18n_key,
                visible=tool_manifest.display.visible,
                category=tool_manifest.display.category,
            )
            return tool_manifest.display

        # No display metadata configured for this tool
        logger.debug(
            "tool_display_metadata_not_configured",
            tool_name=tool_name,
        )
        return None

    except Exception as e:
        # Graceful degradation - don't break execution if metadata retrieval fails
        logger.warning(
            "tool_display_metadata_retrieval_failed",
            tool_name=tool_name,
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def get_node_display_metadata(node_name: str) -> DefaultDisplayMetadata | None:
    """
    Retrieve display metadata for a LangGraph node.

    System nodes (router, planner, orchestrator, response) have default metadata.
    Agent nodes could be extended in the future to support AgentManifest.display.

    Args:
        node_name: Name of the LangGraph node (e.g., "router", "planner")

    Returns:
        DefaultDisplayMetadata if configured, None otherwise

    Example:
        >>> metadata = get_node_display_metadata("router")
        >>> if metadata:
        ...     print(f"{metadata.emoji} {metadata.i18n_key}")
        🧭 router_decision
    """
    # Check default node metadata first
    if node_name in DEFAULT_NODE_METADATA:
        metadata = DEFAULT_NODE_METADATA[node_name]
        logger.debug(
            "node_display_metadata_found",
            node_name=node_name,
            emoji=metadata.emoji,
            i18n_key=metadata.i18n_key,
            visible=metadata.visible,
            category=metadata.category,
        )
        return metadata

    # Future: Could check AgentManifest.display for agent nodes
    # For now, return None for unknown nodes
    logger.debug(
        "node_display_metadata_not_found",
        node_name=node_name,
    )
    return None


def should_emit_execution_step(
    step_type: Literal["tool", "node"],
    step_name: str,
) -> bool:
    """
    Determine if an execution step should be emitted as SSE event.

    Checks if display metadata exists and visibility is enabled.

    Args:
        step_type: Type of step ("tool" or "node")
        step_name: Name of the tool or node

    Returns:
        True if step should be emitted, False otherwise

    Example:
        >>> if should_emit_execution_step("tool", "search_contacts_tool"):
        ...     # Emit SSE event
        ...     pass
    """
    if step_type == "tool":
        metadata = get_tool_display_metadata(step_name)
        return metadata is not None and metadata.visible
    elif step_type == "node":
        metadata = get_node_display_metadata(step_name)
        return metadata is not None and metadata.visible
    else:
        logger.warning(
            "invalid_step_type",
            step_type=step_type,
            step_name=step_name,
        )
        return False


# ============================================================================
# SSE Event Builder
# ============================================================================


def build_execution_step_event(
    step_type: Literal["tool", "node"],
    step_name: str,
    status: Literal["started", "completed", "failed"] = "started",
    additional_data: dict | None = None,
) -> dict | None:
    """
    Build a complete SSE event payload for an execution step.

    This is a convenience function that combines metadata retrieval with event building.

    Args:
        step_type: Type of step ("tool" or "node")
        step_name: Name of the tool or node
        status: Status of the step ("started", "completed", "failed")
        additional_data: Optional additional data to include in event

    Returns:
        SSE event dict if step should be emitted, None otherwise

    Example:
        >>> event = build_execution_step_event(
        ...     step_type="tool",
        ...     step_name="search_contacts_tool",
        ...     status="started",
        ... )
        >>> if event:
        ...     yield json.dumps(event)
        {
            "type": "execution_step",
            "step_type": "tool",
            "step_name": "search_contacts_tool",
            FIELD_STATUS: "started",
            "emoji": "🔍",
            "i18n_key": "search_contacts",
            "category": "tool"
        }
    """
    # Check if step should be emitted
    if not should_emit_execution_step(step_type, step_name):
        return None

    # Get metadata
    if step_type == "tool":
        metadata = get_tool_display_metadata(step_name)
    else:  # node
        metadata = get_node_display_metadata(step_name)

    if not metadata:
        return None

    # Build event payload
    event = {
        "type": "execution_step",
        "step_type": step_type,
        "step_name": step_name,
        FIELD_STATUS: status,
        "emoji": metadata.emoji,
        "i18n_key": metadata.i18n_key,
        "category": metadata.category,
    }

    # Merge additional data if provided
    if additional_data:
        event.update(additional_data)

    return event
