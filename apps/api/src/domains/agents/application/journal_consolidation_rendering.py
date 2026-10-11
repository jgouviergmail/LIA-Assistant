"""The confirmation discloses generative effects and history/cost scope, never promises them."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.journal_consolidation_schemas import JournalConsolidationPatch
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def journal_consolidation_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    scope = JournalConsolidationPatch.model_validate(draft.intent).journal_consolidation
    return [
        Note(text=labels["application_journal_consolidation_note"]),
        Row(
            label=labels["application_field_journal_consolidation"],
            value=json.dumps(scope.public_scope(), ensure_ascii=False),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]
