"""Saved-copy deletion preserves checkpoint, exact action and private-editor boundaries."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.bookmark_delete_schemas import (
    BookmarkDeleteInput,
    BookmarkDeleteObservation,
    BookmarkDeletePatch,
)
from src.domains.agents.application.bookmark_delete_spec import BOOKMARK_DELETE_OPERATION
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.state_changes import changed_resources
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.effects.labels import build_effect_label
from src.domains.agents.tools.application_bookmark_tools import delete_lia_saved_answer_tool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra",
    [{"user_id": uuid4()}, {"force": True}, {"state_digest": "f" * 64}, {"content": "invented"}],
)
def test_saved_copy_removal_never_accepts_authority_or_private_witness(extra):
    with pytest.raises(ValidationError):
        BookmarkDeleteInput.model_validate({"bookmark_id": uuid4(), **extra})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_saved_copy_removal_checkpoint_render_editor_and_action_identity(language):
    scope = BookmarkDeleteObservation(
        request=BookmarkDeleteInput(bookmark_id=uuid4()),
        answered_at=datetime.now(UTC),
        answer_preview="<script>literal</script>",
        request_preview=None,
        answer_chars=100_000,
        request_chars=None,
        projection=None,
        space_id=None,
        chunks=0,
        state_digest="f" * 64,
        file=None,
    )
    draft = build_action_content(
        uuid4(),
        BOOKMARK_DELETE_OPERATION,
        BookmarkDeletePatch(saved_answer_to_delete=scope),
        {"saved_answer_to_delete": scope.public_scope()},
        {"saved_answer_to_delete": scope.public_scope(after=True)},
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    labels = get_draft_preview_labels(language)
    assert (
        labels["application_bookmark_delete_note"]
        and labels["application_field_saved_answer_to_delete"]
    )
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Remove the same saved copy")
    )
    assert "state_digest" not in prompt and "f" * 64 not in prompt and "f" * 64 not in html
    assert changed_resources(draft) == ["generated_assets"]
    label = build_effect_label(
        "draft:application_action",
        {"draft": {"title": "Delete saved answer", "operation_id": draft.operation_id}},
    )
    assert label["values"]["operation"] == BOOKMARK_DELETE_OPERATION.operation_id
    assert set(delete_lia_saved_answer_tool.tool_call_schema.model_json_schema()["properties"]) == {
        "request"
    }
