"""The map tile sources a page the model writes may load (ADR-370 amendment 2026-11-12).

A source's origin goes into a content policy and its pattern into a prompt: both
are read by something that takes them literally, so the table is held to the
shape those two readers need.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

import pytest

from src.core.constants import INTERACTIVE_PAGE_MAP_PROVIDERS_DEFAULT
from src.core.map_tile_providers import (
    MAP_TILE_PROVIDERS,
    map_tile_providers,
    parse_map_provider_keys,
)

pytestmark = pytest.mark.unit

_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
#: What a policy source may hold: a scheme, a host, nothing a policy would read as syntax.
_ORIGIN = re.compile(r"^https://[a-z0-9.-]+$")


class TestTheTable:
    def test_is_not_empty(self) -> None:
        assert MAP_TILE_PROVIDERS

    @pytest.mark.parametrize("key", list(MAP_TILE_PROVIDERS))
    def test_a_source_is_keyed_by_its_own_key(self, key: str) -> None:
        assert MAP_TILE_PROVIDERS[key].key == key
        assert _KEY.match(key)

    @pytest.mark.parametrize("key", list(MAP_TILE_PROVIDERS))
    def test_a_pattern_is_https_and_names_the_three_tile_tokens(self, key: str) -> None:
        pattern = MAP_TILE_PROVIDERS[key].url_template
        assert pattern.startswith("https://")
        for token in ("{z}", "{x}", "{y}"):
            assert pattern.count(token) == 1
        # Nothing else is left to fill: the writer reads the pattern as it is.
        assert set(re.findall(r"\{[^}]*\}", pattern)) == {"{z}", "{x}", "{y}"}

    @pytest.mark.parametrize("key", list(MAP_TILE_PROVIDERS))
    def test_the_origin_is_the_pattern_s_host_and_nothing_a_policy_would_parse(
        self, key: str
    ) -> None:
        provider = MAP_TILE_PROVIDERS[key]
        parts = urlsplit(provider.url_template)
        assert provider.origin == f"{parts.scheme}://{parts.netloc}"
        assert _ORIGIN.match(provider.origin)

    @pytest.mark.parametrize("key", list(MAP_TILE_PROVIDERS))
    def test_a_source_has_a_name_a_credit_and_a_zoom_range(self, key: str) -> None:
        provider = MAP_TILE_PROVIDERS[key]
        assert provider.label.strip()
        assert provider.credit.strip()
        assert 0 <= provider.min_zoom < provider.max_zoom <= 22

    @pytest.mark.parametrize(
        ("host", "why"),
        [
            ("tile.openstreetmap.org", "serves « access blocked » to a browser with no referrer"),
            ("cartocdn.com", "serves « API key required » to everyone"),
        ],
    )
    def test_no_source_is_a_host_measured_to_refuse_the_page(self, host: str, why: str) -> None:
        """Both answered 200 with an image, and neither image was a map.

        Chromium sends no referrer from the page's frame, whatever the page asks,
        and no key may sit in a page. Read on a person's browser, 2026-11-12: a
        source enters this table on what a real browser is SHOWN, never on a status.
        """
        for provider in MAP_TILE_PROVIDERS.values():
            assert host not in provider.url_template, why

    def test_no_line_of_the_prompt_can_be_broken_by_a_source(self) -> None:
        """A source is rendered on ONE line of cells separated by a bar."""
        for provider in MAP_TILE_PROVIDERS.values():
            for cell in (provider.label, provider.url_template, provider.credit):
                assert "\n" not in cell
                assert "|" not in cell


class TestTheDefault:
    def test_names_declared_sources_only(self) -> None:
        assert set(INTERACTIVE_PAGE_MAP_PROVIDERS_DEFAULT) <= set(MAP_TILE_PROVIDERS)


class TestParse:
    def test_reads_a_comma_separated_spelling(self) -> None:
        first, second = list(MAP_TILE_PROVIDERS)[:2]
        assert parse_map_provider_keys(f" {second.upper()} , {first} ") == [first, second]

    def test_keeps_the_table_s_order_and_drops_a_duplicate(self) -> None:
        first, second = list(MAP_TILE_PROVIDERS)[:2]
        assert parse_map_provider_keys([second, first, second]) == [first, second]

    @pytest.mark.parametrize("empty", ["", " , ", []])
    def test_an_empty_list_allows_no_source(self, empty: str | list[str]) -> None:
        assert parse_map_provider_keys(empty) == []

    def test_refuses_a_source_nobody_declared_and_names_the_declared_ones(self) -> None:
        (declared,) = list(MAP_TILE_PROVIDERS)[:1]
        with pytest.raises(ValueError) as refused:
            parse_map_provider_keys(f"{declared},some_unknown_source")
        assert "some_unknown_source" in str(refused.value)
        for key in MAP_TILE_PROVIDERS:
            assert key in str(refused.value)


class TestRead:
    def test_gives_the_sources_in_the_table_s_order(self) -> None:
        first, second = list(MAP_TILE_PROVIDERS)[:2]
        assert [provider.key for provider in map_tile_providers([second, first])] == [first, second]

    def test_gives_nothing_for_no_key(self) -> None:
        assert map_tile_providers([]) == ()
