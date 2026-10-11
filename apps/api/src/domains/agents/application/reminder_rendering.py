"""Existing source reminder previews, extracted verbatim from generic composition."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.reminder_create_schemas import ReminderCreatePatch
from src.domains.agents.application.reminder_update_schemas import ReminderUpdatePatch
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def _reminder_update_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    previous = ReminderUpdatePatch.model_validate(draft.before).reminder_configuration
    selected = ReminderUpdatePatch.model_validate(draft.intent).reminder_configuration
    if (
        previous.expected != selected.expected
        or previous.changes != selected.changes
        or previous.requested_timezone != selected.requested_timezone
    ):
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_reminder_update_note"]),
        Row(
            label=labels["application_reminder_creation_title"],
            value=json.dumps(
                {
                    "id": str(selected.expected.id),
                    labels["application_before"]: previous.configuration.model_dump(mode="json"),
                    labels["application_after"]: selected.configuration.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def _reminder_creation_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    reminder = ReminderCreatePatch.model_validate(draft.intent).reminder_to_create
    if draft.before != {"reminder_to_create": None} or reminder.id != draft.command_id:
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_reminder_creation_note"]),
        Row(
            label=labels["application_reminder_creation_title"],
            value=json.dumps(
                {
                    "timezone": reminder.user_timezone,
                    "first_trigger_at": reminder.trigger_at.isoformat(),
                    **reminder.configuration.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]
