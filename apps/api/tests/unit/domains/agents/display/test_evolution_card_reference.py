"""Browser fixtures must remain exact native output, including host metadata."""

import json
from pathlib import Path

import pytest

from tests.helpers.evolution_card_reference import evolution_cards

pytestmark = pytest.mark.unit


def test_browser_fixture_matches_native_producers():
    path = Path(__file__).with_name("evolution_card_reference.json")
    assert json.loads(path.read_text(encoding="utf-8")) == evolution_cards()
