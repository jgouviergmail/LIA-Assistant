"""The individual tools of an administrator's iterative MCP servers (spec D1, 2026-10-29).

An iterative server offers the planner ONE task tool; its individual tools are
reached through that task — by its sub-agent, by the ReAct loop that expands
it, and by the replay of a confirmed draft. Their manifests therefore never
enter the agent registry, whose every manifest is catalogue: the planner would
otherwise see each of them beside the task.

A personal server keeps its individuals on the request
(``UserMCPToolsContext.reactive_tool_manifests``); an administrator's server is
process-wide, so its individuals live here — written once, at MCP startup, and
read only through ``request_tool_identity._reactive_manifest``, which admits
one when the turn OFFERS its task. Until this store existed they had no
manifest at all: the effect gate read no policy for them and a confirmed draft
could not find them again (probes H3 and P1, 2026-10-29).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.agents.registry.catalogue import ToolManifest

_REACTIVE_MANIFESTS: dict[str, ToolManifest] = {}


def register_reactive_manifest(manifest: ToolManifest) -> None:
    """Keep an administrator iterative server's individual, out of the catalogue.

    Args:
        manifest: The individual's manifest, built like a standard tool's.

    Raises:
        ValueError: The manifest does not name an administrator server — a
            personal individual belongs to its request, never to the process.
    """
    if manifest.mcp_origin != "admin" or manifest.mcp_server_key is None:
        raise ValueError("Only an administrator MCP server's individual belongs to this store")
    _REACTIVE_MANIFESTS[manifest.name] = manifest


def reactive_manifest(name: str) -> ToolManifest | None:
    """The individual registered under ``name``, admitted or not by any turn."""
    return _REACTIVE_MANIFESTS.get(name)


def reactive_manifests_of(server_key: str) -> list[ToolManifest]:
    """Every individual of one administrator server, in registration order.

    Read by the ReAct loop, which binds them in place of — and beside — the
    server's task (spec D8); each call is still admitted at the gate only while
    the turn offers that task (``request_tool_identity``).
    """
    return [m for m in _REACTIVE_MANIFESTS.values() if m.mcp_server_key == server_key]


def reset_reactive_manifests() -> None:
    """Forget every individual (a new MCP registration, and tests)."""
    _REACTIVE_MANIFESTS.clear()
