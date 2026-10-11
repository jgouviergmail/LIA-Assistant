"""A retry is a paid background workflow proposal, never completed processing."""

from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def test_retry_request_cannot_choose_authority_or_change_processing_preferences() -> None:
    from pydantic import ValidationError

    from src.domains.agents.application.meeting_retry_schemas import MeetingRetryInput

    with pytest.raises(ValidationError):
        MeetingRetryInput.model_validate(
            {"meeting_id": str(uuid4()), "user_id": str(uuid4()), "auto_email": True}
        )


def test_retry_snapshot_growth_requires_scope_and_privacy_review() -> None:
    from src.infrastructure.meeting_retry import MeetingRetrySnapshot

    assert set(MeetingRetrySnapshot.model_fields) == {
        "meeting_id",
        "status",
        "stage",
        "title",
        "attempts",
        "audio_files",
        "audio_bytes_on_disk",
        "transcript_available",
        "keep_audio_until",
        "language",
        "account_email",
        "preferences_at_confirmation",
        "source_digest",
    }


def test_retry_is_owned_nonadmin_and_mandatory_hitl_in_both_modes() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.meeting_retry_spec import (
        MEETING_RETRY_MANIFEST,
        MEETING_RETRY_OPERATION,
    )
    from src.domains.agents.application.native_operations import NATIVE_OPERATIONS

    assert MEETING_RETRY_OPERATION in NATIVE_OPERATIONS
    assert MEETING_RETRY_OPERATION.tool_name in APPLICATION_TOOL_NAMES
    assert not MEETING_RETRY_OPERATION.administrative
    assert MEETING_RETRY_MANIFEST.mutation_policy == "draft"
    assert MEETING_RETRY_MANIFEST.execution_modes == {"pipeline", "react"}


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_retry_preview_roundtrip_and_prompt_do_not_expose_audio_or_source(language: str) -> None:
    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.application.action_preparation import build_action_content
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.meeting_retry_schemas import (
        MeetingRetryPatch,
        canonical_meeting_retry,
        retry_states,
    )
    from src.domains.agents.application.meeting_retry_spec import MEETING_RETRY_OPERATION
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.agents.drafts.card_html import to_html_card
    from src.domains.agents.drafts.card_spec import CardSpec
    from src.infrastructure.meeting_retry import MeetingRetrySnapshot

    selected = MeetingRetrySnapshot(
        meeting_id=uuid4(),
        status="failed",
        stage=None,
        title="<script>Literal</script>",
        attempts=3,
        audio_files=2,
        audio_bytes_on_disk=1234,
        transcript_available=True,
        keep_audio_until=None,
        language=language,
        account_email="owner@example.test",
        preferences_at_confirmation={
            "stt_engine": "auto",
            "language": "auto",
            "auto_email": True,
            "keep_audio_hours": 0,
            "default_template_ref": None,
            "keep_audio_hours_max": 72,
        },
        source_digest="e" * 64,
    )
    draft = build_action_content(
        uuid4(),
        MEETING_RETRY_OPERATION,
        MeetingRetryPatch(meeting_retry=selected),
        *retry_states(selected),
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    assert canonical_meeting_retry(draft)
    rows = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Refresh this retry"))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "source_digest" not in html + prompt and "e" * 64 not in html + prompt
    assert "processing_completed" in html and "auto_email" in html
    assert not canonical_meeting_retry(draft.model_copy(update={"after": {}}))
