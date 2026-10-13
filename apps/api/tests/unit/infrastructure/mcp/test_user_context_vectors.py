"""A server's vectors are read alone and parsed once per catalogue per worker (ADR-283 amendment)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

from src.domains.agents.services.tool_embeddings_envelope import wrap_server_cache
from src.domains.agents.services.tool_vectors import (
    get_server_vector_cache,
    reset_server_vector_cache,
)
from src.infrastructure.mcp.user_context import _usable_tool_embeddings

pytestmark = pytest.mark.unit

TOOLS: list[dict[str, Any]] = [{"name": "hub_search", "description": "Search", "input_schema": {}}]
ENVELOPE = wrap_server_cache(
    {"hub_search": {"description": [0.1, 0.2], "keywords": [[0.3, 0.4]], "keyword_names": ["srv"]}},
    tool_metadata=TOOLS,
)


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:
    reset_server_vector_cache()
    yield
    reset_server_vector_cache()


@pytest.fixture
def repo() -> Iterator[AsyncMock]:
    """The repository class the context builder instantiates, and a session that opens nothing."""
    repository = AsyncMock()
    repository.get_tool_embeddings_cache = AsyncMock(return_value=ENVELOPE)

    @asynccontextmanager
    async def _session() -> AsyncIterator[MagicMock]:
        yield MagicMock()

    with (
        patch("src.domains.user_mcp.repository.UserMCPServerRepository", return_value=repository),
        patch("src.infrastructure.database.session.get_db_context", _session),
    ):
        yield repository


def _server() -> Any:
    return SimpleNamespace(id=uuid4(), name="TestServer")


class TestParsedOncePerCatalogue:
    async def test_the_envelope_is_read_once_and_served_compact(self, repo: AsyncMock) -> None:
        server = _server()

        first = await _usable_tool_embeddings(server, TOOLS)
        second = await _usable_tool_embeddings(server, list(TOOLS))

        repo.get_tool_embeddings_cache.assert_awaited_once_with(server.id)
        assert second is first, "the second turn is served from the per-worker cache"
        assert first["hub_search"]["description"].dtype == np.float32
        assert first["hub_search"]["keywords"].shape == (1, 2)
        assert first["hub_search"]["keyword_names"] == ["srv"]

    async def test_a_changed_catalogue_reads_the_envelope_again(self, repo: AsyncMock) -> None:
        server = _server()
        changed = [*TOOLS, {"name": "hub_fetch", "description": "Fetch", "input_schema": {}}]
        repo.get_tool_embeddings_cache.side_effect = [
            ENVELOPE,
            wrap_server_cache({}, tool_metadata=changed),
        ]

        await _usable_tool_embeddings(server, TOOLS)
        after = await _usable_tool_embeddings(server, changed)

        assert repo.get_tool_embeddings_cache.await_count == 2
        assert after == {}
        assert len(get_server_vector_cache()) == 2

    async def test_two_servers_never_share_an_entry(self, repo: AsyncMock) -> None:
        first = await _usable_tool_embeddings(_server(), TOOLS)
        second = await _usable_tool_embeddings(_server(), TOOLS)

        assert first is not second
        assert repo.get_tool_embeddings_cache.await_count == 2


class TestTheReadIsBestEffort:
    async def test_a_failed_read_costs_the_ranking_never_the_tools(self, repo: AsyncMock) -> None:
        """The tools still bind through their family's coverage: nothing raises."""
        repo.get_tool_embeddings_cache.side_effect = RuntimeError("database away")
        server = _server()

        assert await _usable_tool_embeddings(server, TOOLS) == {}
        assert len(get_server_vector_cache()) == 0, "a failure is never cached"

    async def test_a_row_without_envelope_is_empty_and_cached(self, repo: AsyncMock) -> None:
        repo.get_tool_embeddings_cache.return_value = None
        server = _server()

        assert await _usable_tool_embeddings(server, TOOLS) == {}
        assert await _usable_tool_embeddings(server, TOOLS) == {}
        repo.get_tool_embeddings_cache.assert_awaited_once()


class TestAStaleEnvelopeIsRecomputedThenCached:
    async def test_recomputed_vectors_are_cached_compact(self, repo: AsyncMock) -> None:
        repo.get_tool_embeddings_cache.return_value = {"legacy": "flat shape"}
        repo.get_by_id = AsyncMock(return_value=MagicMock())
        fresh = {"hub_search": {"description": [0.5] * 4, "keywords": [[0.1] * 4]}}
        server = _server()

        with patch(
            "src.domains.agents.services.tool_selector.compute_tool_embeddings",
            new=AsyncMock(return_value=fresh),
        ) as compute:
            first = await _usable_tool_embeddings(server, TOOLS)
            second = await _usable_tool_embeddings(server, TOOLS)

        compute.assert_awaited_once_with(tool_metadata=TOOLS, server_name="TestServer")
        repo.update.assert_awaited_once()
        assert second is first
        assert first["hub_search"]["description"].shape == (4,)
        assert first["hub_search"]["keywords"].dtype == np.float32
