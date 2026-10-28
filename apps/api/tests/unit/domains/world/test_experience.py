"""Experience defaults, strict edits and explicit repair without private projection."""

import pytest
from pydantic import ValidationError

from src.domains.users.user_column_map import USER_COLUMNS, UserColumnClass
from src.domains.world.experience import (
    ExperiencePreferences,
    ExperienceUpdate,
    read_experience_preferences,
)
from src.domains.world.schemas import PublicActor

pytestmark = pytest.mark.unit


def test_experience_defaults_do_not_rewrite_storage() -> None:
    preferences, reset = read_experience_preferences(None)
    assert not reset
    assert preferences == ExperiencePreferences()
    assert preferences.show_route is True
    assert preferences.season_mode == "calendar"
    assert preferences.hemisphere == "north"


def test_the_persisted_document_is_exactly_the_five_supported_fields() -> None:
    document = ExperiencePreferences(revision=3, show_route=False).model_dump(mode="json")
    assert document == {
        "version": 1,
        "revision": 3,
        "show_route": False,
        "season_mode": "calendar",
        "hemisphere": "north",
    }
    assert read_experience_preferences(document) == (
        ExperiencePreferences.model_validate(document),
        False,
    )


@pytest.mark.parametrize(
    "raw",
    [
        {"version": 2},
        {"version": True},
        {"show_route": "false"},
        {"unknown": "private"},
        {"revision": -1},
        {"revision": True},
        {"season_mode": "rain"},
        {"hemisphere": "east"},
        # The retired introduction's fields: unsupported storage, explicit repair.
        {"tutorial_version": 1},
        {"tutorial_status": "completed"},
        {
            "version": 1,
            "revision": 4,
            "show_route": True,
            "tutorial_version": 1,
            "tutorial_status": "dismissed",
            "season_mode": "calendar",
            "hemisphere": "north",
        },
        [],
        "invalid",
    ],
)
def test_experience_unknown_fields_and_versions_require_repair(raw: object) -> None:
    preferences, reset = read_experience_preferences(raw)
    assert reset and preferences == ExperiencePreferences()


@pytest.mark.parametrize(
    "edit",
    [
        {"owner_id": "other"},
        {"show_route": 0},
        {"tutorial_status": "completed"},
        {"tutorial_version": 1},
        {"expected_revision": True},
        {"expected_revision": 2**31 - 1},
        {"reset": True, "show_route": False},
        {"reset": True, "season_mode": "off"},
    ],
)
def test_experience_invalid_edits_cannot_reach_persistence(edit: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ExperienceUpdate.model_validate({"expected_revision": 0, **edit})


def test_experience_is_private_exported_and_erased() -> None:
    assert USER_COLUMNS["world_experience_preferences"] is UserColumnClass.SCRUBBED_PREFERENCE
    assert "world_experience_preferences" not in PublicActor.model_fields
    assert "show_route" not in PublicActor.model_fields
