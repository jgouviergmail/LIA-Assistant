"""The envelope a persisted per-server vector cache travels in: its model, then its tools.

``user_mcp_servers.tool_embeddings_cache`` is written once, when a person tests
their MCP server, and read to rank that server's tools (ADR-293) — once per
catalogue and per worker since the ADR-283 amendment of 2026-10-12, the compact
form living in ``tool_vectors.ServerVectorCache`` between turns.
It used to be a flat dict of vectors with no word about the model that produced
them. When the embedder changed width, the rows stayed: measured 2026-09-20, two
dev servers and two production servers (DeepWiki, GitMCP) carried 384-dimension
vectors against 1 536-dimension queries, ``cosine_similarity`` answered 0 for
every one of their tools — 163 warnings per turn on dev, 20 tools invisible to
the ranking — and nothing refreshed them, because the only writer is a click in
the settings.

A cache therefore names its model (``embedding_model``, the same key the native
catalogue's disk cache is hashed on) beside its vectors (``tools``) and, since
2026-10-28, each vector's IDENTITY — the hash of the exact texts it embeds. The
catalogue used to be fingerprinted as an ordered whole: measured on production,
a reordered or one-tool-edited listing threw every vector away (31
recomputations, up to 16.4 s on a turn, spec 2026-10-21 §0ter H5). A reader now
reuses each vector whose identity still holds and embeds only the rest; a row
of another model, of a legacy shape, or with no envelope heals on the person's
next turn rather than on their next visit to the settings.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

from src.core.config import settings
from src.infrastructure.mcp.catalogue_fingerprint import canonical_fingerprint

#: Key of the model that wrote the vectors.
MODEL_KEY: Final = "embedding_model"
#: Key of the vectors themselves, by raw MCP tool name.
TOOLS_KEY: Final = "tools"
#: Key of each vector's identity: the hash of the exact texts it was computed from.
IDENTITIES_KEY: Final = "identities"

#: How many description words become keywords (the selector's own rule).
_KEYWORD_WORDS: Final = 10
_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def embedding_model_key() -> str:
    """The model AND the width the selector asks it for — one string, one implementation.

    The same model serves several widths on request (Gemini: 384 or 1 536), so
    the name alone does not identify the vectors it produced.
    """
    return f"{settings.memory_embedding_model}:{settings.memory_embedding_dimensions}"


def tool_embedding_texts(
    tool: Mapping[str, Any], *, server_name: str
) -> tuple[str | None, list[str]]:
    """The exact texts LIA embeds for one tool: its description line and its keywords.

    One implementation, read by the embedder (``compute_tool_embeddings``) and
    by the identity below, so a change in how the texts are composed changes
    the identity too and the old vectors are recomputed (spec 2026-10-21 M6).

    Args:
        tool: The tool's metadata (``name``, ``description``).
        server_name: The server's name, a keyword of every tool.

    Returns:
        ``(description line or None, keywords)``.
    """
    name = str(tool.get("name", ""))
    description = str(tool.get("description") or "")
    line = _BOLD.sub(r"\1", description.split("\n")[0].strip()) if description else ""
    words = [w.strip(".,;:!?") for w in description.split() if len(w.strip(".,;:!?")) > 3]
    return (line or None), [server_name, name, *words[:_KEYWORD_WORDS]]


def tool_identity(tool: Mapping[str, Any], *, server_name: str) -> str:
    """The identity of one tool's vectors: the model and the exact texts they embed.

    LangChain ``CacheBackedEmbeddings``' keying, applied per tool: a tool whose
    texts did not change keeps its vectors whatever happened to the others.
    """
    description, keywords = tool_embedding_texts(tool, server_name=server_name)
    return canonical_fingerprint(
        {"model": embedding_model_key(), "description": description, "keywords": keywords}
    )


def catalogue_fingerprint(tools: Sequence[Mapping[str, Any]], *, server_name: str) -> str:
    """A catalogue's fingerprint that ignores the ORDER a server lists its tools in.

    MCP asks servers for a deterministic order without requiring it; measured,
    one server's reordered listings recomputed every vector (spec §0ter H5).
    """
    ordered = sorted(tools, key=lambda tool: str(tool.get("name", "")))
    return canonical_fingerprint({"server": server_name, "tools": ordered})


def wrap_server_cache(
    tools: Mapping[str, Any],
    *,
    tool_metadata: Sequence[Mapping[str, Any]],
    server_name: str,
) -> dict[str, Any]:
    """The envelope to persist: the model key, the vectors and each vector's identity.

    Args:
        tools: Vectors by raw tool name.
        tool_metadata: The tools they were computed from.
        server_name: The server's name at computation time.

    Returns:
        A NEW dict, never a view of its inputs.
    """
    identities = {
        str(tool["name"]): tool_identity(tool, server_name=server_name)
        for tool in tool_metadata
        if tool.get("name") in tools
    }
    return {MODEL_KEY: embedding_model_key(), TOOLS_KEY: dict(tools), IDENTITIES_KEY: identities}


def reusable_vectors(
    cache: Any, tools: Sequence[Mapping[str, Any]], *, server_name: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Split the current tools into those whose stored vectors still hold and the rest.

    A stored vector is reused only when this model wrote it AND its identity
    equals the current tool's. A legacy envelope (no identities), another
    model, or no envelope at all reuses nothing: each is recomputed once.

    Args:
        cache: The column's value — the envelope, a legacy shape, or nothing.
        tools: The tools the server lists now.
        server_name: The server's current name.

    Returns:
        ``(kept vectors by tool name, tools to embed)``.
    """
    stored: Mapping[str, Any] = {}
    identities: Mapping[str, Any] = {}
    if isinstance(cache, dict) and cache.get(MODEL_KEY) == embedding_model_key():
        stored_raw, identities_raw = cache.get(TOOLS_KEY), cache.get(IDENTITIES_KEY)
        stored = stored_raw if isinstance(stored_raw, dict) else {}
        identities = identities_raw if isinstance(identities_raw, dict) else {}
    kept: dict[str, Any] = {}
    missing: list[dict[str, Any]] = []
    for tool in tools:
        name = str(tool.get("name", ""))
        identity = tool_identity(tool, server_name=server_name)
        if name in stored and identities.get(name) == identity:
            kept[name] = stored[name]
        else:
            missing.append(dict(tool))
    return kept, missing
