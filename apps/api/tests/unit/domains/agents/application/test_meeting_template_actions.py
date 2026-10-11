"""Template arguments reuse the original contracts without exposing actor or quota fields."""

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_native_creation_inherits_every_original_input_field() -> None:
    from src.domains.agents.application.meeting_template_schemas import TemplateCreateInput
    from src.domains.meetings.schemas import MeetingTemplateCreate

    assert set(TemplateCreateInput.model_fields) == set(MeetingTemplateCreate.model_fields)


def test_sparse_edits_cover_original_fields_and_cannot_transfer_ownership() -> None:
    from src.domains.agents.application.meeting_template_schemas import TemplateEditValues
    from src.domains.meetings.schemas import MeetingTemplateResponse, MeetingTemplateUpdate

    assert set(TemplateEditValues.model_fields) == set(MeetingTemplateUpdate.model_fields)
    assert set(MeetingTemplateUpdate.model_fields) <= set(MeetingTemplateResponse.model_fields)
    assert not {"id", "user_id", "builtin_key", "created_at", "updated_at"} & set(
        MeetingTemplateUpdate.model_fields
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"duplicate_of": "builtin:default_minutes", "user_id": "forged"},
        {"duplicate_of": "builtin:default_minutes", "maximum": 999},
        {
            "name": "Controlled",
            "sections": [
                {
                    "key": "summary",
                    "label": "Summary",
                    "instruction": "Literal",
                    "kind": "paragraph",
                    "execute": True,
                }
            ],
        },
    ],
)
def test_hidden_authority_and_unknown_section_fields_are_rejected(payload: object) -> None:
    from src.domains.agents.application.meeting_template_schemas import TemplateCreateInput

    with pytest.raises(ValidationError):
        TemplateCreateInput.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
@pytest.mark.parametrize("action", ["create", "update", "delete"])
def test_exact_full_consent_roundtrip_and_safe_sparse_editor(language: str, action: str) -> None:
    from uuid import uuid4

    from src.core.i18n_drafts import get_draft_preview_labels
    from src.core.meeting_templates import MeetingTemplateResponse
    from src.domains.agents.application.action_preparation import build_action_content
    from src.domains.agents.application.draft_models import ApplicationActionDraftContent
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.meeting_template_schemas import (
        TemplateCreateInput,
        TemplateCreatePatch,
        TemplateCreation,
        TemplateDeleteInput,
        TemplateDeletePatch,
        TemplateRemoval,
        TemplateReplacement,
        TemplateUpdateInput,
        TemplateUpdatePatch,
        desired_template_update,
        template_creation_states,
        template_removal_states,
        template_replacement_states,
    )
    from src.domains.agents.application.meeting_template_spec import (
        TEMPLATE_CREATE_OPERATION,
        TEMPLATE_DELETE_OPERATION,
        TEMPLATE_UPDATE_OPERATION,
    )
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.agents.drafts.card_html import to_html_card
    from src.domains.agents.drafts.card_spec import CardSpec
    from src.infrastructure.meeting_templates import TemplateWriteFacts

    identity = uuid4()
    ref = f"user:{identity}"
    instruction = "<script>literal</script> " + "完整内容" * 140
    sections = [
        {
            "key": f"section_{number}",
            "label": f"Section {number}",
            "instruction": instruction,
            "kind": "paragraph",
        }
        for number in range(12)
    ]
    before = MeetingTemplateResponse(
        ref=ref,
        id=identity,
        name="Original",
        description="private-description-229",
        category="custom",
        sections=sections,
        builtin=False,
        builtin_key=None,
        auto_selectable=True,
    )
    if action == "create":
        selection = TemplateCreation(
            request=TemplateCreateInput(name="New", sections=sections),
            expected=TemplateWriteFacts(
                count=1,
                maximum=10,
                values={
                    "name": "New",
                    "description": None,
                    "category": "custom",
                    "sections": sections,
                    "builtin_key": None,
                },
            ),
            created_id=identity,
        )
        patch = TemplateCreatePatch(meeting_template_create=selection)
        states = template_creation_states(selection)
        spec = TEMPLATE_CREATE_OPERATION
    elif action == "update":
        request = TemplateUpdateInput(ref=ref, changes={"name": "New"})
        selection = TemplateReplacement(
            request=request, expected=before, desired=desired_template_update(request, before)
        )
        patch = TemplateUpdatePatch(meeting_template_update=selection)
        states = template_replacement_states(selection)
        spec = TEMPLATE_UPDATE_OPERATION
    else:
        selection = TemplateRemoval(
            request=TemplateDeleteInput(ref=ref), expected=before, default_template_ref=ref
        )
        patch = TemplateDeletePatch(meeting_template_delete=selection)
        states = template_removal_states(selection)
        spec = TEMPLATE_DELETE_OPERATION
    draft = build_action_content(uuid4(), spec, patch, *states)
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    rows = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert html.count("完整内容" * 140) >= 12
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Change request"))
    assert "created_id" not in prompt and "expected" not in prompt and "maximum" not in prompt
    if action == "update":
        assert "private-description-229" not in prompt and instruction not in prompt
