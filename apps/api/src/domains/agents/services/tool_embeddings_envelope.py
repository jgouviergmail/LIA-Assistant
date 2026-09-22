"""The envelope a persisted per-server vector cache travels in: its model, then its tools.

``user_mcp_servers.tool_embeddings_cache`` is written once, when a person tests
their MCP server, and read on every turn to rank that server's tools (ADR-293).
It used to be a flat dict of vectors with no word about the model that produced
them. When the embedder changed width, the rows stayed: measured 2026-09-20, two
dev servers and two production servers (DeepWiki, GitMCP) carried 384-dimension
vectors against 1 536-dimension queries, ``cosine_similarity`` answered 0 for
every one of their tools — 163 warnings per turn on dev, 20 tools invisible to
the ranking — and nothing refreshed them, because the only writer is a click in
the settings.

A cache therefore names its model (``embedding_model``, the same key the native
catalogue's disk cache is hashed on) beside its vectors (``tools``). A reader
that finds another model, or the legacy flat shape, treats the cache as STALE
and says which: the context builder then recomputes it from the tools it has
just fetched and persists the new envelope, so the row heals on the person's
next turn rather than on their next visit to the settings.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from src.core.config import settings

#: Key of the model that wrote the vectors.
MODEL_KEY: Final = "embedding_model"
#: Key of the vectors themselves, by raw MCP tool name.
TOOLS_KEY: Final = "tools"

StaleReason = Literal["legacy_shape", "model_changed"]


def embedding_model_key() -> str:
    """The model AND the width the selector asks it for — one string, one implementation.

    The same model serves several widths on request (Gemini: 384 or 1 536), so
    the name alone does not identify the vectors it produced.
    """
    return f"{settings.memory_embedding_model}:{settings.memory_embedding_dimensions}"


def wrap_server_cache(tools: dict[str, Any]) -> dict[str, Any]:
    """The envelope to persist: the current model key beside the vectors."""
    return {MODEL_KEY: embedding_model_key(), TOOLS_KEY: tools}


def read_server_cache(cache: Any) -> tuple[dict[str, Any], StaleReason | None]:
    """The vectors of a persisted cache when this model wrote them, else why not.

    Args:
        cache: The column's value — the envelope, the legacy flat dict, or nothing.

    Returns:
        ``(tools, stale)`` — the vectors by raw tool name and ``None``, or an
        empty dict and the reason the cache cannot be trusted. An empty cache
        is empty, not stale: there is nothing to recompute from it.
    """
    if not isinstance(cache, dict) or not cache:
        return {}, None
    if MODEL_KEY not in cache or TOOLS_KEY not in cache:
        return {}, "legacy_shape"
    if cache[MODEL_KEY] != embedding_model_key():
        return {}, "model_changed"
    tools = cache[TOOLS_KEY]
    return (tools if isinstance(tools, dict) else {}), None
