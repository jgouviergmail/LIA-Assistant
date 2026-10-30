"""Tool vectors are reused per TOOL, so only what changed is embedded again (M6, E11, E8).

Measured on production (spec 2026-10-21 §0ter H5): 31 recomputations in seven
days, 131 s on the turns' critical path, up to 16.4 s for one turn, every one
« catalogue_changed » — one 6-tool server recomputed on 21 of its 46
discoveries while its tool count never moved. The envelope's fingerprint was
taken over the ORDERED list, so a reordering or a single edited tool threw
every vector away. A vector is now keyed by the exact text LIA embeds for its
tool (LangChain ``CacheBackedEmbeddings``' keying), the catalogue fingerprint
ignores order, and only the missing tools are embedded — never while a
spending ceiling refuses the account (E8).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.services.tool_embeddings_envelope import (
    IDENTITIES_KEY,
    TOOLS_KEY,
    wrap_server_cache,
)
from src.domains.agents.services.tool_vectors import reset_server_vector_cache
from src.infrastructure.mcp.server_vectors import (
    usable_tool_embeddings as _usable_tool_embeddings,
)

pytestmark = pytest.mark.unit

SERVER_NAME = "Notes"
SEARCH = {"name": "search_notes", "description": "Search the notes by keyword", "input_schema": {}}
FETCH = {"name": "fetch_note", "description": "Fetch one note by its id", "input_schema": {}}


def _vectors(*names: str) -> dict[str, Any]:
    return {name: {"description": [0.1, 0.2], "keywords": [[0.3, 0.4]]} for name in names}


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:
    reset_server_vector_cache()
    yield
    reset_server_vector_cache()


@pytest.fixture
def repo() -> Iterator[AsyncMock]:
    repository = AsyncMock()
    repository.get_by_id = AsyncMock(return_value=MagicMock())

    @asynccontextmanager
    async def _session() -> AsyncIterator[MagicMock]:
        yield MagicMock()

    with (
        patch("src.domains.user_mcp.repository.UserMCPServerRepository", return_value=repository),
        patch("src.infrastructure.database.session.get_db_context", _session),
    ):
        yield repository


@pytest.fixture
def compute() -> Iterator[AsyncMock]:
    async def embed(*, tool_metadata: list[dict[str, Any]], server_name: str) -> dict[str, Any]:
        return _vectors(*(tool["name"] for tool in tool_metadata))

    with patch(
        "src.domains.agents.services.tool_selector.compute_tool_embeddings",
        new=AsyncMock(side_effect=embed),
    ) as mock:
        yield mock


@pytest.fixture
def allowed() -> Iterator[AsyncMock]:
    with patch(
        "src.domains.usage_limits.enforcement.spend_blocked", new=AsyncMock(return_value=False)
    ) as mock:
        yield mock


def _server() -> Any:
    return SimpleNamespace(id=uuid4(), name=SERVER_NAME, user_id=uuid4())


async def test_reordered_catalogue_reuses_every_vector(
    repo: AsyncMock, compute: AsyncMock, allowed: AsyncMock
) -> None:
    repo.get_tool_embeddings_cache = AsyncMock(
        return_value=wrap_server_cache(
            _vectors("search_notes", "fetch_note"),
            tool_metadata=[SEARCH, FETCH],
            server_name=SERVER_NAME,
        )
    )

    vectors = await _usable_tool_embeddings(_server(), [FETCH, SEARCH])

    compute.assert_not_awaited()
    repo.update.assert_not_awaited()
    assert set(vectors) == {"search_notes", "fetch_note"}


async def test_one_changed_tool_embeds_one(
    repo: AsyncMock, compute: AsyncMock, allowed: AsyncMock
) -> None:
    repo.get_tool_embeddings_cache = AsyncMock(
        return_value=wrap_server_cache(
            _vectors("search_notes", "fetch_note"),
            tool_metadata=[SEARCH, FETCH],
            server_name=SERVER_NAME,
        )
    )
    edited = {**FETCH, "description": "Fetch one note, with its attachments"}

    vectors = await _usable_tool_embeddings(_server(), [SEARCH, edited])

    compute.assert_awaited_once_with(tool_metadata=[edited], server_name=SERVER_NAME)
    assert set(vectors) == {"search_notes", "fetch_note"}


async def test_new_tools_embedded_inline_in_one_call(
    repo: AsyncMock, compute: AsyncMock, allowed: AsyncMock
) -> None:
    """A first discovery embeds every tool in ONE call (the background path was rejected:
    a tool without a vector can fall out of the planner's catalogue)."""
    repo.get_tool_embeddings_cache = AsyncMock(return_value=None)

    vectors = await _usable_tool_embeddings(_server(), [SEARCH, FETCH])

    compute.assert_awaited_once_with(tool_metadata=[SEARCH, FETCH], server_name=SERVER_NAME)
    assert set(vectors) == {"search_notes", "fetch_note"}


async def test_spend_blocked_keeps_previous_vectors(repo: AsyncMock, compute: AsyncMock) -> None:
    repo.get_tool_embeddings_cache = AsyncMock(
        return_value=wrap_server_cache(
            _vectors("search_notes"), tool_metadata=[SEARCH], server_name=SERVER_NAME
        )
    )
    with patch(
        "src.domains.usage_limits.enforcement.spend_blocked", new=AsyncMock(return_value=True)
    ):
        vectors = await _usable_tool_embeddings(_server(), [SEARCH, FETCH])

    compute.assert_not_awaited()
    repo.update.assert_not_awaited()
    assert set(vectors) == {"search_notes"}  # the new tool stays offered, unranked


async def test_envelope_written_as_new_dict(
    repo: AsyncMock, compute: AsyncMock, allowed: AsyncMock
) -> None:
    previous = wrap_server_cache(
        _vectors("search_notes"), tool_metadata=[SEARCH], server_name=SERVER_NAME
    )
    snapshot = {
        key: dict(value) if isinstance(value, dict) else value for key, value in previous.items()
    }
    repo.get_tool_embeddings_cache = AsyncMock(return_value=previous)
    row = MagicMock()
    repo.get_by_id = AsyncMock(return_value=row)

    await _usable_tool_embeddings(_server(), [SEARCH, FETCH])

    written = repo.update.await_args.args[1]["tool_embeddings_cache"]
    assert written is not previous and previous == snapshot  # never mutated in place
    assert set(written[TOOLS_KEY]) == {"search_notes", "fetch_note"}
    assert set(written[IDENTITIES_KEY]) == {"search_notes", "fetch_note"}


async def test_legacy_envelope_recomputed_once(
    repo: AsyncMock, compute: AsyncMock, allowed: AsyncMock
) -> None:
    """A row written before per-tool identities is recomputed once; the next turn hits."""
    legacy = {"embedding_model": "x", TOOLS_KEY: _vectors("search_notes")}
    stored: list[Any] = [legacy]
    repo.get_tool_embeddings_cache = AsyncMock(side_effect=lambda _id: stored[-1])

    async def keep(_row: Any, data: dict[str, Any]) -> None:
        stored.append(data["tool_embeddings_cache"])

    repo.update = AsyncMock(side_effect=keep)
    server = _server()

    await _usable_tool_embeddings(server, [SEARCH])
    reset_server_vector_cache()  # another worker: no process cache to help
    await _usable_tool_embeddings(server, [SEARCH])

    assert compute.await_count == 1


async def test_a_server_rename_reembeds_its_tools(
    repo: AsyncMock, compute: AsyncMock, allowed: AsyncMock
) -> None:
    """The server's name is one of the texts LIA embeds for each tool."""
    repo.get_tool_embeddings_cache = AsyncMock(
        return_value=wrap_server_cache(
            _vectors("search_notes"), tool_metadata=[SEARCH], server_name=SERVER_NAME
        )
    )
    renamed = SimpleNamespace(id=uuid4(), name="Work notes", user_id=uuid4())

    await _usable_tool_embeddings(renamed, [SEARCH])

    compute.assert_awaited_once_with(tool_metadata=[SEARCH], server_name="Work notes")
