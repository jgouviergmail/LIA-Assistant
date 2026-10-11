"""Manifest-only resolution, independent of callable registration."""

from contextlib import suppress

from src.core.context import (
    request_tool_manifests_ctx,
    strip_hallucinated_mcp_suffix,
    user_mcp_tools_ctx,
)
from src.domains.agents.registry.agent_registry import get_global_registry
from src.domains.agents.registry.catalogue import ToolManifest, ToolManifestNotFound
from src.domains.agents.registry.request_tool_identity import offered_manifest_named


def resolve_tool_manifest_named(name: str) -> tuple[ToolManifest | None, str]:
    """Resolve a tool name to its ``ToolManifest`` AND its canonical name.

    A bound request snapshot is authoritative, including an explicitly empty
    catalogue. It admits iterative individuals by exact task/server identity.
    Outside a request, diagnostics retain global exact/suffix lookup followed
    by the user context. The returned name is always the canonical alias.

    Args:
        name: Tool name to resolve.

    Returns:
        ``(manifest, canonical_name)`` when found, or ``(None, name)`` otherwise.
    """
    offered = request_tool_manifests_ctx.get()
    if offered is not None:
        return offered_manifest_named(name, offered, user_mcp_tools_ctx.get())
    registry = get_global_registry()
    manifest: ToolManifest | None

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
