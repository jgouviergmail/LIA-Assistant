"""Manual recompute has a fixed owned scope and no user-supplied outcome or authority."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.habit_recompute_schemas import (
    HabitRecomputePatch,
    HabitRecomputeRequest,
    HabitRecomputeScope,
)
from src.domains.agents.application.habit_spec import HABIT_RECOMPUTE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.habits.schemas import HabitsRecomputeResponse

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"scope": "all"},
        {"scope": "current_account", "actor_id": str(uuid4())},
        {"scope": "current_account", "force": False},
        {"scope": "current_account", "outcome": "computed"},
    ],
)
def test_recompute_request_refuses_authority_and_invented_result(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        HabitRecomputeRequest.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_recompute_preview_and_editor_describe_evaluation_not_a_forecast(language: str) -> None:
    scope = HabitRecomputeScope(timezone="Europe/Paris", habits_enabled=False)
    data = scope.model_dump(mode="json")
    draft = build_action_content(
        uuid4(),
        HABIT_RECOMPUTE_OPERATION,
        HabitRecomputePatch(habit_recompute=scope),
        {"habit_recompute": data},
        {"habit_recompute": {**data, "requested": True}},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_habit_recompute_note"] in preview and scope.timezone in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "recompute now")
    assert json.loads(prompt[1]["content"])["intent"] == {"scope": "current_account"}
    assert "habits_enabled" not in prompt[1]["content"]
    assert HABIT_RECOMPUTE_OPERATION.required_capabilities == (PlatformCapability.HABITS,)
    assert set(HabitsRecomputeResponse.model_fields) == {"outcome", "profile"}
