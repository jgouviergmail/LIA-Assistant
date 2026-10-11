"""Source-field growth, strict controls, private edit input and literal previews stay explicit."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.workboard_update_schemas import (
    WorkboardUpdateInput,
    WorkboardUpdatePatch,
    WorkboardUpdateSelection,
)
from src.domains.agents.application.workboard_update_spec import WORKBOARD_UPDATE_OPERATION
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.tools.workboard_tools import update_ticket_tool
from src.domains.agents.workboard.catalogue_manifests import update_ticket_catalogue_manifest
from src.domains.workboard.schemas import TicketUpdate

pytestmark = pytest.mark.unit


def test_full_source_update_schema_is_reviewed_and_bound_to_both_modes():
    assert set(TicketUpdate.model_fields) == {
        "title",
        "description",
        "priority",
        "status",
        "start_at",
        "due_at",
        "clear_start_at",
        "clear_due_at",
        "assignee",
        "assignee_user_id",
        "execution_mode",
        "follow",
    }
    assert set(WorkboardUpdateInput.model_fields) == set(TicketUpdate.model_fields) | {
        "ticket_id",
        "move",
        "run_now",
    }
    assert update_ticket_catalogue_manifest.mutation_policy == "draft"
    assert not update_ticket_catalogue_manifest.permissions.hitl_required
    request_schema = next(
        param.schema
        for param in update_ticket_catalogue_manifest.parameters
        if param.name == "request"
    )
    assert request_schema == WorkboardUpdateInput.model_json_schema()
    assert "request" in update_ticket_tool.tool_call_schema.model_json_schema()["properties"]
    assert not next(
        param.required
        for param in update_ticket_catalogue_manifest.parameters
        if param.name == "ticket"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"run_now": "false"},
        {"follow": 1},
        {"clear_due_at": "true"},
        {"start_at": "2026-10-09T10:00:00"},
        {"move": {"status": "done", "position": True}},
        {"move": {"status": "done", "position": 0}, "status": "todo"},
        {"run_now": True, "status": "done"},
        {"due_at": "2026-10-09T10:00:00Z", "clear_due_at": True},
    ],
)
def test_malformed_or_contradictory_native_control_is_refused(changes):
    with pytest.raises(ValidationError):
        WorkboardUpdateInput.model_validate({"ticket_id": str(uuid4()), **changes})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_update_preview_and_edit_prompt_boundaries(language):
    request_data = WorkboardUpdateInput(
        ticket_id=uuid4(), title="<script>New literal title</script>"
    )
    scope = WorkboardUpdateSelection(
        request=request_data,
        before={"title": "Old title"},
        after={"title": request_data.title},
        pending_preview=["<script>Pending source content</script>"],
        answer_note=None,
        answer=None,
        pending_before=True,
        pending_after=True,
        pending_approved=False,
        holder_name=None,
        owner_id=uuid4(),
        requires_peers=False,
        statuses=("todo",),
        events_before=1,
        expected_events=[],
        state_digest="e" * 64,
        result_digest="f" * 64,
    )
    draft = build_action_content(
        scope.owner_id,
        WORKBOARD_UPDATE_OPERATION,
        WorkboardUpdatePatch(workboard_update=scope),
        {"workboard_update": scope.public_scope()},
        {"workboard_update": scope.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    lines = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(lines)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert labels["application_workboard_update_note"] in str(lines)
    assert "state_digest" not in str(lines) and "result_digest" not in str(lines)
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Change the title")
    assert json.loads(prompt[1]["content"])["intent"] == request_data.model_dump(
        mode="json", exclude_none=True
    )
    assert (
        "state_digest" not in str(prompt)
        and "pending_preview" not in str(prompt)
        and "expected_events" not in str(prompt)
    )
