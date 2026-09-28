"""LocationCard speaks the reader's language where it used to fix one (ADR-323).

The map image is the link's only content, so its alt text is the link's name —
it read « Location map » in six languages; and a place known only by its
coordinates was titled « Position » whatever the reader's language.
"""

from __future__ import annotations

import pytest

from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.location_card import LocationCard

pytestmark = pytest.mark.unit

_MAP = "/api/v1/connectors/google-location/static-map?lat=48.8584&lng=2.2945"


@pytest.fixture
def card() -> LocationCard:
    return LocationCard()


def test_the_map_link_is_named_in_the_reader_s_language(card: LocationCard) -> None:
    data = {"locality": "Paris", "latitude": 48.8584, "longitude": 2.2945, "static_map_url": _MAP}

    html = card.render(data, RenderContext(language="de"), with_wrapper=False)

    assert f'alt="{V3Messages.get_open_in_maps("de")}"' in html
    assert "Location map" not in html


def test_a_place_known_by_its_coordinates_is_titled_in_the_reader_s_language(
    card: LocationCard,
) -> None:
    html = card.render(
        {"latitude": 48.8584, "longitude": 2.2945}, RenderContext(language="it"), with_wrapper=False
    )

    assert V3Messages.get_position("it") in html
    assert V3Messages.get_position("it") != V3Messages.get_position("en")
