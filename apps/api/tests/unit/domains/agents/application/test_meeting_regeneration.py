"""Owned rebuild proposals preserve exact consent, privacy and finite context."""

from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def snapshot(language: str = "fr"):
    from src.infrastructure.meeting_regeneration import MeetingRegenerationSnapshot

    return MeetingRegenerationSnapshot(
        meeting_id=uuid4(),
        status="ready",
        stage=None,
        current_title="<script>Literal</script>",
        current_valid=True,
        current_participants_count=2,
        current_sections_count=1,
        transcript_turns=3,
        language=language,
        template_definition_at_confirmation={
            "ref": "builtin:standard",
            "name": "Selected template",
            "sections": [
                {
                    "key": "summary",
                    "label": "Summary",
                    "kind": "paragraph",
                    "instruction": "<script>exact instruction</script>",
                }
            ],
        },
        source_digest="e" * 64,
    )


def test_rebuild_is_registered_nonadmin_and_requires_original_hitl_in_both_modes():
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.meeting_regeneration_spec import (
        MEETING_REGENERATION_MANIFEST,
        MEETING_REGENERATION_OPERATION,
    )
    from src.domains.agents.application.native_operations import NATIVE_OPERATIONS

    assert MEETING_REGENERATION_OPERATION in NATIVE_OPERATIONS
    assert MEETING_REGENERATION_OPERATION.tool_name in APPLICATION_TOOL_NAMES
    assert not MEETING_REGENERATION_OPERATION.administrative
    assert MEETING_REGENERATION_MANIFEST.mutation_policy == "draft"
    assert MEETING_REGENERATION_MANIFEST.execution_modes == {"pipeline", "react"}


def test_rebuild_request_refuses_account_and_background_configuration_overrides():
    from pydantic import ValidationError

    from src.domains.agents.application.meeting_regeneration_schemas import MeetingRegenerationInput

    with pytest.raises(ValidationError):
        MeetingRegenerationInput.model_validate(
            {"meeting_id": str(uuid4()), "user_id": str(uuid4()), "template_ref": "builtin:other"}
        )


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_rebuild_exact_scope_roundtrip_and_private_witness_exclusion(language: str):
    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.application.action_preparation import build_action_content
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.meeting_regeneration_schemas import (
        MeetingRegenerationPatch,
        canonical_meeting_regeneration,
        regeneration_states,
    )
    from src.domains.agents.application.meeting_regeneration_spec import (
        MEETING_REGENERATION_OPERATION,
    )
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.agents.drafts.card_html import to_html_card
    from src.domains.agents.drafts.card_spec import CardSpec

    selected = snapshot(language)
    draft = build_action_content(
        uuid4(),
        MEETING_REGENERATION_OPERATION,
        MeetingRegenerationPatch(meeting_regeneration=selected),
        *regeneration_states(selected),
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    assert canonical_meeting_regeneration(draft)
    rows = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Refresh consent"))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "source_digest" not in html + prompt and "e" * 64 not in html + prompt
    assert "instruction" in html and "processing_completed" in html
    assert not canonical_meeting_regeneration(draft.model_copy(update={"after": {}}))


def test_rebuild_scope_growth_requires_authority_and_privacy_review():
    from src.infrastructure.meeting_regeneration import (
        ConfirmedTemplateSection,
        MeetingRegenerationSnapshot,
        RegenerationTemplate,
    )

    assert set(MeetingRegenerationSnapshot.model_fields) == {
        "meeting_id",
        "status",
        "stage",
        "current_title",
        "current_valid",
        "current_participants_count",
        "current_sections_count",
        "transcript_turns",
        "language",
        "template_definition_at_confirmation",
        "source_digest",
    }
    assert set(RegenerationTemplate.model_fields) == {"ref", "name", "sections"}
    assert set(ConfirmedTemplateSection.model_fields) == {"key", "label", "kind", "instruction"}


@pytest.mark.parametrize("text", ["ordinary", "中文é<|endoftext|>"])
def test_context_bound_refuses_complete_consent_instead_of_truncating(monkeypatch, text: str):
    from src.domains.agents.application import meeting_action_budget
    from src.domains.agents.application.action_preparation import build_action_content
    from src.domains.agents.application.command_service import CommandRejected
    from src.domains.agents.application.meeting_regeneration_schemas import (
        MeetingRegenerationPatch,
        regeneration_states,
    )
    from src.domains.agents.application.meeting_regeneration_spec import (
        MEETING_REGENERATION_OPERATION,
    )

    selected = snapshot().model_copy(update={"current_title": text})
    draft = build_action_content(
        uuid4(),
        MEETING_REGENERATION_OPERATION,
        MeetingRegenerationPatch(meeting_regeneration=selected),
        *regeneration_states(selected),
    )
    monkeypatch.setattr(meeting_action_budget, "meeting_read_token_budget", lambda: 1)
    with pytest.raises(CommandRejected) as refused:
        meeting_action_budget.require_meeting_action_budget(draft)
    assert refused.value.code == "CONSTRAINT_VIOLATION"
    assert draft.before["meeting_regeneration"]["current_title"] == text
