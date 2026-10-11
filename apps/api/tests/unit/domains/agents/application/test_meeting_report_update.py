"""Native sparse report edits reuse original schemas and seal source facts."""

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_native_report_patch_reuses_the_original_five_fields() -> None:
    from src.core.meeting_reports import MeetingPatchRequest
    from src.domains.agents.application.meeting_report_update_schemas import ReportEditValues

    assert issubclass(ReportEditValues, MeetingPatchRequest)
    assert set(ReportEditValues.model_fields) == {
        "title",
        "participants",
        "sections",
        "location_label",
        "template_ref",
    }
    from src.domains.meetings.schemas import MeetingPatchRequest as PublicPatch

    assert PublicPatch is MeetingPatchRequest


def test_every_nested_original_field_is_classified_for_exact_replacements() -> None:
    from src.core.meeting_reports import (
        ActionItem,
        Participant,
        ReportSection,
        TopicItem,
        TranscriptLine,
    )

    assert set(Participant.model_fields) == {"label", "name", "role"}
    assert set(ReportSection.model_fields) == {
        "key",
        "label",
        "kind",
        "paragraph",
        "bullets",
        "topics",
        "action_items",
        "transcript",
    }
    assert set(TopicItem.model_fields) == {"title", "summary"}
    assert set(ActionItem.model_fields) == {"description", "owner", "due_date"}
    assert set(TranscriptLine.model_fields) == {"speaker", "start", "text"}


@pytest.mark.parametrize(
    "changes",
    [
        {"title": None},
        {"participants": [{"label": "S1", "admin": True}]},
        {"sections": [{"key": "summary", "label": "Summary", "kind": "paragraph", "secret": True}]},
        {
            "sections": [
                {
                    "key": "summary",
                    "label": "Summary",
                    "kind": "topics",
                    "topics": [{"title": "Topic", "summary": "Body", "admin": True}],
                }
            ]
        },
    ],
)
def test_native_patch_refuses_unannounced_fields_and_ignored_null(
    changes: dict[str, object],
) -> None:
    from src.domains.agents.application.meeting_report_update_schemas import ReportEditValues

    with pytest.raises(ValidationError):
        ReportEditValues.model_validate(changes)


def test_native_report_patch_is_mandatory_hitl_in_both_modes() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.meeting_report_update_spec import (
        REPORT_UPDATE_MANIFEST,
        REPORT_UPDATE_OPERATION,
    )
    from src.domains.agents.application.native_operations import NATIVE_OPERATIONS

    assert REPORT_UPDATE_OPERATION.tool_name in APPLICATION_TOOL_NAMES
    assert REPORT_UPDATE_OPERATION in NATIVE_OPERATIONS
    assert not REPORT_UPDATE_OPERATION.administrative
    assert REPORT_UPDATE_MANIFEST.execution_modes == {"pipeline", "react"}
    assert REPORT_UPDATE_MANIFEST.mutation_policy == "draft"


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_sparse_preview_is_exact_escaped_and_does_not_leak_source_witness(language: str) -> None:
    from uuid import uuid4

    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.application.action_preparation import build_action_content
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.meeting_report_update_schemas import (
        ReportUpdateInput,
        ReportUpdatePatch,
        ReportUpdateSelection,
        canonical_report_update,
        report_update_states,
    )
    from src.domains.agents.application.meeting_report_update_spec import REPORT_UPDATE_OPERATION
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.agents.application.state_changes import changed_resources
    from src.domains.agents.drafts.card_html import to_html_card
    from src.domains.agents.drafts.card_spec import CardSpec
    from src.infrastructure.meeting_report_updates import ReportPatchState

    identity = uuid4()
    value = "<script>Literal 漢字</script>"
    selected = ReportUpdateSelection(
        request=ReportUpdateInput(meeting_id=identity, changes={"title": value}),
        expected=ReportPatchState(
            meeting_id=identity,
            status="ready",
            stage=None,
            edited_at=None,
            source_digest="e" * 64,
            before={"title": "Before"},
            after={"title": value},
        ),
    )
    draft = build_action_content(
        uuid4(),
        REPORT_UPDATE_OPERATION,
        ReportUpdatePatch(meeting_report_update=selected),
        *report_update_states(selected),
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    assert canonical_report_update(draft)
    rows = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Choose another title")
    )
    assert "<script>" not in html and "&lt;script&gt;Literal 漢字&lt;/script&gt;" in html
    assert "source_digest" not in html + prompt and "e" * 64 not in html + prompt
    assert changed_resources(draft) == ["meetings"]
    assert not canonical_report_update(draft.model_copy(update={"after": {}}))


def test_oversized_exact_report_consent_is_refused_without_truncation() -> None:
    from uuid import uuid4

    from src.domains.agents.application.meeting_report_update_schemas import (
        ReportUpdateInput,
        ReportUpdateSelection,
    )
    from src.infrastructure.meeting_report_updates import ReportPatchState

    identity = uuid4()
    with pytest.raises(ValidationError):
        ReportUpdateSelection(
            request=ReportUpdateInput(meeting_id=identity, changes={"sections": []}),
            expected=ReportPatchState(
                meeting_id=identity,
                status="ready",
                stage=None,
                edited_at=None,
                source_digest="a" * 64,
                before={"sections": ["漢" * 24000]},
                after={"sections": []},
            ),
        )


async def test_exact_proposal_refuses_the_existing_token_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    from src.domains.agents.application import meeting_report_updating as module
    from src.domains.agents.application.command_service import CommandRejected
    from src.domains.agents.application.meeting_report_update_schemas import ReportUpdateInput
    from src.infrastructure.meeting_report_updates import ReportPatchState

    identity = uuid4()
    facts = ReportPatchState(
        meeting_id=identity,
        status="ready",
        stage=None,
        edited_at=None,
        source_digest="a" * 64,
        before={"title": "Before"},
        after={"title": "After"},
    )
    monkeypatch.setattr(
        module,
        "require_meeting_preferences",
        AsyncMock(return_value=SimpleNamespace(language="fr")),
    )
    monkeypatch.setattr(
        module,
        "get_meeting_report_updates",
        lambda: SimpleNamespace(read_update=AsyncMock(return_value=facts)),
    )
    from src.domains.agents.application import meeting_action_budget

    monkeypatch.setattr(meeting_action_budget, "meeting_read_token_budget", lambda: 1)
    with pytest.raises(CommandRejected, match="CONSTRAINT_VIOLATION"):
        await module.prepare_report_update(
            MagicMock(), uuid4(), ReportUpdateInput(meeting_id=identity, changes={"title": "After"})
        )
