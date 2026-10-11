"""Frozen deletion scope stays literal and private proof never becomes edit input."""

import json
from uuid import uuid4

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.workboard_delete_schemas import (
    WorkboardDeleteInput,
    WorkboardDeletePatch,
    WorkboardDeleteSelection,
    WorkboardDeleteTarget,
)
from src.domains.agents.application.workboard_delete_spec import WORKBOARD_DELETE_OPERATION
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.workboard.catalogue_manifests import delete_ticket_catalogue_manifest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_deletion_preview_and_editor_privacy(language):
    request_data = WorkboardDeleteInput(ticket_id=uuid4())
    selected = WorkboardDeleteSelection(
        request=request_data,
        items=[
            WorkboardDeleteTarget(
                ticket_id=request_data.ticket_id,
                title="<script>Literal target</script>",
                status="confirming",
                running=True,
                has_pending_action=True,
            )
        ],
        comments=2,
        events=3,
        owned_count=1,
        state_digest="e" * 64,
    )
    draft = build_action_content(
        uuid4(),
        WORKBOARD_DELETE_OPERATION,
        WorkboardDeletePatch(workboard_delete=selected),
        {"workboard_delete": selected.public_scope()},
        {"workboard_delete": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    lines = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(lines)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert labels["application_workboard_delete_note"] in str(lines)
    assert "state_digest" not in str(lines) and "owned_count" not in str(lines)
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Refresh the proposal")
    assert json.loads(prompt[1]["content"])["intent"] == request_data.model_dump(mode="json")
    assert "state_digest" not in str(prompt) and "owned_count" not in str(prompt)
    assert delete_ticket_catalogue_manifest.mutation_policy == "draft"
    assert not delete_ticket_catalogue_manifest.permissions.hitl_required
