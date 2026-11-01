"""Where an approval given in advance becomes an approval (spec 2026-10-29 D9, 2026-10-30 D6).

Two approvals given before the call, read at ONE point of the effect gate:

- the person's « never ask » for one personal MCP tool whose declaration owes a
  confirmation: its offered manifest is ``approved_in_advance``, and the call runs
  under an APPROVED scope filed as ``standing_choice`` with the server as its
  reference — attended or not, with no routine pre-approval needed;
- a routine whose form ticked MCP servers (``domains/shared/mcp_preapproval``): a
  ``confirm`` call of a ticked server runs under a scope filed as
  ``routine_preapproval`` with the routine as its reference, and the ReAct loop does
  not refuse that call before the gate sees it.

Neither is ever filed as the person's ``tool_confirmation``, which they did not give
for this call. Anything else keeps today's refusal.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from src.domains.agents.effects.scope import EffectScope
from src.domains.shared.mcp_preapproval import (
    ROUTINE_PREAPPROVAL_KIND,
    MCPPreapproval,
    current_mcp_preapproval,
)

if TYPE_CHECKING:
    from src.domains.agents.registry.catalogue import ToolManifest

#: How the effect register names the person's « never ask » for one tool.
STANDING_CHOICE_KIND = "standing_choice"


def _own_mcp_manifest(tool_name: str) -> ToolManifest | None:
    """The tool's OWN offered manifest when it is an MCP server's (exact name only).

    A name that resolves solely through a stripped suffix belongs to another tool.
    """
    from src.domains.agents.registry.manifest_resolution import resolve_tool_manifest_named

    manifest, canonical = resolve_tool_manifest_named(tool_name)
    if manifest is None or canonical != tool_name or manifest.mcp_origin is None:
        return None
    return manifest


def preapproval_for(tool_name: str) -> MCPPreapproval | None:
    """The running routine's pre-approval when it covers this tool's server.

    The tool's OWN offered manifest decides (exact name only): a name that
    resolves solely through a stripped suffix belongs to another tool.

    Args:
        tool_name: The registered tool name.

    Returns:
        The pre-approval, or None outside a routine run, for a tool that is
        not an MCP server's, or for a server the routine did not tick.
    """
    preapproval = current_mcp_preapproval()
    if preapproval is None or not preapproval.servers:
        return None
    manifest = _own_mcp_manifest(tool_name)
    if manifest is None:
        return None
    return preapproval if manifest.mcp_server_key in preapproval.servers else None


def is_preapproved(tool_name: str) -> bool:
    """Whether the running routine pre-approved this MCP tool's server."""
    return preapproval_for(tool_name) is not None


def preapproved_scope(
    tool_name: str, policy: str | None, scope: EffectScope | None
) -> EffectScope | None:
    """The scope a call runs under once the approvals given in advance are read.

    Args:
        tool_name: The tool being called.
        policy: Its declared ``mutation_policy``.
        scope: The authority the executor published; never invented when absent.

    Returns:
        An approved copy for an unapproved ``confirm`` call the person approved in
        advance (their « never ask ») or of a server the routine ticked; the scope
        unchanged otherwise.
    """
    if policy != "confirm" or scope is None or scope.approved:
        return scope
    manifest = _own_mcp_manifest(tool_name)
    if manifest is not None and manifest.approved_in_advance:
        return replace(
            scope,
            approved=True,
            approval_kind=STANDING_CHOICE_KIND,
            approval_ref=manifest.mcp_server_key,
        )
    preapproval = preapproval_for(tool_name)
    if preapproval is None:
        return scope
    return replace(
        scope,
        approved=True,
        approval_kind=ROUTINE_PREAPPROVAL_KIND,
        approval_ref=preapproval.routine_id,
    )
