"""
HITL (Human-in-the-Loop) configuration utilities.

Provides functions to determine which tools require approval before execution.
Uses tool manifests from the registry as the single source of truth.

Migration Note:
    - Legacy: Used settings.tool_approval_required (pattern matching with fnmatch)
    - Current: Uses registry.requires_tool_approval() (manifest-driven)
    - Benefit: Single source of truth, no duplication, declarative configuration

Architecture:
    Tool Definition → ToolManifest (permissions.hitl_required) → Registry → Runtime Check

    The tool's manifest is the authoritative source for approval requirements.
    Settings only control global enable/disable via tool_approval_enabled.

Best Practice (LangGraph v1.0):
    HITL approval should be declarative (manifest) not imperative (settings).
    This follows the principle of "configuration as code" where tool metadata
    lives with the tool definition, not in environment configuration.
"""

from src.domains.agents.registry import get_global_registry
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def requires_approval(tool_name: str) -> bool:
    """
    Check if a tool requires user approval before execution.

    Queries the tool's manifest in the registry for permissions.hitl_required.
    This is the authoritative source for HITL approval requirements.

    Args:
        tool_name: Name of the tool to check.

    Returns:
        True if tool requires approval, False otherwise.

    Example:
        >>> requires_approval("search_contacts_tool")  # True (from manifest)
        >>> requires_approval("get_context_state")     # False
        >>> requires_approval("unknown_tool")          # False (defensive)

    Note:
        - Tool approval is always enabled (no kill switch)
        - Per-tool requirement: manifest.permissions.hitl_required
        - If manifest not found: defaults to False (defensive)
        - Thread-safe: Uses registry catalogue lock

    Best Practice (LangGraph v1.0):
        HITL approval should be declarative (manifest) not imperative (settings).
        This follows the principle of "configuration as code" where tool
        metadata lives with the tool definition, not in environment config.

    Migration Note:
        Legacy approach used pattern matching:
            for pattern in settings.tool_approval_required:
                if fnmatch(tool_name, pattern): return True

        Current approach queries manifest:
            registry.requires_tool_approval(tool_name)

        Benefits:
        - Single source of truth (manifest)
        - No duplication between manifest and settings
        - Type-safe (PermissionProfile schema)
        - Automatic for new tools (just set hitl_required in manifest)
    """
    # Query registry for manifest-driven approval requirement
    registry = get_global_registry()
    requires_hitl = registry.requires_tool_approval(tool_name)

    if requires_hitl:
        logger.debug(
            "tool_requires_approval",
            tool_name=tool_name,
            source="manifest.permissions.hitl_required",
        )

    return requires_hitl


def get_approval_config(tool_name: str) -> dict[str, list[str]]:
    """
    Get approval configuration for a specific tool.

    Returns the allowed decisions for this tool (approve, edit, reject).

    Args:
        tool_name: Name of the tool.

    Returns:
        Dict with "allowed_decisions" key containing list of allowed actions.

    Example:
        >>> get_approval_config("search_contacts_tool")
        {"allowed_decisions": ["approve", "edit", "reject"]}

    Note:
        All tools currently support the same decisions.
        Future enhancement: Per-tool allowed decisions from manifest:
            manifest.permissions.allowed_decisions = ["approve", "reject"]  # No edit
    """
    # All tools support the same decisions for now
    # Future: Extract from manifest.permissions.allowed_decisions
    return {"allowed_decisions": ["approve", "edit", "reject"]}
