"""Exact email envelopes, private editor boundaries and action identity survive checkpoints."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application import email_share_read, email_share_send
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.email_share_send_schemas import (
    EmailShareSendInput,
    EmailShareSendPatch,
    EmailShareSnapshot,
)
from src.domains.agents.application.email_share_send_spec import EMAIL_SHARE_SEND_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.effects.labels import build_effect_label
from src.domains.agents.tools.application_email_share_tools import send_lia_email_share_tool
from src.domains.email_share import rate_limits, router

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "invalid",
    [
        {"kind": "markdown", "filename": "invented", "text": "model copy"},
        {"kind": "file", "attachment_id": str(uuid4()), "force": True},
        {"kind": "saved_answer", "bookmark_id": str(uuid4()), "user_id": str(uuid4())},
    ],
)
def test_sending_never_accepts_invented_content_or_owner_override(invalid):
    with pytest.raises(ValidationError):
        EmailShareSendInput.model_validate({"subject": "Actual subject", "attachment": invalid})


def test_subject_header_and_rate_limits_reuse_original_ui_contract():
    with pytest.raises(ValidationError):
        EmailShareSendInput.model_validate(
            {
                "subject": "Forged\r\nBcc: stranger",
                "attachment": {"kind": "saved_answer", "bookmark_id": str(uuid4())},
            }
        )
    assert (
        router.rate_limit_email_share
        is rate_limits.rate_limit_email_share
        is email_share_send.rate_limit_email_share
    )
    assert (
        router.rate_limit_recipient_suggestions
        is rate_limits.rate_limit_recipient_suggestions
        is email_share_read.limit_recipients
    )


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_email_consent_checkpoint_private_editor_html_and_action_identity(language):
    request = EmailShareSendInput(
        subject="Actual subject",
        message="Literal message",
        attachment={"kind": "saved_answer", "bookmark_id": uuid4()},
    )
    scope = EmailShareSnapshot(
        request=request,
        route="relay",
        connector_type=None,
        recipients=("owner@example.test",),
        filename="lia-answer.md",
        file_bytes=200_000,
        content_type="text/markdown",
        answer_preview="<script>literal</script>",
        state_digest="f" * 64,
    )
    draft = build_action_content(
        uuid4(),
        EMAIL_SHARE_SEND_OPERATION,
        EmailShareSendPatch(email_to_send=scope),
        {"email_to_send": scope.public_scope()},
        {"email_to_send": scope.public_scope(after=True)},
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Change the subject"))
    assert "state_digest" not in prompt and "f" * 64 not in prompt
    labels = get_draft_preview_labels(language)
    assert labels["application_email_share_send_note"]
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    assert "f" * 64 not in str(rows)
    label = build_effect_label(
        "draft:application_action",
        {"draft": {"title": "Email answer", "operation_id": draft.operation_id}},
    )
    assert label["values"]["operation"] == EMAIL_SHARE_SEND_OPERATION.operation_id
    assert set(send_lia_email_share_tool.tool_call_schema.model_json_schema()["properties"]) == {
        "request"
    }
