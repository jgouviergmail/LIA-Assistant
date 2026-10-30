"""The persisted catalogue snapshot of a personal MCP server: one shape, one parser (M1).

The ``discovered_tools_cache`` column held a bare list of tools with no date, no
fingerprint and no word on who wrote it, so nothing could serve a turn from it.
It becomes a versioned envelope (spec 2026-10-21 §5.2): routable only while its
configuration fingerprint matches the row being prepared, revalidated after the
server's own TTL when it gives one (MCP 2026-07-28 ``ttlMs``), in canonical
order so a reordered listing is the same catalogue. Legacy shapes are read
forever by the UI and never serve the router.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.core.config import settings
from src.infrastructure.mcp.catalogue_snapshot import (
    REFERENCE_MAX_CHARS,
    CatalogueSnapshot,
    InvalidSnapshot,
    LegacySnapshot,
    ValidSnapshot,
    build_snapshot,
    parse_catalogue_snapshot,
    revalidation_horizon_seconds,
    snapshot_routes,
    snapshot_to_jsonb,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
SEARCH = {"name": "search", "description": "Search", "input_schema": {}}
FETCH = {"name": "fetch", "description": "Fetch", "input_schema": {}}


def _snapshot(**overrides: object) -> CatalogueSnapshot:
    values: dict[str, object] = {
        "tools": [FETCH, SEARCH],
        "configuration_fingerprint": "cfg-1",
        "discovered_at": NOW,
        "generation": 7,
        "has_reference_tool": True,
        "server_ttl_ms": 60_000,
        "cache_scope": "private",
        "server_instructions": "Use search before fetch.",
    }
    values.update(overrides)
    return build_snapshot(**values)  # type: ignore[arg-type]


class TestParseMatrix:
    def test_parse_matrix(self) -> None:
        assert isinstance(parse_catalogue_snapshot(None), InvalidSnapshot)
        legacy_list = parse_catalogue_snapshot([SEARCH])
        assert isinstance(legacy_list, LegacySnapshot) and legacy_list.tools == (SEARCH,)
        legacy_dict = parse_catalogue_snapshot({"tools": [SEARCH]})
        assert isinstance(legacy_dict, LegacySnapshot) and legacy_dict.tools == (SEARCH,)
        valid = parse_catalogue_snapshot(snapshot_to_jsonb(_snapshot()))
        assert isinstance(valid, ValidSnapshot)
        future = {**snapshot_to_jsonb(_snapshot()), "version": 3}
        assert isinstance(parse_catalogue_snapshot(future), InvalidSnapshot)
        malformed = {**snapshot_to_jsonb(_snapshot()), "tools": "not a list"}
        assert isinstance(parse_catalogue_snapshot(malformed), InvalidSnapshot)
        too_many = {
            **snapshot_to_jsonb(_snapshot()),
            "tools": [
                {"name": f"t{i}", "description": ""}
                for i in range(settings.mcp_max_tools_per_server + 1)
            ],
        }
        assert isinstance(parse_catalogue_snapshot(too_many), InvalidSnapshot)

    def test_a_legacy_dict_without_tools_is_invalid(self) -> None:
        assert isinstance(parse_catalogue_snapshot({"unexpected": 1}), InvalidSnapshot)


def test_roundtrip_every_field() -> None:
    snapshot = _snapshot(reference_content="# How to use", reference_fetched_at=NOW)
    parsed = parse_catalogue_snapshot(snapshot_to_jsonb(snapshot))
    assert isinstance(parsed, ValidSnapshot)
    assert parsed.snapshot == snapshot


def test_jsonb_is_a_new_plain_dict() -> None:
    snapshot = _snapshot()
    first, second = snapshot_to_jsonb(snapshot), snapshot_to_jsonb(snapshot)
    assert first == second and first is not second
    assert first["discovered_at"] == NOW.isoformat()


def test_tools_stored_in_canonical_order() -> None:
    """Two listings of the same tools in different orders are the same catalogue."""
    one = _snapshot(tools=[SEARCH, FETCH])
    other = _snapshot(tools=[FETCH, SEARCH])
    assert [t["name"] for t in one.tools] == ["fetch", "search"]
    assert one.catalogue_fingerprint == other.catalogue_fingerprint


def test_the_catalogue_fingerprint_covers_the_tools_only() -> None:
    with_reference = _snapshot(reference_content="# Guide", reference_fetched_at=NOW)
    assert with_reference.catalogue_fingerprint == _snapshot().catalogue_fingerprint
    assert _snapshot(tools=[SEARCH]).catalogue_fingerprint != _snapshot().catalogue_fingerprint


def test_the_reference_is_bounded() -> None:
    snapshot = _snapshot(
        reference_content="x" * (REFERENCE_MAX_CHARS + 10), reference_fetched_at=NOW
    )
    assert len(snapshot.reference_content or "") == REFERENCE_MAX_CHARS


class TestRouting:
    def test_snapshot_routes_only_when_fingerprint_matches(self) -> None:
        read = parse_catalogue_snapshot(snapshot_to_jsonb(_snapshot()))
        assert snapshot_routes(read, configuration_fingerprint="cfg-1") is True
        assert snapshot_routes(read, configuration_fingerprint="cfg-2") is False

    def test_legacy_never_routes(self) -> None:
        assert (
            snapshot_routes(LegacySnapshot(tools=(SEARCH,)), configuration_fingerprint="") is False
        )
        assert (
            snapshot_routes(InvalidSnapshot(reason="none"), configuration_fingerprint="") is False
        )

    def test_an_empty_catalogue_never_routes(self) -> None:
        read = parse_catalogue_snapshot(snapshot_to_jsonb(_snapshot(tools=[])))
        assert snapshot_routes(read, configuration_fingerprint="cfg-1") is False

    def test_private_scope_keyed_by_authorization_context(self) -> None:
        """A private list is never served under another credential or grant (SEP-2549)."""
        private = parse_catalogue_snapshot(snapshot_to_jsonb(_snapshot(cache_scope="private")))
        assert snapshot_routes(private, configuration_fingerprint="cfg-1") is True
        assert snapshot_routes(private, configuration_fingerprint="cfg-after-regrant") is False


class TestRevalidationHorizon:
    def test_server_ttl_drives_revalidation_horizon(self) -> None:
        assert revalidation_horizon_seconds(_snapshot(server_ttl_ms=60_000)) == 60.0

    def test_legacy_server_uses_setting(self) -> None:
        assert revalidation_horizon_seconds(_snapshot(server_ttl_ms=None)) == float(
            settings.mcp_user_catalogue_revalidate_after_seconds
        )

    def test_a_zero_ttl_is_the_sdk_default_not_a_hint(self) -> None:
        """mcp 2.2.0 sends ``ttlMs: 0`` when the server declared nothing (measured)."""
        assert revalidation_horizon_seconds(_snapshot(server_ttl_ms=0)) == float(
            settings.mcp_user_catalogue_revalidate_after_seconds
        )

    def test_a_server_ttl_is_capped_at_a_day(self) -> None:
        assert revalidation_horizon_seconds(_snapshot(server_ttl_ms=10**12)) == 86_400.0

    def test_age_is_measured_from_discovery(self) -> None:
        snapshot = _snapshot(discovered_at=NOW - timedelta(seconds=61), server_ttl_ms=60_000)
        assert snapshot.age_seconds(NOW) == pytest.approx(61.0)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("discovered_at", 1_761_642_000, "ValueError"),  # not an instant
        ("discovered_at", "2026-10-28T09:00:00", "ValueError"),  # a naive instant
        ("reference_content", ["not", "text"], "ValueError"),
        ("cache_scope", "shared", "ValueError"),
        ("server_ttl_ms", True, "ValueError"),
        ("server_ttl_ms", "60000", "ValueError"),
        ("generation", True, "ValueError"),
    ],
)
def test_an_envelope_field_of_the_wrong_shape_is_invalid(
    field: str, value: object, reason: str
) -> None:
    """A version-2 envelope is read whole or not at all: one bad field refuses it."""
    raw = {**snapshot_to_jsonb(_snapshot()), field: value}

    read = parse_catalogue_snapshot(raw)

    assert isinstance(read, InvalidSnapshot)
    assert read.reason == reason


@pytest.mark.parametrize(
    "raw",
    [None, [SEARCH], {"tools": [SEARCH]}, {"version": 3, "generation": 9}],
    ids=["absent", "legacy-list", "legacy-dict", "future-version"],
)
def test_only_a_version_2_envelope_declares_a_generation(raw: object) -> None:
    from src.infrastructure.mcp.catalogue_snapshot import stored_generation

    assert stored_generation(raw) is None
    assert stored_generation(snapshot_to_jsonb(_snapshot(generation=11))) == 11
