"""The manual test writes a version-2 snapshot; the conditional publication refuses by reason (M1)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.user_mcp.catalogue_publication import (
    probe_update_data,
    publish_catalogue_if_current,
)
from src.infrastructure.mcp.catalogue_snapshot import (
    ValidSnapshot,
    build_snapshot,
    parse_catalogue_snapshot,
    reserve_generation,
)
from src.infrastructure.mcp.user_pool import PoolEntry

pytestmark = pytest.mark.unit

TOOLS = [{"name": "search", "description": "Search"}, {"name": "fetch", "description": "Fetch"}]


def _entry() -> PoolEntry:
    return PoolEntry(
        user_id=uuid4(),
        server_id=uuid4(),
        last_used=0.0,
        tools=list(TOOLS),
        configuration_fingerprint="cfg",
        has_reference_tool=True,
        server_ttl_ms=30_000,
        cache_scope="public",
        server_instructions="Search first.",
    )


async def test_test_connection_writes_v2_envelope() -> None:
    server = SimpleNamespace(
        id=uuid4(), name="Notes", user_id=uuid4(), domain_description="Notes", auth_type="none"
    )
    with patch(
        "src.domains.user_mcp.catalogue_publication.build_connection_embeddings",
        new=AsyncMock(return_value={}),
    ):
        update = await probe_update_data(
            MagicMock(), server, _entry(), user_id=server.user_id, generation=42  # type: ignore[arg-type]
        )

    read = parse_catalogue_snapshot(update["discovered_tools_cache"])
    assert isinstance(read, ValidSnapshot)
    snapshot = read.snapshot
    assert [t["name"] for t in snapshot.tools] == ["fetch", "search"]
    assert snapshot.generation == 42 and snapshot.configuration_fingerprint == "cfg"
    assert (snapshot.has_reference_tool, snapshot.server_ttl_ms) == (True, 30_000)
    assert snapshot.server_instructions == "Search first."
    assert update["status"] == "active" and update["last_error"] is None


def test_snapshot_source_and_wording() -> None:
    from src.infrastructure.mcp.user_catalogue import describe_user_server

    stored = describe_user_server("Notes", "My notes", TOOLS, from_snapshot=True)
    bare = describe_user_server("Notes", None, TOOLS, from_snapshot=True)
    live = describe_user_server("Notes", "My notes", TOOLS)

    assert stored.source == "stored+snapshot" and bare.source == "snapshot"
    assert live.source == "stored+discovered"
    assert "\nDeclared capabilities: " in stored.description
    assert "Current discovered capabilities" not in stored.description + live.description
    assert stored.fingerprint == live.fingerprint  # same declarations, same catalogue


@pytest.mark.parametrize(
    "cache",
    [
        list(TOOLS),
        {"tools": list(TOOLS)},
        "v2",
    ],
)
def test_projection_reads_legacy_and_v2(cache: object) -> None:
    from datetime import UTC, datetime

    from src.domains.user_mcp.projection import server_to_response
    from src.infrastructure.mcp.catalogue_snapshot import snapshot_to_jsonb

    if cache == "v2":
        cache = snapshot_to_jsonb(
            build_snapshot(
                tools=TOOLS,
                configuration_fingerprint="cfg",
                discovered_at=datetime.now(UTC),
                generation=1,
            )
        )
    server = MagicMock()
    server.discovered_tools_cache = cache
    server.auth_type, server.status = "none", "active"
    service = MagicMock()
    with patch(
        "src.domains.user_mcp.projection.UserMCPServerResponse",
        side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
    ):
        response = server_to_response(server, service)  # type: ignore[arg-type]

    assert sorted(tool.tool_name for tool in response.tools) == ["fetch", "search"]
    assert response.tool_count == 2


def test_generations_reserved_later_are_larger() -> None:
    first = reserve_generation()
    assert reserve_generation() > first


def _locked_row(row: Any):
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=row)
    session.execute = AsyncMock(return_value=result)

    @asynccontextmanager
    async def context() -> AsyncIterator[Any]:
        yield session

    return patch("src.infrastructure.database.session.get_db_context", context)


def _snapshot(generation: int = 5) -> Any:
    from datetime import UTC, datetime

    return build_snapshot(
        tools=TOOLS,
        configuration_fingerprint="cfg",
        discovered_at=datetime.now(UTC),
        generation=generation,
    )


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (None, "missing"),
        (
            SimpleNamespace(is_enabled=False, status="active", discovered_tools_cache=None),
            "inactive",
        ),
        (SimpleNamespace(is_enabled=True, status="error", discovered_tools_cache=None), "inactive"),
    ],
)
async def test_publication_refused_when_inactive_or_missing(row: Any, expected: str) -> None:
    with _locked_row(row):
        outcome = await publish_catalogue_if_current(
            user_id=uuid4(), server_id=uuid4(), snapshot=_snapshot(), tool_embeddings=None
        )
    assert outcome == expected


def _active_row(stored: Any) -> SimpleNamespace:
    return SimpleNamespace(
        is_enabled=True,
        status="active",
        url="https://notes.example/mcp",
        timeout_seconds=30,
        extra_headers=None,
        discovered_tools_cache=stored,
    )


@pytest.mark.parametrize(("tools", "kept"), [(TOOLS, True), ([{"name": "other"}], False)])
async def test_a_rediscovery_keeps_the_reference_only_for_the_same_catalogue(
    tools: list[dict[str, str]], kept: bool
) -> None:
    """Discovery never reads read_me (spec §5.5b): a revalidation of an unchanged
    catalogue must not erase what a real use fetched; a changed one clears it."""
    from datetime import UTC, datetime

    from src.infrastructure.mcp.catalogue_fingerprint import connection_fingerprint
    from src.infrastructure.mcp.catalogue_snapshot import snapshot_to_jsonb

    configuration = connection_fingerprint("https://notes.example/mcp", None, 30, None)
    fetched = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)
    stored = build_snapshot(
        tools=TOOLS,
        configuration_fingerprint=configuration,
        discovered_at=fetched,
        generation=5,
        reference_content="# Guide",
        reference_fetched_at=fetched,
    )
    row = _active_row(snapshot_to_jsonb(stored))
    fresh = build_snapshot(
        tools=tools,
        configuration_fingerprint=configuration,
        discovered_at=datetime.now(UTC),
        generation=6,
    )
    with (
        _locked_row(row),
        patch("src.infrastructure.mcp.auth.build_auth_for_server", return_value=None),
    ):
        outcome = await publish_catalogue_if_current(
            user_id=uuid4(), server_id=uuid4(), snapshot=fresh, tool_embeddings=None
        )

    assert outcome == "published"
    read = parse_catalogue_snapshot(row.discovered_tools_cache)
    assert isinstance(read, ValidSnapshot) and read.snapshot.generation == 6
    assert read.snapshot.reference_content == ("# Guide" if kept else None)
    assert read.snapshot.reference_fetched_at == (fetched if kept else None)


def _described_server() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(), name="Notes", user_id=uuid4(), domain_description="Notes", auth_type="none"
    )


async def test_the_probe_carries_the_vectors_with_the_model_that_wrote_them() -> None:
    from src.domains.agents.services.tool_embeddings_envelope import MODEL_KEY, TOOLS_KEY

    vectors = {"search": {"vector": [0.1, 0.2]}, "fetch": {"vector": [0.3, 0.4]}}
    server = _described_server()
    with patch(
        "src.domains.user_mcp.catalogue_publication.build_connection_embeddings",
        new=AsyncMock(return_value=vectors),
    ):
        update = await probe_update_data(
            MagicMock(), server, _entry(), user_id=server.user_id, generation=3  # type: ignore[arg-type]
        )

    envelope = update["tool_embeddings_cache"]
    assert envelope[TOOLS_KEY] == vectors
    assert envelope[MODEL_KEY]


async def test_a_failed_embedding_still_publishes_the_catalogue() -> None:
    """The vectors are an optimisation: their failure never refuses the connection."""
    server = _described_server()
    with patch(
        "src.domains.user_mcp.catalogue_publication.build_connection_embeddings",
        new=AsyncMock(side_effect=RuntimeError("embedding provider down")),
    ):
        update = await probe_update_data(
            MagicMock(), server, _entry(), user_id=server.user_id, generation=3  # type: ignore[arg-type]
        )

    assert "tool_embeddings_cache" not in update
    assert isinstance(parse_catalogue_snapshot(update["discovered_tools_cache"]), ValidSnapshot)
    assert update["status"] == "active"


async def test_a_publication_with_vectors_writes_them_as_a_new_dict() -> None:
    from datetime import UTC, datetime

    from src.infrastructure.mcp.catalogue_fingerprint import connection_fingerprint

    configuration = connection_fingerprint("https://notes.example/mcp", None, 30, None)
    row = _active_row(None)
    row.tool_embeddings_cache = None
    vectors = {"model": "m", "tools": {"search": [0.1]}}
    fresh = build_snapshot(
        tools=TOOLS,
        configuration_fingerprint=configuration,
        discovered_at=datetime.now(UTC),
        generation=6,
    )
    with (
        _locked_row(row),
        patch("src.infrastructure.mcp.auth.build_auth_for_server", return_value=None),
    ):
        outcome = await publish_catalogue_if_current(
            user_id=uuid4(), server_id=uuid4(), snapshot=fresh, tool_embeddings=vectors
        )

    assert outcome == "published"
    assert row.tool_embeddings_cache == vectors
    assert row.tool_embeddings_cache is not vectors
