"""Both reformat modes retain exact consent, owned authority and source privacy."""

from uuid import uuid4

import pytest

from tests.unit.domains.agents.application.test_meeting_regeneration import snapshot

pytestmark = pytest.mark.unit


def test_reformat_input_refuses_destination_account_and_unknown_fields() -> None:
    from pydantic import ValidationError

    from src.domains.agents.application.meeting_reformat_schemas import MeetingReformatInput

    with pytest.raises(ValidationError):
        MeetingReformatInput.model_validate(
            {
                "meeting_id": str(uuid4()),
                "template_ref": "builtin:standard",
                "mode": "new",
                "destination_id": str(uuid4()),
                "user_id": str(uuid4()),
            }
        )


def test_reformat_registered_nonadmin_with_original_hitl_in_both_modes() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.meeting_reformat_spec import (
        MEETING_REFORMAT_MANIFEST,
        MEETING_REFORMAT_OPERATION,
    )
    from src.domains.agents.application.native_operations import NATIVE_OPERATIONS

    assert MEETING_REFORMAT_OPERATION in NATIVE_OPERATIONS
    assert MEETING_REFORMAT_OPERATION.tool_name in APPLICATION_TOOL_NAMES
    assert not MEETING_REFORMAT_OPERATION.administrative
    assert MEETING_REFORMAT_MANIFEST.mutation_policy == "draft"
    assert MEETING_REFORMAT_MANIFEST.execution_modes == {"pipeline", "react"}


@pytest.mark.parametrize("mode", ["replace", "new"])
@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_full_reformat_consent_roundtrip_literal_data_and_no_private_witness(
    mode: str, language: str
) -> None:
    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.application.action_preparation import build_action_content
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.meeting_reformat_schemas import (
        MeetingReformatPatch,
        canonical_meeting_reformat,
        reformat_states,
    )
    from src.domains.agents.application.meeting_reformat_spec import MEETING_REFORMAT_OPERATION
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.agents.drafts.card_html import to_html_card
    from src.domains.agents.drafts.card_spec import CardSpec
    from src.infrastructure.meeting_reformat import MeetingReformatSnapshot

    source = snapshot(language)
    selected = MeetingReformatSnapshot.model_validate(
        {
            "source": source,
            "request": {"template_ref": "builtin:standard", "mode": mode},
            "destination_id": source.meeting_id if mode == "replace" else uuid4(),
            "rag_enabled_at_confirmation": True,
        }
    )
    draft = build_action_content(
        uuid4(),
        MEETING_REFORMAT_OPERATION,
        MeetingReformatPatch(meeting_reformat=selected),
        *reformat_states(selected),
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    assert canonical_meeting_reformat(draft)
    rows = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Change format"))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "source_digest" not in html + prompt and "e" * 64 not in html + prompt
    assert "destination_id" in html and "instruction" in html and "processing_completed" in html
    assert not canonical_meeting_reformat(draft.model_copy(update={"after": {}}))


def test_reformat_growth_requires_ownership_privacy_and_original_contract_review() -> None:
    from src.core.meeting_reformat import MeetingReformatRequest
    from src.domains.agents.application.meeting_reformat_schemas import MeetingReformatInput
    from src.infrastructure.meeting_reformat import (
        ConfirmedReformatRequest,
        MeetingReformatSnapshot,
    )

    assert set(MeetingReformatRequest.model_fields) == {"template_ref", "mode"}
    assert set(MeetingReformatInput.model_fields) == {"meeting_id", "template_ref", "mode"}
    assert set(ConfirmedReformatRequest.model_fields) == {"template_ref", "mode"}
    assert set(MeetingReformatSnapshot.model_fields) == {
        "source",
        "request",
        "destination_id",
        "rag_enabled_at_confirmation",
    }
