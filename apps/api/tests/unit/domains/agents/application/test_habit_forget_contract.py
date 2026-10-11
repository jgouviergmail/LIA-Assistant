"""Complete forgetting exposes only localized counts and explicit source scope."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.habit_forget_schemas import HabitForgetPatch, HabitForgetRequest
from src.domains.agents.application.habit_spec import HABIT_FORGET_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.habits.forget_snapshot import HabitForgetSnapshot

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"scope": "all"},
        {"scope": "all_owned", "user_id": str(uuid4())},
        {"scope": "all_owned", "redis_key": "*"},
        {"scope": "all_owned", "confirm": True},
    ],
)
def test_forgetting_refuses_scope_or_authority_injection(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        HabitForgetRequest.model_validate(payload)


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_forgetting_preview_and_editor_keep_the_digest_private(language: str) -> None:
    scope = HabitForgetSnapshot(habits=203, profiles=1, activity_days=56, digest="e" * 64)
    draft = build_action_content(
        uuid4(),
        HABIT_FORGET_OPERATION,
        HabitForgetPatch(habit_data=scope),
        {"habit_data": scope.public_counts()},
        {"habit_data": None},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_habit_forget_note"] in preview
    assert all(
        labels[key] in preview
        for key in (
            "application_habit_count",
            "application_habit_profile_count",
            "application_habit_activity_count",
        )
    )
    assert "203" in preview and scope.digest not in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "forget everything")
    assert json.loads(prompt[1]["content"])["intent"] == {"scope": "all_owned"}
    assert scope.digest not in str(prompt)
