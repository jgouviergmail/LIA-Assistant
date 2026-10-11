"""Both sides of the confirmed commitment are visible as escaped public data."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def open_loop_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    return [
        Note(text=labels["application_open_loop_note"]),
        Row(
            label=labels["application_field_open_loop"],
            value=json.dumps(
                {
                    labels["application_before"]: draft.before["open_loop"],
                    labels["application_after"]: draft.after["open_loop"],
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
