"""Home provenance, bounded edits and source reconciliation without a provider."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.domains.world.home import (
    HomePreferences,
    HomeUpdate,
    project_home,
    read_home_preferences,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra", [{"automatic": False}, {"placements": [{"anchor": "desk", "motif": "books"}]}]
)
def test_palette_writes_reject_retired_decoration_fields(extra: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        HomeUpdate.model_validate({"expected_revision": 0, "palette": "sage", **extra})


def test_palette_projection_uses_the_explicit_colour_or_application_theme() -> None:
    original = project_home(HomePreferences(), "ocean")
    changed = project_home(HomePreferences(palette="amber"), "ocean")
    assert original.model_dump() == {"automatic_palette": "teal", "palette": "teal"}
    assert changed.model_dump() == {"automatic_palette": "teal", "palette": "amber"}
    assert project_home(HomePreferences(), "unknown").palette == "clay"


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_revision": 0, "placements": [{"anchor": "other-user-home", "motif": "books"}]},
        {
            "expected_revision": 0,
            "placements": [
                {"anchor": "desk", "motif": "books"},
                {"anchor": "desk", "motif": "nature"},
            ],
        },
        {"expected_revision": True},
        {"expected_revision": -1},
        {"expected_revision": 0, "owner_id": "other"},
        {"expected_revision": 0, "palette": "javascript:alert(1)"},
    ],
)
def test_invalid_edit_never_reaches_a_persistence_transition(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        HomeUpdate.model_validate(payload)


def test_corrupt_preferences_never_silently_reenable_automatic_sources() -> None:
    preferences, needs_reset = read_home_preferences({"version": 200, "automatic": False})
    assert needs_reset and preferences == HomePreferences()
    with pytest.raises(ValidationError):
        HomeUpdate(expected_revision=0, reset=True, palette="teal")


def test_client_catalogue_and_server_vocabulary_cannot_drift() -> None:
    from src.domains.world import home

    catalogue = json.loads((Path(home.__file__).parent / "assets/home-v1.json").read_text())
    assert set(catalogue) == {"version", "palettes"}
    for palette in catalogue["palettes"]:
        HomeUpdate(expected_revision=0, palette=palette)
