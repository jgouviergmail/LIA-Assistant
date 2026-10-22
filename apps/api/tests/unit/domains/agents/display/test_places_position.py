"""Selected places become one display aggregate, never model/registry facts."""

import copy
import json
import re
from html import unescape

import pytest

from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.display.places_position import (
    project_positions,
    render_positions,
)

pytestmark = pytest.mark.unit


def place(identity="one", location=None, **extra):
    return RegistryItem(
        id=f"place_{identity}",
        type=RegistryItemType.PLACE,
        payload={
            "id": identity,
            "displayName": {"text": f"Place {identity}"},
            "location": location,
            **extra,
        },
        meta=RegistryItemMeta(source="google_places", domain="places"),
    )


@pytest.mark.parametrize(
    "location,expected",
    [
        ({"lat": 0, "lon": 0}, (0, 0)),
        ({"latitude": 48.1, "longitude": -179.9}, (48.1, -179.9)),
        ({"latitude": 91, "longitude": 2}, None),
        ({"lat": False, "lon": 0}, None),
        ({"lat": float("nan"), "lon": 0}, None),
        ({"lat": float("inf"), "lon": 0}, None),
        ({"lat": 10**1000, "lon": 0}, None),
        ({"lat": 1}, None),
        (None, None),
    ],
)
def test_coordinates_are_exact_or_explicitly_unlocated(location, expected):
    source = {"one": place(location=location)}
    before = copy.deepcopy(source)
    result = project_positions(source)
    assert result is not None
    point = result.places[0].position
    assert ((point.lat, point.lng) if point else None) == expected
    assert result.unlocated_count == int(expected is None)
    if expected is not None:
        assert source == before


def test_deduplicates_identity_but_keeps_coincident_places_and_complete_fallback():
    a, b = place("a", {"lat": 0, "lon": 179.9}), place("b", {"lat": 0, "lon": 179.9})
    registry = {"a": a, "copy": a.model_copy(deep=True), "b": b}
    projection = project_positions(registry)
    assert len(projection.places) == 2
    html = render_positions(registry, language="fr")
    assert html.count('class="lia-place-position"') == 1
    assert "Position" in html and "Place a" in html and "Place b" in html
    wire = re.search(r'data-place-position="([^"]+)"', html).group(1)
    assert json.loads(unescape(wire))["version"] == 2
    assert "api_key" not in html


def test_empty_selection_does_not_resurrect_reference_places():
    references = {"items": [{"place_id": "old", "name": "Old", "location": {"lat": 0, "lon": 0}}]}
    assert render_positions({}, resolved=references, language="en") == ""
    assert "Old" in render_positions(None, resolved=references, language="en")


def test_position_header_remains_html_when_appended_to_a_markdown_answer():
    html = render_positions({"one": place(location={"lat": 0, "lon": 0})}, language="fr")
    assert "\n" not in html
    assert '<div class="lia-card-top__title">Position</div>' in html


def test_bounds_wire_but_keeps_every_selected_place_in_static_fallback():
    registry = {str(i): place(str(i), {"lat": 1, "lon": 2}) for i in range(80)}
    projection = project_positions(registry)
    assert projection.omitted_count > 0
    assert len(projection.places) + projection.omitted_count == 80
    html = render_positions(registry, language="en")
    assert "Place 79" in html


def test_source_text_and_links_cannot_become_executable_html():
    value = place("<script>", {"lat": 0, "lon": 0}, name='<img src=x onerror="alert(1)">')
    html = render_positions({"one": value}, language="fr")
    assert "<script>" not in html and "<img src=x" not in html
    assert 'href="javascript:' not in html


@pytest.mark.parametrize(
    "facts",
    [
        {
            "formattedAddress": "1 Main Street",
            "rating": "4.5",
            "userRatingCount": 0,
            "internationalPhoneNumber": "+33 1 23 45 67 89",
            "websiteUri": "https://example.test/?a=1&b=2",
            "currentOpeningHours": {"weekdayDescriptions": ["Monday: 09:00–18:00"]},
        },
        {
            "address": "1 Main Street",
            "rating": 4.5,
            "reviews_count": 0,
            "phone": "+33 1 23 45 67 89",
            "website": "https://example.test/?a=1&b=2",
            "opening_hours": ["Monday: 09:00–18:00"],
        },
    ],
)
def test_projects_only_already_acquired_place_facts_without_changing_the_source(facts):
    registry = {"one": place(location={"lat": 0, "lon": 0}, **facts)}
    before = copy.deepcopy(registry)
    result = project_positions(registry)
    assert result.version == 2
    assert result.places[0].details.model_dump() == {
        "address": "1 Main Street",
        "rating": 4.5,
        "reviews_count": 0,
        "phone": "+33 1 23 45 67 89",
        "website": "https://example.test/?a=1&b=2",
        "opening_hours": ["Monday: 09:00–18:00"],
    }
    assert registry == before


@pytest.mark.parametrize(
    "website",
    [
        "javascript:alert(1)",
        "mailto:test@example.test",
        "https://user:password@example.test",
        "https://user@example.test",
        "https://example.test\\@evil.test",
        "https://example.test/\npath",
        "https:///missing-host",
        "https://example.test:invalid",
        "https://example.test:65536",
    ],
)
def test_optional_invalid_facts_are_absent_instead_of_discarding_the_map(website):
    result = project_positions(
        {"one": place(website=website, rating=True, reviews_count=-1, phone={"raw": "tree"})}
    )
    assert result.places[0].details.model_dump() == {
        "address": None,
        "rating": None,
        "reviews_count": None,
        "phone": None,
        "website": None,
        "opening_hours": [],
    }


def test_bounds_details_and_keeps_home_coordinates_and_provider_trees_out_of_archives():
    registry = {
        "one": place(
            address="A" * 1200,
            phone="1" * 200,
            website="https://example.test/" + "a" * 4096,
            reviews_count=10**100,
            opening_hours=[None, {"raw": "tree"}, ""] + ["H" * 600 for _ in range(9)],
            home_location={"lat": 12.345, "lon": 67.89},
            photos=[{"name": "private-provider-photo"}],
        )
    }
    details = project_positions(registry).places[0].details
    assert len(details.address) == 1000
    assert len(details.phone) == 128
    assert details.website is None and details.reviews_count is None
    assert details.opening_hours == ["H" * 500] * 7
    html = render_positions(registry, language="en")
    assert "home_location" not in html and "12.345" not in html
    assert "private-provider-photo" not in html


def test_details_text_stays_data_inside_the_escaped_archive():
    dangerous = '<img src=x onerror="alert(1)">'
    html = render_positions(
        {"one": place(address=dangerous, opening_hours=[dangerous])}, language="en"
    )
    assert dangerous not in html
    wire = re.search(r'data-place-position="([^"]+)"', html).group(1)
    details = json.loads(unescape(wire))["places"][0]["details"]
    assert details["address"] == dangerous and details["opening_hours"] == [dangerous]


def test_archive_budget_removes_details_from_the_end_without_losing_places_or_coordinates():
    registry = {
        str(index): place(
            str(index),
            {"lat": index, "lon": index},
            address="界" * 1000,
            website="https://example.test/" + "a" * 4000,
            opening_hours=["界" * 500] * 7,
        )
        for index in range(64)
    }
    result = project_positions(registry)
    wire = json.dumps(result.model_dump(mode="json"), ensure_ascii=True, separators=(",", ":"))
    assert len(wire) <= 512 * 1024
    assert len(result.places) == 64
    assert result.omitted_count == 0
    assert result.places[0].details is not None and result.places[-1].details is None
    for index, projected in enumerate(result.places):
        assert projected.ref == str(index)
        assert projected.position.lat == index and projected.position.lng == index
        assert projected.url.startswith("https://www.google.com/maps/place/")


def test_non_google_or_non_place_item_cannot_trigger_a_position_card():
    item = place(location={"lat": 0, "lon": 0})
    item.meta.source = "mcp_untrusted"
    assert project_positions({"one": item}) is None


def test_reference_place_rehydrated_before_selection_keeps_its_map():
    item = place(location={"lat": 0, "lon": 0})
    item.meta.source = "resolved_context"
    assert len(project_positions({"one": item}).places) == 1


def test_missing_provider_id_uses_a_search_link_never_a_registry_hash_as_place_id():
    item = place(location={"lat": 0, "lon": 0})
    item.payload.pop("id")
    assert "/maps/search/" in project_positions({"one": item}).places[0].url


@pytest.mark.parametrize("mode", ["cards", "html_cards", "html", "markdown"])
def test_actual_selected_response_and_history_have_one_host_map_without_geometry_tokens(
    monkeypatch,
    mode,
):
    from importlib import import_module

    from langchain_core.messages import AIMessage

    from src.domains.agents.display.sentinel_filter import strip_widget_sentinels

    response_node = import_module("src.domains.agents.nodes.response_node")
    from src.domains.agents.nodes.react_history import neutralize_widget_sentinels

    first, other = place("a", {"lat": 0, "lon": 179.9}), place("b", {"lat": 1, "lon": -179.9})
    registry = {
        first.id: first.model_dump(mode="json"),
        other.id: other.model_dump(mode="json"),
    }
    content, selected = response_node._apply_relevant_ids_filtering(
        final_content=f"Retained <relevant_ids>{first.id}</relevant_ids>",
        original_content="",
        current_turn_registry=registry,
        state={},
        result_domains={"places"},
        last_user_message="places",
        run_id="position-test",
        require_selection=True,
    )
    monkeypatch.setattr(
        response_node, "generate_html_for_registry", lambda **_: "<p>SOURCE_CARDS</p>"
    )
    result = response_node._render_response_html(
        final_content=content,
        current_turn_registry=selected,
        resolved_context_for_html=None,
        user_display_mode=mode,
        user_viewport="mobile",
        user_language="en",
        user_timezone="UTC",
        run_id="position-test",
    )
    assert "Place a" in result and "Place b" not in result
    assert result.count('class="lia-place-position"') == 1
    assert result.index('class="lia-place-position"') < result.index("Retained")
    if mode in {"cards", "html_cards"}:
        assert result.index('class="lia-place-position"') < result.index("SOURCE_CARDS")
    else:
        assert "SOURCE_CARDS" not in result
    historical = neutralize_widget_sentinels([AIMessage(content=result)])[0].content
    assert "data-place-position" not in historical and "179.9" not in historical
    assert ("SOURCE_CARDS" in historical) is (mode in {"cards", "html_cards"})
    assert (
        strip_widget_sentinels(
            '<div class="lia-place-position" data-place-position="forged">BAD</div>Safe'
        )[0]
        == "Safe"
    )
