"""Context variables for cross-cutting concerns.

This module provides ContextVar instances for implicit propagation of
context through the async call stack without explicit parameter passing.

Usage:
    from src.core.context import current_tracker

    # Set the tracker (done by TrackingContext.__aenter__)
    token = current_tracker.set(tracker_instance)

    # Access from anywhere in the async call stack
    tracker = current_tracker.get()
    if tracker is not None:
        tracker.record_google_api_call(...)

    # Clear when done (done by TrackingContext.__aexit__)
    current_tracker.reset(token)

Author: Claude Code (Opus 4.5)
Date: 2026-02-04
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from src.domains.agents.registry.agent_registry import AgentRegistry
    from src.domains.agents.registry.catalogue import ToolManifest
    from src.domains.chat.service import TrackingContext

# Context variable to access current tracker from anywhere in async call stack.
# This enables implicit propagation of tracking context to Google API clients
# without modifying their constructors or method signatures.
current_tracker: ContextVar["TrackingContext | None"] = ContextVar("current_tracker", default=None)

# Context variables for panic mode state per request
# FIX 2026-02-06: Replaces instance variables on singletons for thread-safety
# SmartCatalogueService AND SmartPlannerService are BOTH singletons,
# so instance attributes are shared across concurrent requests.
panic_mode_used: ContextVar[bool] = ContextVar("panic_mode_used", default=False)
panic_mode_attempted: ContextVar[bool] = ContextVar("panic_mode_attempted", default=False)

# F6: Exclude sub-agent delegation from planner prompt during replan after user rejection.
# When True, _build_sub_agents_section() returns empty string so the LLM prompt
# does not encourage delegation. Reset to False after plan generation.
exclude_sub_agents_from_prompt: ContextVar[bool] = ContextVar(
    "exclude_sub_agents_from_prompt", default=False
)


# ---------------------------------------------------------------------------
# MCP tool name resolution (shared by admin + user MCP — evolution F2.1/F2.5)
# ---------------------------------------------------------------------------
# The planner LLM sometimes appends '_tool' or '_action' to MCP tool names
# by pattern-matching with native tools (e.g. "unified_web_search_tool").
# This module-level helper is the single source of truth for suffix stripping,
# reused by UserMCPToolsContext and the execution fallback chain
# (parallel_executor, validator, approval_gate_node).
# ---------------------------------------------------------------------------

_MCP_HALLUCINATED_SUFFIXES: tuple[str, ...] = ("_tool", "_action")


def strip_hallucinated_mcp_suffix(name: str) -> str | None:
    """Strip LLM-hallucinated suffixes from MCP tool names.

    Returns the stripped name if a known suffix was found, None otherwise.
    """
    for suffix in _MCP_HALLUCINATED_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


# ---------------------------------------------------------------------------
# Per-user MCP tools context (evolution F2.1)
# ---------------------------------------------------------------------------
# Injected by user_mcp_session() context manager for each chat request.
# Provides per-request isolation of user MCP tools without modifying
# global singletons (AgentRegistry, tool_registry).
# ---------------------------------------------------------------------------


@dataclass
class UserMCPToolsContext:
    """Per-request context holding user MCP tool manifests, instances, and metadata."""

    tool_manifests: list["ToolManifest"] = field(default_factory=list)
    tool_instances: dict[str, "BaseTool"] = field(default_factory=dict)
    # Server-level domain descriptions for query_analyzer enrichment
    server_descriptions: dict[str, str] = field(default_factory=dict)
    # Per-server domain slugs: server_name → domain slug (e.g., "HuggingFace Hub" → "mcp_huggingface_hub")
    server_domains: dict[str, str] = field(default_factory=dict)
    # Pre-computed E5 embeddings for semantic tool scoring (keyed by adapter name)
    tool_embeddings: dict[str, dict] = field(default_factory=dict)
    # Auto-fetched read_me content per server (for planner prompt injection)
    server_reference_content: dict[str, str] = field(default_factory=dict)
    # Original MCP input_schema per tool (adapter_name → JSON Schema dict)
    # Used by MCPDirectCallStrategy for native function calling with full schema fidelity
    tool_input_schemas: dict[str, dict] = field(default_factory=dict)

    def resolve_tool_name(self, name: str) -> str | None:
        """Resolve a tool name with fuzzy matching for LLM-hallucinated suffixes.

        The planner LLM sometimes appends '_tool' to MCP tool names
        by pattern-matching with native tools like 'unified_web_search_tool'.

        Returns the corrected tool name if found, or None.
        """
        # Exact match
        for m in self.tool_manifests:
            if m.name == name:
                return name
        # Fuzzy: strip common LLM-hallucinated suffixes
        stripped = strip_hallucinated_mcp_suffix(name)
        if stripped:
            for m in self.tool_manifests:
                if m.name == stripped:
                    return stripped
        return None

    def resolve_tool_manifest(self, name: str) -> "ToolManifest | None":
        """Resolve a tool name and return the matching ToolManifest.

        Combines resolve_tool_name + manifest lookup in a single call.
        Used by pipeline nodes to avoid duplicating the fallback pattern.
        """
        resolved = self.resolve_tool_name(name)
        if resolved:
            for m in self.tool_manifests:
                if m.name == resolved:
                    return m
        return None


user_mcp_tools_ctx: ContextVar[UserMCPToolsContext | None] = ContextVar(
    "user_mcp_tools_ctx", default=None
)

# Admin MCP per-user disabled servers (evolution F2.5)
# Set per-request in AgentService._stream_with_new_services() from User.admin_mcp_disabled_servers.
# Read by collect_all_mcp_domains() in query_analyzer to filter out disabled admin servers.
admin_mcp_disabled_ctx: ContextVar[set[str] | None] = ContextVar(
    "admin_mcp_disabled_ctx", default=None
)

# Active skills for the current user (positive set).
# Set per-request in AgentService._stream_with_new_services() via SkillPreferenceService.
# Read by build_skills_catalog(), response_node, and skill_bypass to filter by inclusion.
active_skills_ctx: ContextVar[set[str] | None] = ContextVar("active_skills_ctx", default=None)


# ---------------------------------------------------------------------------
# Per-request filtered tool manifests (centralized catalogue).
# Built ONCE at request start from:
#   1. Global registry manifests (admin + native tools)
#   2. Minus admin MCP servers disabled by user (admin_mcp_disabled_ctx)
#   3. Plus user MCP tools (user_mcp_tools_ctx)
# All consumers read via get_request_tool_manifests() instead of
# registry.list_tool_manifests() + manual filtering.
# ---------------------------------------------------------------------------
request_tool_manifests_ctx: ContextVar[list["ToolManifest"] | None] = ContextVar(
    "request_tool_manifests_ctx", default=None
)


def build_request_tool_manifests(
    registry: "AgentRegistry",
) -> list["ToolManifest"]:
    """Build the per-request available tool manifests list.

    Single source of truth for tool availability. Combines global registry
    with user-specific filtering (admin MCP disabled, user MCP enabled).

    Must be called AFTER admin_mcp_disabled_ctx and user_mcp_tools_ctx are set.

    Args:
        registry: Global AgentRegistry singleton.

    Returns:
        Filtered and merged manifest list.
    """
    from src.domains.agents.registry.domain_taxonomy import (
        filter_admin_mcp_disabled_manifests,
    )

    # 1. Global registry - admin MCP disabled by user
    manifests = filter_admin_mcp_disabled_manifests(registry.list_tool_manifests())

    # 2. + user MCP tools (already filtered by is_enabled + status at setup time)
    user_ctx = user_mcp_tools_ctx.get()
    if user_ctx and user_ctx.tool_manifests:
        manifests = list(manifests) + user_ctx.tool_manifests

    return manifests


def get_request_tool_manifests() -> list["ToolManifest"]:
    """Get the per-request available tool manifests.

    Returns the pre-built list from request_tool_manifests_ctx.
    Falls back to empty list with warning if called outside request lifecycle.

    Returns:
        List of available ToolManifest for the current request.
    """
    from src.infrastructure.observability.logging import get_logger

    result = request_tool_manifests_ctx.get()
    if result is None:
        _logger = get_logger(__name__)
        _logger.warning(
            "request_tool_manifests_ctx_not_set",
            message="Accessed outside request lifecycle, returning empty list",
        )
        return []
    return result
