"""A routine may pre-approve MCP servers (spec 2026-10-29 D9) — the value and its seam.

A routine runs with nobody to ask, so the effect gate refuses its ``confirm``
calls (ADR-263): an MCP tool its owner wants a routine to use was out of reach.
The person may tick, in the routine's own form, the servers whose confirmations
a run may give itself — per SERVER, never one switch per routine, so an
instruction a third party slipped into the routine's input reaches only what
was ticked. The routine row carries the keys; its run publishes them here
around the stream (``mcp_preapproval_scope``); the effect gate reads them at one
point (``agents/effects/preapproval``).

Neutral on purpose: the routines domain builds the value, the agents domain
reads it, and neither imports the other here.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

#: How the effect register names an approval the routine's owner gave in advance.
ROUTINE_PREAPPROVAL_KIND = "routine_preapproval"


@dataclass(frozen=True)
class MCPPreapproval:
    """The MCP servers one routine run may confirm for itself.

    Attributes:
        servers: The server keys ticked in the routine's form — a personal
            server's id, an administrator server's key.
        routine_id: The routine, recorded as the approval's reference.
    """

    servers: frozenset[str]
    routine_id: str


_PREAPPROVAL: ContextVar[MCPPreapproval | None] = ContextVar("mcp_preapproval", default=None)


@contextmanager
def mcp_preapproval_scope(preapproval: MCPPreapproval | None) -> Iterator[None]:
    """Publish a routine run's pre-approval for the whole stream; always reset.

    Args:
        preapproval: The run's pre-approval, or None (nothing is pre-approved).
    """
    token = _PREAPPROVAL.set(preapproval)
    try:
        yield
    finally:
        _PREAPPROVAL.reset(token)


def current_mcp_preapproval() -> MCPPreapproval | None:
    """The pre-approval of the routine run in progress, None outside one."""
    return _PREAPPROVAL.get()


def stored_server_keys(value: object) -> list[str]:
    """A stored pre-approval, read forgivingly: its keys, never a failure.

    A key gone stale since it was stored (a server removed, switched off) is
    returned as stored — the run's offered catalogue no longer holds its tools,
    so it pre-approves nothing; a malformed value reads as no pre-approval.

    Args:
        value: The column's value (a JSON list of strings when well formed).

    Returns:
        The keys, in their stored order.
    """
    if not isinstance(value, list):
        return []
    return [key for key in value if isinstance(key, str) and key]
