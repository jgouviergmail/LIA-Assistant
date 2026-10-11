"""Exact public counts or complete individual facts are escaped in confirmation."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def journal_removal_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    return [
        Note(text=labels["application_journal_removal_note"]),
        Row(
            label=labels["application_field_journal_entries_to_delete"],
            value=json.dumps(
                {
                    labels["application_before"]: draft.before["journal_entries_to_delete"],
                    labels["application_after"]: None,
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
