"""Deletion consent is exact, private, nonadministrative and explicit about cleanup."""

from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def test_deletion_is_registered_nonadmin_with_original_hitl_in_both_modes() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.meeting_deletion_spec import (
        MEETING_DELETION_MANIFEST,
        MEETING_DELETION_OPERATION,
    )
    from src.domains.agents.application.native_operations import NATIVE_OPERATIONS

    assert MEETING_DELETION_OPERATION in NATIVE_OPERATIONS
    assert MEETING_DELETION_OPERATION.tool_name in APPLICATION_TOOL_NAMES
    assert not MEETING_DELETION_OPERATION.administrative
    assert MEETING_DELETION_MANIFEST.mutation_policy == "draft"
    assert MEETING_DELETION_MANIFEST.execution_modes == {"pipeline", "react"}


def test_delete_input_refuses_account_paths_and_a_wider_purge() -> None:
    from pydantic import ValidationError

    from src.domains.agents.application.meeting_deletion_schemas import MeetingDeletionInput

    with pytest.raises(ValidationError):
        MeetingDeletionInput.model_validate(
            {
                "meeting_id": str(uuid4()),
                "user_id": str(uuid4()),
                "path": "/",
                "delete_derived": True,
            }
        )


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_delete_checkpoint_and_literal_preview_exclude_private_witnesses(language: str) -> None:
    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.application.action_preparation import build_action_content
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.meeting_deletion_schemas import (
        MeetingDeletionPatch,
        canonical_meeting_deletion,
        deletion_states,
    )
    from src.domains.agents.application.meeting_deletion_spec import MEETING_DELETION_OPERATION
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.agents.drafts.card_html import to_html_card
    from src.domains.agents.drafts.card_spec import CardSpec
    from src.infrastructure.meeting_deletions import MeetingDeletionSnapshot

    selected = MeetingDeletionSnapshot(
        meeting_id=uuid4(),
        status="ready",
        stage=None,
        title="<script>Literal</script>",
        current_valid=True,
        current_sections_count=1,
        generated_report_present=True,
        transcript_present=True,
        audio_files=2,
        audio_bytes_on_disk=32,
        projection_id=uuid4(),
        projection_present=True,
        derived_minutes_kept=2,
        source_digest="e" * 64,
    )
    draft = build_action_content(
        uuid4(),
        MEETING_DELETION_OPERATION,
        MeetingDeletionPatch(meeting_delete=selected),
        *deletion_states(selected),
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    assert canonical_meeting_deletion(draft)
    rows = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Choose another meeting")
    )
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "source_digest" not in html + prompt and "e" * 64 not in html + prompt
    assert "derived_minutes_kept" in html and "files_cleanup_requested" in html
    assert not canonical_meeting_deletion(draft.model_copy(update={"after": {}}))


def test_delete_scope_growth_requires_privacy_and_effect_review() -> None:
    from src.infrastructure.meeting_deletions import MeetingDeletionSnapshot

    assert set(MeetingDeletionSnapshot.model_fields) == {
        "meeting_id",
        "status",
        "stage",
        "title",
        "current_valid",
        "current_sections_count",
        "generated_report_present",
        "transcript_present",
        "audio_files",
        "audio_bytes_on_disk",
        "projection_id",
        "projection_present",
        "derived_minutes_kept",
        "source_digest",
    }
