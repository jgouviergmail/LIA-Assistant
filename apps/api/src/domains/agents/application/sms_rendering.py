"""Source-owned, non-secret SMS approval preview using the common card grammar."""

import json
from collections.abc import Callable

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.sms_action_spec import SMS_ACTION_SPECS
from src.domains.agents.application.sms_actions import canonical_sms_action
from src.domains.agents.drafts.card_spec import Note, PreviewLine, Row


def sms_preview(
    draft: ApplicationActionDraftContent,
    labels: dict[str, str],
    format_dt: Callable[[str | None], str],
) -> list[PreviewLine]:
    return [
        Note(text=labels["application_sms_note"]),
        Row(
            label=labels["application_before"],
            value=json.dumps(draft.before, ensure_ascii=False),
            key="details",
        ),
        Row(
            label=labels["application_after"],
            value=json.dumps(draft.after, ensure_ascii=False),
            key="details",
        ),
        Row(
            label=labels["application_expiry"],
            value=format_dt(draft.expires_at.isoformat()),
            key="date",
        ),
    ]


SMS_CANONICAL = dict.fromkeys(SMS_ACTION_SPECS, canonical_sms_action)
SMS_PREVIEWS = dict.fromkeys(SMS_ACTION_SPECS, sms_preview)
