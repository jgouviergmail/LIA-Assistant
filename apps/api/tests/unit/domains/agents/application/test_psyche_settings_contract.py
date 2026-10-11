"""Psyche updates are exact sparse source values, never null, coercions or another owner."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.psyche_catalogue import PSYCHE_SETTINGS_OPERATION
from src.domains.agents.application.psyche_settings_schemas import (
    PsycheSettingField,
    PsycheSettingsPatch,
)
from src.domains.psyche.schemas import PsycheSettingsResponse, PsycheSettingsUpdate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"psyche_enabled": None},
        {"psyche_enabled": "false"},
        {"psyche_sensitivity": True},
        {"psyche_sensitivity": 101},
        {"psyche_stability": -1},
        {"user_id": "other"},
    ],
)
def test_psyche_settings_never_serialize_unapproved_defaults_or_bad_values(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        PsycheSettingsPatch.model_validate(payload)


def test_future_psyche_settings_require_reviewed_confirmation_and_sync_fields() -> None:
    assert (
        set(PsycheSettingsPatch.model_fields)
        == set(PsycheSettingsUpdate.model_fields)
        == set(PsycheSettingsResponse.model_fields)
        == {field.value for field in PsycheSettingField}
    )
    assert PsycheSettingsPatch(psyche_stability=0).model_dump(exclude_unset=True) == {
        "psyche_stability": 0
    }


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_psyche_confirmation_and_editor_show_exact_source_values(language: str) -> None:
    patch = PsycheSettingsPatch(
        psyche_enabled=False,
        psyche_display_avatar=False,
        psyche_sensitivity=0,
        psyche_stability=100,
    )
    before = {
        "psyche_enabled": True,
        "psyche_display_avatar": True,
        "psyche_sensitivity": 50,
        "psyche_stability": 50,
    }
    draft = build_action_content(
        uuid4(),
        PSYCHE_SETTINGS_OPERATION,
        patch,
        before,
        patch.model_dump(mode="json", exclude_unset=True),
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_psyche_settings_note"] in preview
    for field in PsycheSettingField:
        assert labels[f"application_field_{field.value}"] in preview
    messages = build_application_edit_prompt(
        draft.model_dump(mode="json"), "Show the emotional avatar"
    )
    assert json.loads(messages[1]["content"])["intent"] == patch.model_dump()
    properties = PsycheSettingsPatch.model_json_schema()["properties"]
    assert properties["psyche_enabled"]["type"] == "boolean"
    assert properties["psyche_stability"]["minimum"] == 0
    assert properties["psyche_stability"]["maximum"] == 100
    assert all("anyOf" not in prop and "default" not in prop for prop in properties.values())
