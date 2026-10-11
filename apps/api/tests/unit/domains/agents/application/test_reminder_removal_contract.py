"""Deletion previews disclose the full effect, without internal comparison or archive data."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.core.card_composition import CardCompositionRequest
from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.reminder_create_schemas import ReminderRecurrence
from src.domains.agents.application.reminder_removal_schemas import (
    ReminderDeletePatch,
    ReminderSnapshot,
)
from src.domains.agents.application.reminder_spec import REMINDER_DELETE_OPERATION
from src.domains.reminders.service import once_at

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language", list(DRAFT_PREVIEW_LABELS))
def test_removal_preview_and_editor_keep_private_bindings_out(language: str) -> None:
    instant = datetime(2099, 1, 1, 9, 1, 19, tzinfo=UTC)
    private_identity = str(uuid4())
    patch = ReminderDeletePatch(
        reminder_to_delete=ReminderSnapshot(
            id=uuid4(),
            content="Exact full content",
            trigger_at=instant,
            user_timezone="Europe/Paris",
            recurrence=ReminderRecurrence.model_validate(
                once_at(instant, "Europe/Paris").model_dump(mode="json")
            ),
            created_at=instant,
            configuration_digest="d" * 64,
            card_selection=CardCompositionRequest(
                version=1,
                message_id=private_identity,
                run_id="private-run",
                registry_id="private-registry",
                action="cancel_reminder",
            ),
        )
    )
    content = build_action_content(
        uuid4(),
        REMINDER_DELETE_OPERATION,
        patch,
        patch.model_dump(mode="json"),
        {"reminder_to_delete": None},
    ).model_dump(mode="json")
    lines = render_application_preview(
        content, DRAFT_PREVIEW_LABELS[language], lambda value: value or ""
    )
    assert len(lines) == 3
    assert "Exact full content" in str(lines) and "Europe/Paris" in str(lines)
    assert instant.isoformat().replace("+00:00", "Z") in str(lines)
    assert "d" * 64 not in str(lines) and private_identity not in str(lines)
    prompt = build_application_edit_prompt(content, "Refresh")
    assert "reminder_id" in str(prompt)
    assert "configuration_digest" not in str(prompt) and "card_selection" not in str(prompt)
    assert private_identity not in str(prompt)
