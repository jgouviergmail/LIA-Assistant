"""The source public token metadata is escaped before irreversible confirmation."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def health_token_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    return [
        Note(text=labels["application_health_token_note"]),
        Row(
            label=labels["application_field_health_token_to_revoke"],
            value=json.dumps(draft.before["health_token_to_revoke"], ensure_ascii=False),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


def health_token_creation_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    return [
        Note(text=labels["application_health_token_creation_note"]),
        Row(
            label=labels["application_field_health_token_to_create"],
            value=json.dumps(draft.after["health_token_to_create"], ensure_ascii=False),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]
