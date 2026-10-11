"""Literal whole-email consent survives checkpoints without exposing source bodies."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.meeting_email_schemas import (
    MeetingEmailInput,
    MeetingEmailPatch,
    canonical_meeting_email,
    email_states,
)
from src.domains.agents.application.meeting_email_spec import (
    MEETING_EMAIL_MANIFEST,
    MEETING_EMAIL_OPERATION,
)
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.infrastructure.meeting_email import MeetingEmailSnapshot

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_email_consent_is_literal_complete_and_private(language: str) -> None:
    selected = MeetingEmailSnapshot(
        meeting_id=uuid4(),
        title="<script>Literal</script>",
        recipient="owner@example.test",
        sender="platform@example.test",
        subject="Minutes <script>Literal</script>",
        language=language,
        participants_count=2,
        sections_count=3,
        previous_sent_at=None,
        source_digest="d" * 64,
    )
    draft = build_action_content(
        uuid4(),
        MEETING_EMAIL_OPERATION,
        MeetingEmailPatch(meeting_email_send=selected),
        *email_states(selected),
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    assert canonical_meeting_email(draft)
    rows = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Refresh this send"))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "source_digest" not in html + prompt and "d" * 64 not in html + prompt
    assert "owner@example.test" in html and "platform@example.test" in html
    assert "entire_report" in html and "summary_only" in html
    assert not canonical_meeting_email(draft.model_copy(update={"after": {}}))
    assert MEETING_EMAIL_OPERATION in NATIVE_OPERATIONS
    assert MEETING_EMAIL_OPERATION.tool_name in APPLICATION_TOOL_NAMES
    assert not MEETING_EMAIL_OPERATION.administrative
    assert MEETING_EMAIL_MANIFEST.mutation_policy == "draft"
    assert MEETING_EMAIL_MANIFEST.execution_modes == {"pipeline", "react"}


def test_request_rejects_recipient_and_authority_injection() -> None:
    with pytest.raises(ValidationError):
        MeetingEmailInput.model_validate(
            {"meeting_id": str(uuid4()), "recipient": "foreign@example.test"}
        )


def test_snapshot_field_growth_requires_public_scope_review() -> None:
    assert set(MeetingEmailSnapshot.model_fields) == {
        "meeting_id",
        "title",
        "recipient",
        "sender",
        "subject",
        "language",
        "participants_count",
        "sections_count",
        "previous_sent_at",
        "source_digest",
    }
