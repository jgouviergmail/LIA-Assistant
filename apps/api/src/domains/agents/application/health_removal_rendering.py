"""Source counts and irreversible scope are displayed; sample values and hashes stay private."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def health_removal_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    return [
        Note(text=labels["application_health_removal_note"]),
        Row(
            label=labels["application_field_health_samples_to_delete"],
            value=json.dumps(draft.before["health_samples_to_delete"], ensure_ascii=False),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]
