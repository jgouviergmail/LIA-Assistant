"""Private state and personality digests are absent from paid approval."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.psyche_summary_schemas import PsycheSummaryPatch
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def psyche_summary_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    scope = PsycheSummaryPatch.model_validate(draft.intent).psyche_summary
    return [
        Note(text=labels["application_psyche_summary_note"]),
        Row(
            label=labels["application_field_psyche_summary"],
            value=json.dumps(scope.public_scope(), ensure_ascii=False),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]
