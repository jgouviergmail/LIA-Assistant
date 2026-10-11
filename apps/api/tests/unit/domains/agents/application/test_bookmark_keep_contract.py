"""Native saved-answer consent survives checkpoints and never offers private copy witnesses to editors."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.bookmark_keep_manifest import BOOKMARK_KEEP_MANIFEST
from src.domains.agents.application.bookmark_keep_schemas import (
    BookmarkKeepInput,
    BookmarkKeepObservation,
    BookmarkKeepPatch,
    ResolvedBookmarkKeepInput,
)
from src.domains.agents.application.bookmark_keep_spec import BOOKMARK_KEEP_OPERATION
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.state_changes import changed_resources
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.effects.labels import build_effect_label
from src.domains.agents.tools.application_bookmark_tools import keep_lia_saved_answer_tool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra",
    [
        {"user_id": uuid4()},
        {"force": True},
        {"copy_digest": "f" * 64},
        {"max_per_user": 999},
        {"content": "invented answer"},
    ],
)
def test_saving_never_accepts_an_invented_copy_or_override(extra):
    with pytest.raises(ValidationError):
        BookmarkKeepInput.model_validate({"message_id": uuid4(), **extra})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_keep_preview_checkpoint_editing_and_action_identity_are_exact(language):
    selected = BookmarkKeepObservation(
        request=ResolvedBookmarkKeepInput(message_id=uuid4()),
        conversation_id=uuid4(),
        answered_at=datetime.now(UTC),
        answer_preview="<script>literal</script>",
        request_preview="Actual request",
        answer_chars=100_000,
        request_chars=14,
        existing_id=None,
        kept_count=1,
        max_per_user=100,
        copy_digest="f" * 64,
    )
    draft = build_action_content(
        uuid4(),
        BOOKMARK_KEEP_OPERATION,
        BookmarkKeepPatch(saved_answer_to_keep=selected),
        {"saved_answer_to_keep": selected.public_scope()},
        {"saved_answer_to_keep": selected.public_scope(after=True)},
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    labels = get_draft_preview_labels(language)
    assert (
        labels["application_bookmark_keep_note"]
        and labels["application_field_saved_answer_to_keep"]
    )
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Save the same answer")
    )
    assert "copy_digest" not in prompt and "f" * 64 not in prompt and "f" * 64 not in html
    assert changed_resources(draft) == ["generated_assets"]
    label = build_effect_label(
        "draft:application_action",
        {"draft": {"title": "Save answer", "operation_id": draft.operation_id}},
    )
    assert label["values"]["operation"] == BOOKMARK_KEEP_OPERATION.operation_id
    assert set(keep_lia_saved_answer_tool.tool_call_schema.model_json_schema()["properties"]) == {
        "request"
    }
    assert (
        BOOKMARK_KEEP_MANIFEST.mutation_policy == "draft"
        and not BOOKMARK_KEEP_MANIFEST.initiative_eligible
    )
