"""Owned minutes PDF uses the original authenticated browser transfer seam."""

import pytest

pytestmark = pytest.mark.unit


def test_meeting_pdf_is_a_nonadmin_confirmed_original_browser_transfer() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.meeting_pdf_spec import (
        MEETING_PDF_MANIFEST,
        MEETING_PDF_OPERATION,
    )
    from src.domains.agents.application.native_operations import NATIVE_OPERATIONS

    assert MEETING_PDF_OPERATION.tool_name in APPLICATION_TOOL_NAMES
    assert MEETING_PDF_OPERATION in NATIVE_OPERATIONS
    assert MEETING_PDF_OPERATION.interaction_kind == "device"
    assert not MEETING_PDF_OPERATION.administrative
    assert MEETING_PDF_MANIFEST.mutation_policy == "draft"
    assert MEETING_PDF_MANIFEST.execution_modes == {"pipeline", "react"}


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_pdf_consent_has_full_scope_without_body_or_private_witness(language: str) -> None:
    from uuid import uuid4

    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.application.action_preparation import build_action_content
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.meeting_pdf_schemas import (
        MeetingPDFPatch,
        canonical_meeting_pdf,
    )
    from src.domains.agents.application.meeting_pdf_spec import MEETING_PDF_OPERATION
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.agents.drafts.card_html import to_html_card
    from src.domains.agents.drafts.card_spec import CardSpec
    from src.infrastructure.meeting_pdf import MeetingPDFSnapshot

    selected = MeetingPDFSnapshot(
        meeting_id=uuid4(),
        title="<script>Literal</script>",
        filename="minutes.pdf",
        language=language,
        participants_count=2,
        sections_count=3,
        source_digest="e" * 64,
    )
    draft = build_action_content(
        uuid4(),
        MEETING_PDF_OPERATION,
        MeetingPDFPatch(meeting_pdf_download=selected),
        {"meeting_pdf_download": None},
        {"meeting_pdf_download": selected.public_scope()},
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    assert canonical_meeting_pdf(draft)
    rows = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Refresh this download")
    )
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "source_digest" not in html + prompt and "e" * 64 not in html + prompt
    assert "entire_report" in html and "current" in html
    assert not canonical_meeting_pdf(draft.model_copy(update={"after": {}}))
