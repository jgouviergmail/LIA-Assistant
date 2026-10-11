"""Only bounded public scope and format appear in export confirmations."""

from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export_schemas import ManagementExportPatch
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row

_COPY = {
    "memories.export": ("application_memory_export_note", "application_memories_export_title"),
    "interests.export": (
        "application_management_export_note",
        "application_interests_export_title",
    ),
    "journals.export": ("application_journal_export_note", "application_journals_export_title"),
}


def management_export_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    selected = ManagementExportPatch.model_validate(draft.intent).management_export
    note, title = _COPY[draft.operation_id]
    if draft.before != {"management_export": None}:
        return [Note(text=labels["application_unavailable"])]
    return [
        Note(text=labels[note]),
        Row(
            label=labels[title],
            value=f"{selected.selected_count} · {selected.format.upper()} · {format_dt(selected.observed_at.isoformat())}",
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]
