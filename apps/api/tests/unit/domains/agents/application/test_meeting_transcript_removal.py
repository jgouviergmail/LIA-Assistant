"""Transcript removal has one exact native HITL operation and safe witnesses."""

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_transcript_deletion_is_registered_in_both_execution_modes() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.meeting_transcript_spec import (
        TRANSCRIPT_DELETE_MANIFEST,
        TRANSCRIPT_DELETE_OPERATION,
    )
    from src.domains.agents.application.native_operations import NATIVE_OPERATIONS

    assert TRANSCRIPT_DELETE_OPERATION.tool_name in APPLICATION_TOOL_NAMES
    assert TRANSCRIPT_DELETE_OPERATION in NATIVE_OPERATIONS
    assert TRANSCRIPT_DELETE_MANIFEST.execution_modes == {"pipeline", "react"}
    assert TRANSCRIPT_DELETE_MANIFEST.mutation_policy == "draft"
    assert not TRANSCRIPT_DELETE_OPERATION.administrative


@pytest.mark.parametrize(
    "extra", [{"user_id": "forged"}, {"force": True}, {"transcript_digest": "a" * 64}]
)
def test_transcript_request_cannot_forge_authority_or_source_facts(
    extra: dict[str, object],
) -> None:
    from uuid import uuid4

    from src.domains.agents.application.meeting_transcript_schemas import TranscriptDeleteInput

    with pytest.raises(ValidationError):
        TranscriptDeleteInput.model_validate({"meeting_id": str(uuid4()), **extra})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_deletion_preview_and_amendment_never_expose_private_digest(language: str) -> None:
    from uuid import uuid4

    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.application.action_preparation import build_action_content
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.meeting_transcript_schemas import (
        TranscriptDeleteInput,
        TranscriptDeletePatch,
        TranscriptDeleteSelection,
        transcript_deletion_states,
    )
    from src.domains.agents.application.meeting_transcript_spec import TRANSCRIPT_DELETE_OPERATION
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.agents.application.state_changes import changed_resources
    from src.domains.agents.drafts.card_html import to_html_card
    from src.domains.agents.drafts.card_spec import CardSpec
    from src.infrastructure.meeting_transcripts import MeetingTranscriptState

    identity = uuid4()
    selected = TranscriptDeleteSelection(
        request=TranscriptDeleteInput(meeting_id=identity),
        expected=MeetingTranscriptState(
            meeting_id=identity,
            title="<script>Literal</script>",
            status="ready",
            stage=None,
            has_transcript=True,
            deleted_at=None,
            transcript_digest="e" * 64,
        ),
    )
    draft = build_action_content(
        uuid4(),
        TRANSCRIPT_DELETE_OPERATION,
        TranscriptDeletePatch(meeting_transcript_delete=selected),
        *transcript_deletion_states(selected),
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    rows = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Choose another meeting")
    )
    assert "transcript_digest" not in html + prompt and "e" * 64 not in html + prompt
    assert "has_transcript" not in prompt
    assert changed_resources(draft) == ["meetings"]
