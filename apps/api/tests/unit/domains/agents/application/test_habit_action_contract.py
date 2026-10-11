"""New source statuses/fields require explicit review; editors carry no authority."""

import json
from datetime import UTC, datetime
from typing import get_args
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.habit_action_schemas import (
    HabitDeletePatch,
    HabitDeleteRequest,
    HabitStatusChange,
    HabitStatusPatch,
    HabitStatusRequest,
    HabitStatusValues,
    habit_after,
)
from src.domains.agents.application.habit_spec import HABIT_DELETE_OPERATION, HABIT_STATUS_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.habits.management_commands import ManagedHabit
from src.domains.habits.models import HabitStatus
from src.domains.habits.schemas import HabitResponse, HabitStatusUpdate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "disabled"},
        {"status": None},
        {"status": False},
        {"status": "blocked", "actor_id": str(uuid4())},
        {"status": "blocked", "confirm": True},
        {"status": "blocked", "expected": {}},
    ],
)
def test_habit_change_refuses_ambiguous_status_and_authority(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        HabitStatusChange.model_validate(payload)


def test_status_and_public_field_coverage_requires_deliberate_source_review() -> None:
    assert set(HabitStatusUpdate.model_fields) == {"status"}
    assert set(get_args(HabitStatusUpdate.model_fields["status"].annotation)) == {
        "active",
        "paused",
        "blocked",
    }
    assert (
        set(ManagedHabit.model_fields)
        == set(HabitResponse.model_fields)
        == {
            "id",
            "kind",
            "key",
            "payload",
            "status",
            "positive_signals",
            "negative_signals",
            "last_observed_at",
            "created_at",
        }
    )
    assert set(HabitStatusRequest.model_fields) == {"habit_id", "status"}
    assert set(HabitDeleteRequest.model_fields) == {"habit_id"}


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
@pytest.mark.parametrize("action", ["status", "delete"])
def test_habit_confirmation_covers_source_scope_and_editor_projection(
    language: str, action: str
) -> None:
    snapshot = ManagedHabit(
        id=uuid4(),
        kind="recurring_request",
        key="<private-text>",
        payload={"version": 1},
        status=HabitStatus.ACTIVE,
        positive_signals=2,
        negative_signals=0,
        last_observed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    change = HabitStatusChange(status="blocked") if action == "status" else None
    intent = (
        HabitStatusPatch(habit=HabitStatusValues(expected=snapshot, status=change))
        if change
        else HabitDeletePatch(habit=snapshot)
    )
    draft = build_action_content(
        uuid4(),
        HABIT_STATUS_OPERATION if change else HABIT_DELETE_OPERATION,
        intent,
        {"habit": snapshot.model_dump(mode="json")},
        habit_after(snapshot, change),
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert (
        labels["application_field_habit"] in preview
        and labels[f"application_habit_{action}_note"] in preview
    )
    assert snapshot.key in preview and str(snapshot.id) in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "use another habit")
    editable = json.loads(prompt[1]["content"])["intent"]
    assert editable == (
        {"habit_id": str(snapshot.id), "status": "blocked"}
        if change
        else {"habit_id": str(snapshot.id)}
    )
    assert "payload" not in editable and "expected" not in editable and "actor_id" not in editable
