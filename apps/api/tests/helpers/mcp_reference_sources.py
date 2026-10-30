"""Personal MCP reference sources for planner and collector tests (M1b, spec §5.5b).

A source is what a turn's registration leaves for the pipeline planner: the
server's identity, its exact domain, its pool entry (the per-worker cache of
``read_me``) and the persisted snapshot that describes its catalogue. These
builders give a test a source in a known state without a discovery.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx
from src.infrastructure.mcp.reference_content import ReferenceSource
from src.infrastructure.mcp.user_pool import PoolEntry

USER_ID = UUID("00000000-0000-4000-8000-0000000000aa")


def reference_source(
    domain: str,
    *,
    reference: str | None = None,
    fetched_at: datetime | None = None,
    has_reference_tool: bool = True,
    instructions: str | None = None,
    timeout_seconds: int = 30,
) -> ReferenceSource:
    """A standard server's source, its ``read_me`` held by the entry when given.

    Args:
        domain: The server's exact domain slug.
        reference: A reference already fetched on this worker.
        fetched_at: When it was fetched (required with ``reference``).
        has_reference_tool: The server exposes ``read_me``.
        instructions: The handshake's instructions.
        timeout_seconds: The server's own tool timeout.

    Returns:
        The source.
    """
    entry = PoolEntry(
        user_id=USER_ID,
        server_id=uuid4(),
        last_used=0.0,
        has_reference_tool=has_reference_tool,
        server_instructions=instructions,
        reference_content=reference,
        reference_fetched_at=fetched_at,
        reference_attempted_at=fetched_at,
    )
    return ReferenceSource(
        user_id=USER_ID,
        server_id=entry.server_id,
        domain=domain,
        timeout_seconds=timeout_seconds,
        entry=entry,
        snapshot=None,
    )


@contextmanager
def reference_context(sources: Mapping[str, ReferenceSource]) -> Iterator[UserMCPToolsContext]:
    """Publish a request context holding these sources (server name → source)."""
    ctx = UserMCPToolsContext(server_reference_sources=dict(sources))
    token = user_mcp_tools_ctx.set(ctx)
    try:
        yield ctx
    finally:
        user_mcp_tools_ctx.reset(token)
