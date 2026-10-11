"""Source field growth, literal rendering and editor privacy have an explicit contract."""

import json
from uuid import uuid4

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.workboard_comment_schemas import (
    WorkboardCommentInput,
    WorkboardCommentPatch,
    WorkboardCommentSelection,
)
from src.domains.agents.application.workboard_comment_spec import WORKBOARD_COMMENT_OPERATION
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.workboard.catalogue_manifests import comment_ticket_catalogue_manifest
from src.domains.workboard.schemas import CommentCreate

pytestmark = pytest.mark.unit


def test_comment_source_growth_requires_review_and_manifest_is_confirmed():
    assert set(CommentCreate.model_fields) == {"body"}
    assert set(WorkboardCommentInput.model_fields) == set(CommentCreate.model_fields) | {
        "ticket_id"
    }
    assert comment_ticket_catalogue_manifest.mutation_policy == "draft"
    # The draft executor owns confirmation; planner HITL here would ask twice.
    assert not comment_ticket_catalogue_manifest.permissions.hitl_required
    from src.core.config import settings
    from src.domains.agents.tools.workboard_tools import comment_ticket_tool

    assert (
        comment_ticket_tool.tool_call_schema.model_json_schema()["properties"]["body"]["maxLength"]
        == settings.workboard_comment_max_chars
    )


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_comment_preview_and_editor_boundaries(language):
    request_data = WorkboardCommentInput(ticket_id=uuid4(), body="<script>literal comment</script>")
    selection = WorkboardCommentSelection(
        request=request_data,
        title="<script>title</script>",
        owner_id=uuid4(),
        status="todo",
        assignee_kind="human",
        holder_id=uuid4(),
        answer=None,
        pending_preview=[],
        max_comment_chars=4000,
        max_runs=10,
        state_digest="e" * 64,
    )
    draft = build_action_content(
        uuid4(),
        WORKBOARD_COMMENT_OPERATION,
        WorkboardCommentPatch(workboard_comment=selection),
        {"workboard_comment": selection.public_scope()},
        {"workboard_comment": selection.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    lines = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(lines)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert labels["application_workboard_comment_note"] in str(lines)
    assert "state_digest" not in str(lines)
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Change the wording")
    assert json.loads(prompt[1]["content"])["intent"] == request_data.model_dump(mode="json")
    assert "state_digest" not in str(prompt) and "pending_preview" not in str(prompt)
