"""Finite public appearance, explicit consent and safe private preference recovery."""

import pytest
from pydantic import ValidationError

from src.domains.world.avatar import (
    AvatarAppearance,
    AvatarPreferences,
    AvatarUpdate,
    public_world_name,
    read_avatar_preferences,
)


def test_public_name_uses_only_the_native_name_and_a_neutral_fallback() -> None:
    assert public_world_name("  E\u0301loïse\u202e  Martin ") == "Éloïse Martin"
    assert public_world_name(None, "en") == "LIA explorer"
    assert public_world_name(" \n\u202e ", "en") == "LIA explorer"
    assert len(public_world_name("🌻" * 40)) == 24
    assert public_world_name("A" * 40) == "A" * 24


@pytest.mark.parametrize(
    "language,expected",
    [
        ("fr", "Explorateur LIA"),
        ("de", "LIA-Entdecker"),
        ("es", "Explorador LIA"),
        ("it", "Esploratore LIA"),
        ("zh", "LIA 探索者"),
    ],
)
def test_missing_public_name_uses_the_account_language(language: str, expected: str) -> None:
    assert public_world_name(None, language) == expected
    assert public_world_name(" \u202e ", language) == expected
    assert public_world_name("Éloïse", language) == "Éloïse"


@pytest.mark.parametrize(
    "patch",
    [
        {"hair": "https://example.invalid/a"},
        {"hair_color": "#123456"},
        {"outfit": "admin"},
        {"headwear": "<script>"},
        {"glasses": "true"},
        {"version": True},
        {"version": 2},
        {"profile": "PRIVATE"},
    ],
)
def test_public_appearance_refuses_unregistered_and_coerced_content(
    patch: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AvatarAppearance.model_validate({**AvatarAppearance().model_dump(), **patch})


def test_appearance_has_one_explicit_public_shape_and_is_immutable() -> None:
    value = AvatarAppearance(hair="mohawk", hair_color="blue", outfit="suit", glasses=True)
    assert set(value.model_dump()) == {
        "version",
        "skin",
        "hair",
        "hair_color",
        "outfit",
        "outfit_color",
        "headwear",
        "headwear_color",
        "glasses",
    }
    assert AvatarAppearance.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        value.hair = "bald"


@pytest.mark.parametrize("consent", [False, 1, "true", None])
def test_avatar_publication_requires_literal_consent(consent: object) -> None:
    with pytest.raises(ValidationError):
        AvatarUpdate.model_validate({"expected_revision": 0, "appearance": {}, "consent": consent})


def test_private_preferences_recover_without_exposing_unknown_content() -> None:
    preferences, reset = read_avatar_preferences(None)
    assert preferences == AvatarPreferences()
    assert not reset
    for invalid in [{"version": 999, "private_memory": "SECRET"}, {"revision": -1}, []]:
        preferences, reset = read_avatar_preferences(invalid)
        assert reset
        assert preferences == AvatarPreferences()
        assert "SECRET" not in preferences.model_dump_json()
    stored = AvatarPreferences(revision=3, appearance=AvatarAppearance(hair="long"))
    assert read_avatar_preferences(stored.model_dump()) == (stored, False)


def test_public_catalogue_matches_the_strict_backend_vocabulary() -> None:
    import json
    from pathlib import Path

    import src.domains.world.avatar as avatar_module

    catalogue = json.loads(
        (Path(avatar_module.__file__).parent / "assets/avatar-v1.json").read_text(encoding="utf-8")
    )
    assert catalogue["defaults"] == AvatarAppearance().model_dump(mode="json")
    fields = AvatarAppearance.model_json_schema()["properties"]
    for field, key in [
        ("hair", "hair"),
        ("skin", "skins"),
        ("outfit", "outfits"),
        ("headwear", "headwear"),
        ("hair_color", "colors"),
        ("outfit_color", "colors"),
        ("headwear_color", "colors"),
    ]:
        assert fields[field]["enum"] == catalogue[key]
