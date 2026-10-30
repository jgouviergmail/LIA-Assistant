"""A persisted vector cache carries the model AND the texts that produced each vector.

``user_mcp_servers.tool_embeddings_cache`` held a flat dict of vectors with no
model key: two dev servers and two production servers (DeepWiki, GitMCP) kept
384-dimension vectors from an earlier embedder while every query is embedded
at 1 536, and ``cosine_similarity`` scored their tools 0 in silence (2026-09-20).
Since 2026-10-28 each vector also carries its identity — the hash of the exact
texts it embeds — so a reordered or partly edited catalogue keeps every vector
whose texts did not change (spec 2026-10-21 M6).
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.agents.services.tool_embeddings_envelope import (
    IDENTITIES_KEY,
    MODEL_KEY,
    TOOLS_KEY,
    catalogue_fingerprint,
    embedding_model_key,
    reusable_vectors,
    tool_embedding_texts,
    tool_identity,
    wrap_server_cache,
)

pytestmark = pytest.mark.unit

_TOOL = {"name": "hub_search", "description": "**Search** the hub by keyword\nMore details"}
_VECTORS = {"hub_search": {"description": [0.1, 0.2], "keywords": [[0.3, 0.4]]}}


def test_the_key_names_the_model_and_the_width_the_selector_asks_for() -> None:
    assert embedding_model_key() == (
        f"{settings.memory_embedding_model}:{settings.memory_embedding_dimensions}"
    )


def test_the_texts_are_the_first_clean_line_and_the_keywords() -> None:
    description, keywords = tool_embedding_texts(_TOOL, server_name="Hub")
    assert description == "Search the hub by keyword"
    assert keywords[:2] == ["Hub", "hub_search"]
    assert "Search" not in keywords and "**Search**" in keywords  # words as written


def test_a_cache_written_by_this_model_is_reused_whole() -> None:
    cache = wrap_server_cache(_VECTORS, tool_metadata=[_TOOL], server_name="Hub")
    assert reusable_vectors(cache, [_TOOL], server_name="Hub") == (_VECTORS, [])
    assert cache[IDENTITIES_KEY]["hub_search"] == tool_identity(_TOOL, server_name="Hub")


def test_a_cache_of_another_model_reuses_nothing() -> None:
    cache = {
        **wrap_server_cache(_VECTORS, tool_metadata=[_TOOL], server_name="Hub"),
        MODEL_KEY: "models/old-embedder:384",
    }
    assert reusable_vectors(cache, [_TOOL], server_name="Hub") == ({}, [_TOOL])


def test_the_legacy_shapes_reuse_nothing() -> None:
    assert reusable_vectors(_VECTORS, [_TOOL], server_name="Hub") == ({}, [_TOOL])
    no_identities = {MODEL_KEY: embedding_model_key(), TOOLS_KEY: _VECTORS}
    assert reusable_vectors(no_identities, [_TOOL], server_name="Hub") == ({}, [_TOOL])


def test_no_cache_means_every_tool_is_missing() -> None:
    assert reusable_vectors(None, [_TOOL], server_name="Hub") == ({}, [_TOOL])
    assert reusable_vectors({}, [], server_name="Hub") == ({}, [])


def test_the_catalogue_fingerprint_ignores_order_but_not_content_or_server() -> None:
    other = {"name": "hub_fetch", "description": "Fetch"}
    assert catalogue_fingerprint([_TOOL, other], server_name="Hub") == catalogue_fingerprint(
        [other, _TOOL], server_name="Hub"
    )
    assert catalogue_fingerprint([_TOOL], server_name="Hub") != catalogue_fingerprint(
        [_TOOL, other], server_name="Hub"
    )
    assert catalogue_fingerprint([_TOOL], server_name="Hub") != catalogue_fingerprint(
        [_TOOL], server_name="Other"
    )
