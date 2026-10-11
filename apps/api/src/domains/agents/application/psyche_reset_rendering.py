"""Only exact public effects are drawn; private scope fingerprints are never displayed."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def render_psyche_reset(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    return [
        Note(text=labels["application_psyche_reset_note"]),
        Row(
            label=labels["application_before"],
            value=json.dumps(draft.before["psyche_reset"], ensure_ascii=False),
        ),
        Row(
            label=labels["application_after"],
            value=json.dumps(draft.after["psyche_reset"], ensure_ascii=False),
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]
