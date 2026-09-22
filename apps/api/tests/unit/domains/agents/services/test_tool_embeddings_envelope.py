"""A persisted vector cache carries the model that wrote it, or it is stale (2026-09-20).

``user_mcp_servers.tool_embeddings_cache`` held a flat dict of vectors with no
model key: two dev servers and two production servers (DeepWiki, GitMCP) kept
384-dimension vectors from an earlier embedder while every query is embedded
at 1 536, and ``cosine_similarity`` scored their tools 0 in silence — 163
warnings per turn on dev, 20 tools invisible to the ranking. The envelope
names its model; a cache of another model, or of the legacy shape, is stale
and recomputed where the tools are already in hand.
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.agents.services.tool_embeddings_envelope import (
    embedding_model_key,
    read_server_cache,
    wrap_server_cache,
)

pytestmark = pytest.mark.unit

_TOOLS = {"hub_search": {"description": [0.1, 0.2], "keywords": [[0.3, 0.4]]}}


def test_the_key_names_the_model_and_the_width_the_selector_asks_for() -> None:
    assert embedding_model_key() == (
        f"{settings.memory_embedding_model}:{settings.memory_embedding_dimensions}"
    )


def test_a_cache_written_by_this_model_is_read_whole() -> None:
    assert read_server_cache(wrap_server_cache(_TOOLS)) == (_TOOLS, None)


def test_a_cache_of_another_model_is_stale() -> None:
    cache = {**wrap_server_cache(_TOOLS), "embedding_model": "models/old-embedder:384"}
    assert read_server_cache(cache) == ({}, "model_changed")


def test_the_legacy_flat_shape_is_stale() -> None:
    assert read_server_cache(_TOOLS) == ({}, "legacy_shape")


def test_an_empty_or_missing_cache_is_simply_empty() -> None:
    assert read_server_cache(None) == ({}, None)
    assert read_server_cache({}) == ({}, None)
    assert read_server_cache(wrap_server_cache({})) == ({}, None)
