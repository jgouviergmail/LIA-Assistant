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

from contextlib import suppress
from typing import TYPE_CHECKING

import structlog

from src.core.context import strip_hallucinated_mcp_suffix, user_mcp_tools_ctx
from src.domains.agents.tools.tool_registry import get_tool

logger = structlog.get_logger(__name__)

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from src.domains.agents.registry.catalogue import ToolManifest

__all__ = [
    "UNRESOLVED_TOOL_REASONS",
    "classify_unresolved_tool_call",
    "resolve_tool_instance",
    "resolve_tool_instance_named",
    "resolve_tool_manifest",
    "resolve_tool_manifest_named",
]

#: The only two verdicts :func:`classify_unresolved_tool_call` can return, and
#: therefore the whole label set of ``react_unknown_tool_calls_total``. Bounded
#: by construction: the tool NAME never becomes a label, because it comes from a
#: model and its cardinality is unbounded (ADR-256).
UNRESOLVED_TOOL_REASONS: tuple[str, ...] = ("not_selected", "unknown")


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
    with suppress(ToolManifestNotFound):
        manifest = registry.get_tool_manifest(name)
        if manifest is not None:
            return manifest, name

    # 2. Global agent registry — hallucinated suffix stripped (admin MCP).
    stripped = strip_hallucinated_mcp_suffix(name)
    if stripped:
        with suppress(ToolManifestNotFound):
            manifest = registry.get_tool_manifest(stripped)
            if manifest is not None:
                return manifest, stripped

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


def classify_unresolved_tool_call(name: object) -> str:
    """Say WHY a tool call found no bound tool, in terms that imply a fix.

    Two situations reach the same dead end and need opposite corrections:

    - ``not_selected`` — the tool exists (global registry or the per-request
      user MCP ContextVar) but was not bound to this turn. The ``max_tools`` cap
      or the per-request filtering dropped it, so the cap is too low for this
      deployment. Up to 896 tools can resolve against a cap of 100.
    - ``unknown`` — nothing of that name exists anywhere. The model invented it,
      which says the catalogue is presented badly rather than trimmed too hard.

    Reuses :func:`resolve_tool_instance` rather than re-implementing a lookup:
    the hallucinated-suffix stripping and the ContextVar fallback must give the
    same answer here as they do when the tool IS bound, or a tool the loop can
    actually run would be reported as invented.

    **Total by construction.** The name comes from a MODEL, and ``AIMessage``
    validates ``tool_calls`` at construction only — a ``None`` field survives a
    checkpoint round-trip, and a post-construction append bypasses the check
    entirely (both measured 2026-09-02). The branch that calls this used to
    write ``Tool 'None' not found.`` and move on; raising here would turn one
    malformed call into a dead turn, which is the opposite of what making the
    path observable was for. A name that is not a string was invented, so it
    reports ``unknown`` — never ``not_selected``, which would send an operator
    hunting for a tool-cap problem that does not exist.

    Args:
        name: Tool name as emitted by the model's tool call. Any value.

    Returns:
        One of :data:`UNRESOLVED_TOOL_REASONS`.
    """
    if not isinstance(name, str) or not name.strip():
        return "unknown"
    try:
        return "not_selected" if resolve_tool_instance(name) is not None else "unknown"
    except Exception:  # noqa: BLE001 - a classifier on a hot error path is total
        logger.debug("classify_unresolved_tool_call_failed", tool_name=name[:120])
        return "unknown"
