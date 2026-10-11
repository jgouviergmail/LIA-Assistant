"""Source growth is visible in schemas and demands a deliberate semantic review."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.workboard_create_schemas import (
    WorkboardCreateInput,
    WorkboardCreatePatch,
    WorkboardCreateSelection,
)
from src.domains.agents.application.workboard_create_spec import WORKBOARD_CREATE_OPERATION
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.workboard.catalogue_manifests import create_ticket_catalogue_manifest
from src.domains.workboard.schemas import TicketCreate

pytestmark = pytest.mark.unit


def test_source_fields_extend_request_but_require_semantic_review():
    fields = {
        "title",
        "description",
        "priority",
        "status",
        "start_at",
        "due_at",
        "assignee",
        "assignee_user_id",
        "parent_id",
        "execution_mode",
        "follow",
    }
    assert set(TicketCreate.model_fields) == fields == set(WorkboardCreateInput.model_fields)
    assert (
        next(p for p in create_ticket_catalogue_manifest.parameters if p.name == "request").schema
        == WorkboardCreateInput.model_json_schema()
    )
    assert create_ticket_catalogue_manifest.mutation_policy == "draft"
    for extra in (
        {"owner_user_id": str(uuid4())},
        {"follow": "true"},
        {"start_at": "2026-10-09T12:00:00"},
    ):
        with pytest.raises(ValidationError):
            WorkboardCreateInput(title="Ticket", **extra)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_ticket_creation_escapes_brief_and_excludes_private_context(language):
    request = WorkboardCreateInput(
        title="<script>title</script>",
        description="<script>literal brief</script>",
        assignee="lia",
        execution_mode="pipeline",
    )
    selected = WorkboardCreateSelection(
        request=request,
        assignee_kind="lia",
        holder_id=None,
        holder_name=None,
        parent_title=None,
        owned_count=0,
        max_tickets=5,
        state_digest="e" * 64,
    )
    draft = build_action_content(
        uuid4(),
        WORKBOARD_CREATE_OPERATION,
        WorkboardCreatePatch(workboard_create=selected),
        {"workboard_create": selected.public_scope()},
        {"workboard_create": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    lines = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(lines)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert labels["application_workboard_create_note"] in str(lines)
    assert "state_digest" not in str(lines)
    editor = build_application_edit_prompt(draft.model_dump(mode="json"), "Make this my own task")
    assert json.loads(editor[1]["content"])["intent"] == request.model_dump(mode="json")
    assert "state_digest" not in str(editor) and "e" * 64 not in str(editor)
