"""Habit preference confirmation is strict, complete and fully localized."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.habit_settings_schemas import (
    HabitSettingField,
    HabitSettingsPatch,
)
from src.domains.agents.application.habit_spec import HABIT_SETTINGS_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.habits.schemas import HabitsSettingsUpdate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"habits_enabled": "false"},
        {"habits_enabled": 0},
        {"habits_enabled": None},
        {"habits_enabled": False, "actor_id": str(uuid4())},
        {"habits_enabled": False, "recompute": True},
    ],
)
def test_learning_preference_refuses_ambiguous_or_structural_input(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        HabitSettingsPatch.model_validate(payload)


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_learning_preference_preview_and_editor_cover_the_source_scope(language: str) -> None:
    patch = HabitSettingsPatch(habits_enabled=False)
    draft = build_action_content(
        uuid4(),
        HABIT_SETTINGS_OPERATION,
        patch,
        {"habits_enabled": True},
        {"habits_enabled": False},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert (
        labels["application_field_habits_enabled"] in preview
        and labels["application_habit_settings_note"] in preview
    )
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Keep learning enabled")
    assert json.loads(prompt[1]["content"])["intent"] == {"habits_enabled": False}
    assert (
        {field.value for field in HabitSettingField}
        == set(HabitsSettingsUpdate.model_fields)
        == set(HabitSettingsPatch.model_fields)
    )
