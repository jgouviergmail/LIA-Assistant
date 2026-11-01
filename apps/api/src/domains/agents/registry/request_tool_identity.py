"""Resolve only a request's offered contract and its exact callable owner."""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from src.core.context import strip_hallucinated_mcp_suffix
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.reactive_manifests import reactive_manifest

if TYPE_CHECKING:
    from src.core.context import UserMCPToolsContext


def _reactive_manifest(
    name: str, manifests: Sequence[ToolManifest], ctx: UserMCPToolsContext | None
) -> ToolManifest | None:
    """An iterative server's individual, admitted only while the turn offers its task.

    A personal individual lives on the request, an administrator's in the
    process-wide store; each is admitted by a task of its OWN origin and server.
    """
    personal = ctx.reactive_tool_manifests.get(name) if ctx is not None else None
    for candidate, origin in ((personal, "user"), (reactive_manifest(name), "admin")):
        if candidate is None or candidate.mcp_origin != origin or candidate.mcp_server_key is None:
            continue
        if any(
            task.delegates_execution
            and task.mcp_origin == origin
            and task.mcp_server_key == candidate.mcp_server_key
            for task in manifests
        ):
            return candidate
    return None


def offered_manifest_named(
    name: str, manifests: Sequence[ToolManifest], ctx: UserMCPToolsContext | None
) -> tuple[ToolManifest | None, str]:
    """An ambiguous alias is unavailable; stripping a suffix never changes its owner."""
    stripped = strip_hallucinated_mcp_suffix(name)
    for canonical in (name, stripped):
        if canonical is None:
            continue
        matches = [manifest for manifest in manifests if manifest.name == canonical]
        if matches:
            return (matches[0] if len(matches) == 1 else None), canonical
        reactive = _reactive_manifest(canonical, manifests, ctx)
        if reactive is not None:
            return reactive, canonical
    return None, name


def callable_matches_manifest(manifest: ToolManifest, tool: object) -> bool:
    """Provider identity comes from the adapter or server-owned task metadata."""
    if manifest.mcp_origin is None:
        return True
    identifier: object = getattr(tool, "server_id", None)
    if isinstance(identifier, UUID):
        return manifest.mcp_origin == "user" and str(identifier) == manifest.mcp_server_key
    server: object = getattr(tool, "server_name", None)
    if isinstance(server, str):
        return manifest.mcp_origin == "admin" and server == manifest.mcp_server_key
    metadata: object = getattr(tool, "metadata", None)
    return bool(
        isinstance(metadata, Mapping)
        and metadata.get("mcp_origin") == manifest.mcp_origin
        and metadata.get("mcp_server_key") == manifest.mcp_server_key
        and manifest.mcp_server_key is not None
    )
