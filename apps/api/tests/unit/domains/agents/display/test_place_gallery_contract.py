"""Paid photo data reaches the reader with its authors, without entering model data."""

import json

import pytest

from src.core.config import settings
from src.core.field_names import FIELD_DISPLAY_ONLY
from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.place_card import PlaceCard
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.places_formatting import _format_place, format_place_details

pytestmark = pytest.mark.unit


class PlaceOutput(ToolOutputMixin):
    tool_name = "test_photo_output"
    operation = "search"


@pytest.mark.parametrize("formatter", [_format_place, format_place_details])
@pytest.mark.parametrize("enabled", [False, True])
def test_photos_and_authors_survive_the_real_registry_round_trip(monkeypatch, formatter, enabled):
    monkeypatch.setattr(settings, "place_carousel_enabled", enabled)
    raw = {
        "id": "test-place",
        "displayName": {"text": "Terrace"},
        "photos": [
            {
                "name": f"places/test/photos/photo{i}",
                "authorAttributions": [
                    {"displayName": f"AUTHOR_{i}", "uri": f"https://example.test/author{i}"}
                ],
            }
            for i in range(3)
        ],
    }
    normalized = formatter(raw, language="en")
    gallery = normalized[FIELD_DISPLAY_ONLY]["photo_gallery"]
    assert len(gallery) == (3 if enabled else 1)
    assert gallery[0]["authors"] == [{"name": "AUTHOR_0", "url": "https://example.test/author0"}]
    output = PlaceOutput().build_places_output([normalized], query="test")
    snapshot = output.model_dump(mode="json")
    model = json.dumps(snapshot["structured_data"])
    assert "photo_gallery" not in model
    item = next(iter(output.registry_updates.values()))
    restored = RegistryItem.model_validate(json.loads(item.model_dump_json()))
    markup = PlaceCard().render(card_payload(restored), RenderContext(language="en"))
    assert "lia-place__photo" in markup
    assert "data-place-photos=" in markup
    assert "AUTHOR_0" in markup
    assert "Google Maps" in markup


@pytest.mark.parametrize(
    "photos", [None, "malformed", [None, {"name": ""}, {"name": {"secret": "tree"}}]]
)
def test_malformed_optional_photos_do_not_drop_the_place(photos):
    data = _format_place(
        {"id": "place", "displayName": {"text": "KEPT_PLACE"}, "photos": photos}, language="en"
    )
    markup = PlaceCard().render(data, RenderContext(language="en"))
    assert "KEPT_PLACE" in markup
    assert "secret" not in markup


def test_photo_authors_are_escaped_and_unsafe_author_links_remain_plain(monkeypatch):
    monkeypatch.setattr(settings, "place_carousel_enabled", True)
    data = {
        "name": "Place",
        "photo_url": "/photo.png",
        "photo_gallery": [
            {
                "url": "/photo.png",
                "authors": [{"name": "<script>AUTHOR</script>", "url": "javascript:alert(1)"}],
            }
        ],
    }
    markup = PlaceCard().render(data, RenderContext(language="en"))
    assert "&lt;script&gt;AUTHOR&lt;/script&gt;" in markup
    assert 'href="javascript:' not in markup
    assert "<script>" not in markup


def test_individual_photo_source_and_author_avatar_reach_the_caption():
    normalized = _format_place(
        {
            "id": "place",
            "displayName": {"text": "Place"},
            "photos": [
                {
                    "name": "places/place/photos/one",
                    "googleMapsUri": "https://maps.google.com/photo-one",
                    "authorAttributions": [
                        {
                            "displayName": "Author",
                            "uri": "https://maps.google.com/author",
                            "photoUri": "https://example.test/author-avatar.jpg",
                        }
                    ],
                }
            ],
        },
        language="fr",
    )
    output = PlaceOutput().build_places_output([normalized])
    item = next(iter(output.registry_updates.values()))
    projected = card_payload(item)
    assert projected is not None
    markup = PlaceCard().render(projected, RenderContext(language="fr"))
    assert "https://maps.google.com/photo-one" in markup
    assert "https://example.test/author-avatar.jpg" in markup
    assert 'translate="no"' in markup


@pytest.mark.parametrize(
    "url", ["mailto:owner@example.test", "tel:123", "/\\evil.test/x", "https:\\evil.test/x"]
)
def test_non_image_protocols_and_backslashes_are_not_photo_sources(url):
    data = {"name": "KEPT_PLACE", "photo_gallery": [{"url": url, "authors": []}]}
    markup = PlaceCard().render(data, RenderContext(language="en"))
    assert "KEPT_PLACE" in markup
    assert "data-place-photos=" not in markup
