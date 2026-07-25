"""Coordinate extraction — the shared entry point of every geo tool.

``extract_coordinates`` normalizes the three naming conventions the geo
providers use (``lat``/``lon``, ``latitude``/``longitude``, Google's ``lng``)
and is the single reader for routes and places. Whatever it drops, the caller
never sees: `get_route_tool` falls back to the textual address, and the
proximity search gives up on the user's position.

The trap it used to carry is the classic falsy zero. Latitude 0 (the equator)
and longitude 0 (the prime meridian) are ordinary coordinates — Greenwich,
Accra, Tamanrasset — but ``a or b`` treats them as absent, so the value was
silently replaced by the next key, then by ``None``.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest

from src.domains.agents.tools.runtime_helpers import (
    extract_cache_metadata,
    extract_coordinates,
    parse_user_id,
)

pytestmark = pytest.mark.unit


@dataclass
class _ShortNameLocation:
    """A location object using the shorthand attribute names."""

    lat: float | None
    lon: float | None


@dataclass
class _GoogleStyleLocation:
    """A location object using Google's `lng` spelling."""

    lat: float | None
    lng: float | None


@dataclass
class _FullNameLocation:
    """A location object using the full attribute names."""

    latitude: float | None
    longitude: float | None


class TestExtractCoordinatesNamingConventions:
    """The three spellings a provider may use."""

    @pytest.mark.parametrize(
        "location",
        [
            {"lat": 48.8566, "lon": 2.3522},
            {"latitude": 48.8566, "longitude": 2.3522},
            {"lat": 48.8566, "lng": 2.3522},
            {"lat": 48.8566, "lon": 2.3522, "extra": "ignored"},
        ],
    )
    def test_reads_every_supported_dict_spelling(self, location: dict[str, Any]) -> None:
        assert extract_coordinates(location) == (48.8566, 2.3522)

    def test_prefers_the_shorthand_key_when_both_are_present(self) -> None:
        assert extract_coordinates({"lat": 1.0, "latitude": 9.0, "lon": 2.0, "longitude": 8.0}) == (
            1.0,
            2.0,
        )

    @pytest.mark.parametrize(
        "location",
        [
            _ShortNameLocation(lat=48.8566, lon=2.3522),
            _GoogleStyleLocation(lat=48.8566, lng=2.3522),
            _FullNameLocation(latitude=48.8566, longitude=2.3522),
        ],
    )
    def test_reads_every_supported_object_shape(self, location: object) -> None:
        assert extract_coordinates(location) == (48.8566, 2.3522)


class TestExtractCoordinatesAtTheOrigin:
    """Zero is a coordinate, not a missing value."""

    @pytest.mark.parametrize(
        ("location", "expected"),
        [
            ({"lat": 0.0, "lon": 2.3522}, (0.0, 2.3522)),
            ({"lat": 51.4779, "lon": 0.0}, (51.4779, 0.0)),
            ({"lat": 0.0, "lon": 0.0}, (0.0, 0.0)),
            ({"latitude": 0.0, "longitude": 0.0}, (0.0, 0.0)),
            ({"lat": 5.6037, "lng": 0.0}, (5.6037, 0.0)),
            ({"lat": 0, "lon": 0}, (0, 0)),
        ],
    )
    def test_keeps_a_zero_coordinate_from_a_dict(
        self, location: dict[str, Any], expected: tuple[float, float]
    ) -> None:
        assert extract_coordinates(location) == expected

    @pytest.mark.parametrize(
        ("location", "expected"),
        [
            (_ShortNameLocation(lat=0.0, lon=0.0), (0.0, 0.0)),
            (_GoogleStyleLocation(lat=0.0, lng=0.0), (0.0, 0.0)),
            (_FullNameLocation(latitude=0.0, longitude=0.0), (0.0, 0.0)),
        ],
    )
    def test_keeps_a_zero_coordinate_from_an_object(
        self, location: object, expected: tuple[float, float]
    ) -> None:
        assert extract_coordinates(location) == expected

    def test_a_zero_longitude_is_not_replaced_by_the_other_spelling(self) -> None:
        # `lon=0.0` must win over `lng=99.0`: falling through was the defect.
        assert extract_coordinates({"lat": 51.4779, "lon": 0.0, "lng": 99.0}) == (51.4779, 0.0)


class TestExtractCoordinatesAbsentValues:
    """Genuinely missing coordinates still come back as None."""

    @pytest.mark.parametrize(
        "location",
        [
            None,
            {},
            {"name": "Paris"},
            {"lat": None, "lon": None},
        ],
    )
    def test_returns_none_when_there_is_no_coordinate(self, location: Any) -> None:
        assert extract_coordinates(location) == (None, None)

    def test_returns_a_partial_pair_when_only_one_axis_is_present(self) -> None:
        assert extract_coordinates({"lat": 48.8566}) == (48.8566, None)
        assert extract_coordinates({"lon": 2.3522}) == (None, 2.3522)

    def test_returns_none_for_an_object_without_coordinate_attributes(self) -> None:
        assert extract_coordinates(object()) == (None, None)

    def test_falls_back_to_lng_only_when_lon_is_truly_absent(self) -> None:
        assert extract_coordinates(_GoogleStyleLocation(lat=1.0, lng=2.0)) == (1.0, 2.0)


class TestParseUserId:
    """Every id shape LangGraph may inject."""

    def test_returns_a_uuid_object_untouched(self) -> None:
        value = uuid4()
        assert parse_user_id(value) is value

    def test_parses_a_canonical_uuid_string(self) -> None:
        assert parse_user_id("12345678-1234-1234-1234-123456789012") == UUID(
            "12345678-1234-1234-1234-123456789012"
        )

    def test_parses_a_hyphenless_uuid_string(self) -> None:
        assert parse_user_id("12345678123412341234123456789012") == UUID(
            "12345678-1234-1234-1234-123456789012"
        )

    def test_parses_a_ulid_deterministically(self) -> None:
        first = parse_user_id("01JA9XWN11N3J3BM0GZNB9FZKM")
        second = parse_user_id("01JA9XWN11N3J3BM0GZNB9FZKM")
        assert isinstance(first, UUID)
        assert first == second

    @pytest.mark.parametrize("value", ["", "not-an-id", "0" * 31, "01JA9XWN11N3J3BM0GZNB9FZK"])
    def test_rejects_what_it_cannot_parse(self, value: str) -> None:
        with pytest.raises(ValueError):
            parse_user_id(value)


class TestExtractCacheMetadata:
    """Cache provenance surfaced to the user must not be invented."""

    def test_reads_both_fields_when_present(self) -> None:
        assert extract_cache_metadata(
            {"from_cache": True, "cached_at": "2026-07-25T10:00:00Z", "items": []}
        ) == (True, "2026-07-25T10:00:00Z")

    def test_defaults_to_a_fresh_result_with_no_timestamp(self) -> None:
        assert extract_cache_metadata({"items": []}) == (False, None)

    def test_never_fabricates_a_timestamp_for_a_cache_hit(self) -> None:
        # A hit without `cached_at` stays without one — the connector parity
        # contract forbids inventing "cached just now".
        assert extract_cache_metadata({"from_cache": True}) == (True, None)
