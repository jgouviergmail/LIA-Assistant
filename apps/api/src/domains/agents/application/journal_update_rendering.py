"""Source effective fields, not requested confidence, appear in exact approval."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def journal_update_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    return [
        Note(text=labels["application_journal_update_note"]),
        Row(
            label=labels["application_field_journal_entry"],
            value=json.dumps(
                {
                    labels["application_before"]: draft.before["journal_entry"],
                    labels["application_after"]: draft.after["journal_entry"],
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
