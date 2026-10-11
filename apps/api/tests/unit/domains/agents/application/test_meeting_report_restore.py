"""A whole-version restore binds full content without putting it in model prompts."""

import pytest

pytestmark = pytest.mark.unit


def test_restore_witness_is_bounded_and_binds_changed_body_with_same_headings() -> None:
    from uuid import uuid4

    from src.domains.agents.application.meeting_report_restore_schemas import restore_witness
    from src.infrastructure.meeting_reports import MeetingReportState

    report = {
        "title": "Controlled",
        "participants": [],
        "sections": [
            {
                "key": "summary",
                "label": "Summary",
                "kind": "paragraph",
                "paragraph": "private words " * 10000,
            }
        ],
    }
    state = MeetingReportState(
        meeting_id=uuid4(),
        status="ready",
        stage=None,
        location_label=None,
        edited_at=None,
        current=report,
        generated=report,
        matches_generated=True,
        source_digest="a" * 64,
    )
    witness = restore_witness(state)
    assert len(witness.model_dump_json().encode("utf-8")) < 64000
    assert "private words" not in witness.model_dump_json()
    assert witness != restore_witness(state.model_copy(update={"source_digest": "b" * 64}))


def test_restore_tool_is_registered_as_mandatory_nonadmin_hitl() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.meeting_report_restore_spec import (
        REPORT_RESTORE_MANIFEST,
        REPORT_RESTORE_OPERATION,
    )
    from src.domains.agents.application.native_operations import NATIVE_OPERATIONS

    assert REPORT_RESTORE_OPERATION.tool_name in APPLICATION_TOOL_NAMES
    assert REPORT_RESTORE_OPERATION in NATIVE_OPERATIONS
    assert not REPORT_RESTORE_OPERATION.administrative
    assert REPORT_RESTORE_MANIFEST.mutation_policy == "draft"
    assert REPORT_RESTORE_MANIFEST.execution_modes == {"pipeline", "react"}


def test_report_summary_classifies_every_original_root_field() -> None:
    from src.domains.meetings.schemas import MeetingReport

    assert set(MeetingReport.model_fields) == {"title", "participants", "sections"}


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_restoration_preview_is_literal_bounded_and_editor_hides_witness(language: str) -> None:
    from uuid import uuid4

    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.application.action_preparation import build_action_content
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.meeting_report_restore_schemas import (
        ReportRestoreInput,
        ReportRestorePatch,
        ReportRestoreSelection,
        canonical_report_restoration,
        report_restore_states,
        restore_witness,
    )
    from src.domains.agents.application.meeting_report_restore_spec import REPORT_RESTORE_OPERATION
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.agents.application.state_changes import changed_resources
    from src.domains.agents.drafts.card_html import to_html_card
    from src.domains.agents.drafts.card_spec import CardSpec
    from src.infrastructure.meeting_reports import MeetingReportState

    identity = uuid4()
    report = {
        "title": "<script>Literal</script>",
        "participants": [],
        "sections": [
            {"label": f"Section {n}", "paragraph": "private body " * 600} for n in range(20)
        ],
    }
    state = MeetingReportState(
        meeting_id=identity,
        status="ready",
        stage=None,
        location_label="Place",
        edited_at=None,
        current=report,
        generated=report,
        matches_generated=True,
        source_digest="e" * 64,
    )
    selected = ReportRestoreSelection(
        request=ReportRestoreInput(meeting_id=identity), expected=restore_witness(state)
    )
    assert selected.expected.generated.sections_count == 20
    assert len(selected.expected.generated.headings) == 12
    draft = build_action_content(
        uuid4(),
        REPORT_RESTORE_OPERATION,
        ReportRestorePatch(meeting_report_restore=selected),
        *report_restore_states(selected),
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    assert canonical_report_restoration(draft)
    rows = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Choose another meeting")
    )
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "summary_only" in html
    assert "private body" not in html + prompt
    assert "source_digest" not in html + prompt and "e" * 64 not in html + prompt
    assert "sections_count" not in prompt
    assert changed_resources(draft) == ["meetings"]
    tampered = draft.model_copy(update={"after": {}})
    assert not canonical_report_restoration(tampered)


@pytest.mark.parametrize(
    "extra", [{"user_id": "forged"}, {"force": True}, {"source_digest": "a" * 64}]
)
def test_restore_request_cannot_forge_source_or_authority(extra: dict[str, object]) -> None:
    from uuid import uuid4

    from pydantic import ValidationError

    from src.domains.agents.application.meeting_report_restore_schemas import ReportRestoreInput

    with pytest.raises(ValidationError):
        ReportRestoreInput.model_validate({"meeting_id": str(uuid4()), **extra})
