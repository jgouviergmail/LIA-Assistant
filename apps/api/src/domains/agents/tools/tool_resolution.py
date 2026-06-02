"""Shared tool-instance resolution (global registry + user MCP ContextVar).

Both the pipeline executor and the ReAct loop need to turn a tool *name* into a
callable ``BaseTool`` instance. Two storage locations exist:

1. The process-global ``tool_registry`` — native tools and **admin** MCP tools
   (registered once at startup).
2. The per-request ``user_mcp_tools_ctx`` ContextVar — **user** MCP tools, which
   are per-user and dynamic, so they must NOT pollute the shared global registry.

The pipeline's ``parallel_executor`` already resolves across both locations. The
ReAct path historically consulted only the global registry, so user MCP tools
were silently dropped (``manifest_without_registered_tool``). This module
centralizes the two-step lookup so both execution modes behave identically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.context import strip_hallucinated_mcp_suffix, user_mcp_tools_ctx
from src.domains.agents.tools.tool_registry import get_tool

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from src.domains.agents.registry.catalogue import ToolManifest

__all__ = [
    "resolve_tool_instance",
    "resolve_tool_instance_named",
    "resolve_tool_manifest",
    "resolve_tool_manifest_named",
]


def resolve_tool_instance_named(name: str) -> tuple[BaseTool | None, str]:
    """Resolve a tool name to its instance AND its canonical name.

    Single source of truth for tool resolution across the pipeline executor and
    the ReAct loop. Resolution order:
        1. Global ``tool_registry`` — exact (native tools + admin MCP).
        2. Global ``tool_registry`` — with the LLM-hallucinated suffix stripped
           (e.g. ``..._tool`` → ``...``), for admin MCP tools.
        3. Per-request ``user_mcp_tools_ctx`` — exact instance-key match (covers
           iterative individual tools that have no manifest), then fuzzy resolve.

    The canonical name lets callers that track the tool name (e.g. the pipeline
    mutating ``step.tool_name`` for display/registry correlation) stay in sync
    when a hallucinated suffix was stripped.

    Args:
        name: Tool name as emitted by the manifest or the LLM tool call.

    Returns:
        ``(instance, canonical_name)`` when found, or ``(None, name)`` otherwise.
    """
    # 1. Global registry — exact (native tools + admin MCP).
    tool = get_tool(name)
    if tool is not None:
        return tool, name

    # 2. Global registry — hallucinated suffix stripped (admin MCP).
    stripped = strip_hallucinated_mcp_suffix(name)
    if stripped:
        tool = get_tool(stripped)
        if tool is not None:
            return tool, stripped

    # 3. User MCP ContextVar — per-request instances keyed by adapter name.
    user_ctx = user_mcp_tools_ctx.get()
    if user_ctx is not None:
        instance = user_ctx.tool_instances.get(name)
        if instance is not None:
            return instance, name
        resolved = user_ctx.resolve_tool_name(name)
        if resolved and resolved in user_ctx.tool_instances:
            return user_ctx.tool_instances[resolved], resolved

    return None, name


def resolve_tool_instance(name: str) -> BaseTool | None:
    """Resolve a tool name to a ``BaseTool`` instance.

    Thin wrapper over :func:`resolve_tool_instance_named` for callers that do not
    need the canonical name. See that function for the resolution order.

    Args:
        name: Tool name as emitted by the manifest or the LLM tool call.

    Returns:
        The resolved ``BaseTool`` instance, or ``None`` if not found.
    """
    return resolve_tool_instance_named(name)[0]


def resolve_tool_manifest_named(name: str) -> tuple[ToolManifest | None, str]:
    """Resolve a tool name to its ``ToolManifest`` AND its canonical name.

    Manifest counterpart of :func:`resolve_tool_instance_named`. Resolution order:
        1. Global ``AgentRegistry`` — exact (native tools + admin MCP).
        2. Global ``AgentRegistry`` — with the hallucinated suffix stripped.
        3. Per-request ``user_mcp_tools_ctx`` — fuzzy resolve (the returned
           manifest's ``name`` is the canonical name).

    Args:
        name: Tool name to resolve.

    Returns:
        ``(manifest, canonical_name)`` when found, or ``(None, name)`` otherwise.
    """
    from src.domains.agents.registry.agent_registry import (
        ToolManifestNotFound,
        get_global_registry,
    )

    registry = get_global_registry()

    # 1. Global agent registry — exact.
    try:
        manifest = registry.get_tool_manifest(name)
        if manifest is not None:
            return manifest, name
    except ToolManifestNotFound:
        pass

    # 2. Global agent registry — hallucinated suffix stripped (admin MCP).
    stripped = strip_hallucinated_mcp_suffix(name)
    if stripped:
        try:
            manifest = registry.get_tool_manifest(stripped)
            if manifest is not None:
                return manifest, stripped
        except ToolManifestNotFound:
            pass

    # 3. User MCP ContextVar — per-request manifests (exact + fuzzy resolve).
    user_ctx = user_mcp_tools_ctx.get()
    if user_ctx is not None:
        manifest = user_ctx.resolve_tool_manifest(name)
        if manifest is not None:
            return manifest, manifest.name

    return None, name


def resolve_tool_manifest(name: str) -> ToolManifest | None:
    """Resolve a tool name to its ``ToolManifest``.

    Thin wrapper over :func:`resolve_tool_manifest_named` for callers that do not
    need the canonical name. The global registry does not know user MCP tools, so
    consumers that look up a manifest only there (e.g. display-metadata) would
    raise ``ToolManifestNotFound``; this resolver adds the ContextVar fallback.

    Args:
        name: Tool name to resolve.

    Returns:
        The resolved ``ToolManifest``, or ``None`` if not found.
    """
    return resolve_tool_manifest_named(name)[0]
