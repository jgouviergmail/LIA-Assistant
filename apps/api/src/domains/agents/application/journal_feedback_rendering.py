"""The whole stored correction and both phases' effects are visible before consent."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_feedback import feedback_public_scope
from src.domains.agents.application.journal_feedback_schemas import JournalFeedbackPatch
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def journal_feedback_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    values = JournalFeedbackPatch.model_validate(draft.intent).journal_feedback
    return [
        Note(text=labels["application_journal_feedback_note"]),
        Row(
            label=labels["application_field_journal_feedback"],
            value=json.dumps(feedback_public_scope(values), ensure_ascii=False),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]
