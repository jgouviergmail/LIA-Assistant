"""Native creation refuses ambiguous/extra input and follows the source field contract."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
from src.core.recurrence import DailyTimes, RecurrenceSpec, SeriesEnd, TimeOfDay
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.reminder_create_schemas import (
    ReminderCreatePatch,
    ReminderCreateRequest,
    ReminderCreationValues,
    ReminderDailyTimes,
    ReminderRecurrence,
    ReminderSeriesEnd,
    ReminderTimeOfDay,
)
from src.domains.agents.application.reminder_spec import REMINDER_CREATE_OPERATION
from src.domains.reminders.schemas import ReminderCreate
from src.domains.reminders.service import resolve_reminder_creation

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "patch",
    [
        {"content": ""},
        {"content": 3},
        {"user_id": "invented-owner"},
        {"trigger_at": None},
        {
            "trigger_at": None,
            "recurrence": {
                "freq": "once",
                "anchor_date": "2099-01-01",
                "times": {"mode": "at", "at": [{"hour": 9, "minute": 0, "execute": True}]},
            },
        },
    ],
)
def test_ambiguous_or_extra_creation_input_is_refused(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReminderCreateRequest.model_validate(
            {
                "content": "Reminder",
                "original_message": "Reminder",
                "trigger_at": datetime(2099, 1, 1, tzinfo=UTC),
                **patch,
            }
        )


def test_future_source_creation_fields_require_a_native_contract_review() -> None:
    assert set(ReminderCreate.model_fields) == {
        "content",
        "original_message",
        "trigger_at",
        "recurrence",
    }
    assert set(ReminderCreateRequest.model_fields) == set(ReminderCreate.model_fields)


@pytest.mark.parametrize(
    "source,native",
    [
        (RecurrenceSpec, ReminderRecurrence),
        (DailyTimes, ReminderDailyTimes),
        (TimeOfDay, ReminderTimeOfDay),
        (SeriesEnd, ReminderSeriesEnd),
    ],
)
def test_future_nested_schedule_fields_require_native_review(source: type, native: type) -> None:
    reviewed = {
        RecurrenceSpec: {
            "freq",
            "times",
            "anchor_date",
            "interval",
            "byweekday",
            "bymonthday",
            "nth_weekday",
            "bymonth",
            "end",
        },
        DailyTimes: {"mode", "at", "step_minutes", "start", "end"},
        TimeOfDay: {"hour", "minute"},
        SeriesEnd: {"kind", "on_date", "after_count"},
    }
    assert set(source.model_fields) == reviewed[source]
    assert set(source.model_fields) == set(native.model_fields)


@pytest.mark.parametrize("language", list(DRAFT_PREVIEW_LABELS))
def test_reminder_preview_is_complete_and_editor_cannot_choose_clock_identity(
    language: str,
) -> None:
    identity = uuid4()
    request = ReminderCreateRequest(
        content="Exact content",
        original_message="Reminder wording",
        trigger_at=datetime(2099, 1, 15, 9, 3, 19, tzinfo=UTC),
    )
    arming = resolve_reminder_creation(request, "Europe/Paris")
    patch = ReminderCreatePatch(
        reminder_to_create=ReminderCreationValues(
            id=identity,
            configuration=request,
            user_timezone="Europe/Paris",
            trigger_at=arming.trigger_at,
            recurrence=ReminderRecurrence.model_validate(arming.recurrence.model_dump(mode="json")),
        )
    )
    content = build_action_content(
        uuid4(),
        REMINDER_CREATE_OPERATION,
        patch,
        {"reminder_to_create": None},
        patch.model_dump(mode="json", exclude_unset=True),
        command_id=identity,
    ).model_dump(mode="json")
    lines = render_application_preview(
        content, DRAFT_PREVIEW_LABELS[language], lambda value: value or ""
    )
    assert len(lines) == 3
    assert "Exact content" in str(lines) and "Europe/Paris" in str(lines)
    assert arming.trigger_at.isoformat() in str(lines)
    assert "LLM" in str(lines)
    prompt = build_application_edit_prompt(content, "Change the content")
    assert str(identity) not in str(prompt) and "user_timezone" not in str(prompt)
    assert "expected_digest" not in str(prompt) and "first_trigger_at" not in str(prompt)
