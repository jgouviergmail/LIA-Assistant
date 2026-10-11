"""Sparse reminder edits never clear, coerce or silently choose between two clocks."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.reminder_operations import reminder_snapshot
from src.domains.agents.application.reminder_spec import REMINDER_UPDATE_OPERATION
from src.domains.agents.application.reminder_update_schemas import (
    ReminderConfigurationValues,
    ReminderUpdateChanges,
    ReminderUpdatePatch,
    ReminderUpdateRequest,
    ReminderUpdateValues,
)
from src.domains.agents.application.result_projection import public_application_values
from src.domains.reminders.models import Reminder
from src.domains.reminders.schemas import ReminderUpdate
from src.domains.reminders.service import once_at, preview_reminder_update

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"content": None},
        {"content": 3},
        {"content": ""},
        {"trigger_at": None},
        {"recurrence": None},
        {"status": "pending"},
        {"trigger_at": 4_000_000_000},
        {"trigger_at": 4_000_000_000.5},
        {
            "trigger_at": "2099-01-01T09:00:00Z",
            "recurrence": {
                "freq": "once",
                "anchor_date": "2099-01-01",
                "times": {"mode": "at", "at": [{"hour": 10, "minute": 0}]},
            },
        },
    ],
)
def test_native_changes_refuse_ambiguous_null_extra_or_coerced_values(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ReminderUpdateRequest.model_validate({"reminder_id": str(uuid4()), "changes": changes})


def test_new_source_settings_require_explicit_review_and_stay_sparse() -> None:
    assert set(ReminderUpdate.model_fields) == {"content", "trigger_at", "recurrence"}
    assert set(ReminderUpdateChanges.model_fields) == set(ReminderUpdate.model_fields)
    request = ReminderUpdateChanges(content="Changed")
    assert request.model_dump(mode="json", exclude_unset=True) == {"content": "Changed"}


@pytest.mark.parametrize("language", list(DRAFT_PREVIEW_LABELS))
def test_complete_edit_preview_and_safe_editor_hide_internal_comparison(language: str) -> None:
    instant = datetime(2099, 1, 1, 9, 3, 19, tzinfo=UTC)
    row = Reminder(
        id=uuid4(),
        user_id=uuid4(),
        content="Before content",
        original_message="Private original",
        trigger_at=instant,
        user_timezone="Europe/Paris",
        recurrence=once_at(instant, "Europe/Paris").model_dump(mode="json"),
        created_at=instant,
    )
    changes = ReminderUpdateChanges(content="After content")
    before = ReminderUpdateValues(
        expected=reminder_snapshot(row),
        requested_timezone="UTC",
        changes=changes,
        configuration=ReminderConfigurationValues.of(
            preview_reminder_update(row, ReminderUpdate(), "UTC")
        ),
    )
    after = before.model_copy(
        update={
            "configuration": ReminderConfigurationValues.of(
                preview_reminder_update(row, changes, "UTC")
            )
        }
    )
    previous, desired = ReminderUpdatePatch(reminder_configuration=before), ReminderUpdatePatch(
        reminder_configuration=after
    )
    draft = build_action_content(
        row.user_id,
        REMINDER_UPDATE_OPERATION,
        desired,
        previous.model_dump(mode="json", exclude_unset=True),
        desired.model_dump(mode="json", exclude_unset=True),
    )
    lines = render_application_preview(
        draft.model_dump(mode="json"), DRAFT_PREVIEW_LABELS[language], lambda value: value or ""
    )
    assert len(lines) == 3
    assert "Before content" in str(lines) and "After content" in str(lines)
    assert "Europe/Paris" in str(lines) and instant.isoformat().replace("+00:00", "Z") in str(lines)
    assert "Private original" not in str(lines) and "configuration_digest" not in str(lines)
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Change content")
    assert "configuration_digest" not in str(prompt) and "requested_timezone" not in str(prompt)
    assert "expected" not in str(prompt) and "Private original" not in str(prompt)
    public = public_application_values(draft)
    assert public["content"] == "After content" and public["user_timezone"] == "Europe/Paris"
    assert "expected" not in str(public) and "Private original" not in str(public)
