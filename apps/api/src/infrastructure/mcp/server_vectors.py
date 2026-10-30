"""A personal server's tool vectors for a turn: reused per tool, embedded only when missing.

Moved out of ``user_context`` (spec 2026-10-21 M2) so the per-server preparation
child and the background revalidation read the same implementation (M6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from src.domains.user_mcp.models import UserMCPServer

logger = structlog.get_logger(__name__)


async def usable_tool_embeddings(
    server: UserMCPServer, tools: list[dict[str, Any]]
) -> dict[str, Any]:
    """The server's vectors in their compact form, reused per tool, parsed once per worker.

    The per-worker :class:`~src.domains.agents.services.tool_vectors.ServerVectorCache`
    answers first, keyed by the server, the embedding model and an ORDER-free
    fingerprint of the tools just discovered. On a miss the persisted envelope
    is read ALONE and each stored vector is reused while its identity — the
    hash of the exact texts it embeds — still matches its tool; only the other
    tools are embedded, in one call (spec 2026-10-21 M6: a reordered or
    one-tool-edited listing used to recompute every vector, up to 16.4 s on a
    turn). Never while a spending ceiling refuses the account (E8): the turn is
    then served the vectors it already has.

    Best-effort in both halves: a tool left without a vector stays offered,
    unranked (it binds through its family's coverage), and nothing fails the
    request. The new envelope is a new dict, written in a short transaction of
    its own once the embeddings are computed (ADR-304). Only a COMPLETE set is
    cached for the worker, so a tool still missing is retried on the next turn.

    Args:
        server: The ``UserMCPServer`` row, read in a session already closed.
        tools: The tools the pool just discovered on the server.

    Returns:
        Vectors by raw MCP tool name — arrays, possibly empty.
    """
    from src.domains.agents.services.tool_embeddings_envelope import (
        catalogue_fingerprint,
        embedding_model_key,
        reusable_vectors,
    )
    from src.domains.agents.services.tool_vectors import (
        compact_tool_vectors,
        get_server_vector_cache,
    )
    from src.domains.user_mcp.repository import UserMCPServerRepository
    from src.infrastructure.database.session import get_db_context

    cache = get_server_vector_cache()
    key = (
        str(server.id),
        embedding_model_key(),
        catalogue_fingerprint(tools, server_name=server.name),
    )
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        async with get_db_context() as db:
            envelope = await UserMCPServerRepository(db).get_tool_embeddings_cache(server.id)
    except Exception as exc:
        # The envelope used to travel with the row; read alone, its failure must
        # cost the turn its ranking of this server's tools, never the tools.
        logger.warning(
            "user_mcp_tool_embeddings_read_failed",
            server_id=str(server.id),
            error_type=type(exc).__name__,
        )
        return {}
    vectors, missing = reusable_vectors(envelope, tools, server_name=server.name)
    if missing:
        vectors = await _embed_missing(server, tools, vectors, missing)
    compact = compact_tool_vectors(vectors)
    if all(str(tool.get("name", "")) in vectors for tool in tools):
        cache.put(key, compact)
    return compact


async def _embed_missing(
    server: UserMCPServer,
    tools: list[dict[str, Any]],
    kept: dict[str, Any],
    missing: list[dict[str, Any]],
) -> dict[str, Any]:
    """Embed the tools without a usable vector, persist the merged envelope, return the merge.

    Args:
        server: The server row.
        tools: Every tool it lists now.
        kept: The stored vectors still valid.
        missing: The tools to embed.

    Returns:
        The kept vectors plus the new ones; the kept ones alone when the account
        may not spend or the computation failed.
    """
    from src.domains.agents.services.tool_embeddings_envelope import wrap_server_cache
    from src.domains.usage_limits.enforcement import spend_blocked
    from src.domains.user_mcp.repository import UserMCPServerRepository
    from src.infrastructure.database.session import get_db_context

    try:
        # Asked inside the guard: a ceiling that cannot be read costs the turn
        # its ranking of these tools, never the tools (best-effort, as below).
        if await spend_blocked(server.user_id):
            logger.info(
                "user_mcp_tool_embeddings_skipped_spend_blocked",
                server_id=str(server.id),
                missing=len(missing),
            )
            return kept
        from src.domains.agents.services.tool_selector import compute_tool_embeddings

        fresh = await compute_tool_embeddings(tool_metadata=missing, server_name=server.name)
        if not fresh:
            return kept
        merged = {**kept, **fresh}
        async with get_db_context() as db:
            repo = UserMCPServerRepository(db)
            row = await repo.get_by_id(server.id)
            if row is not None:
                envelope = wrap_server_cache(merged, tool_metadata=tools, server_name=server.name)
                await repo.update(row, {"tool_embeddings_cache": envelope})
        logger.info(
            "user_mcp_tool_embeddings_refreshed",
            server_id=str(server.id),
            embedded=len(fresh),
            reused=len(kept),
        )
        return merged
    except Exception as exc:
        logger.warning(
            "user_mcp_tool_embeddings_refresh_failed",
            server_id=str(server.id),
            missing=len(missing),
            error_type=type(exc).__name__,
        )
        return kept


__all__ = ["usable_tool_embeddings"]
