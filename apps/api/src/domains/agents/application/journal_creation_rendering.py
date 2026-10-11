"""The manual configuration is complete, escaped data in human confirmation."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_create_schemas import JournalCreatePatch
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def journal_creation_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    selected = JournalCreatePatch.model_validate(draft.intent).journal_entry_to_create
    if (
        draft.before != {"journal_entry_to_create": None}
        or selected.id != draft.command_id
        or draft.after != draft.intent
    ):
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels["application_journal_creation_note"]),
        Row(
            label=labels["application_field_journal_entry_to_create"],
            value=json.dumps(selected.model_dump(mode="json"), ensure_ascii=False),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]
