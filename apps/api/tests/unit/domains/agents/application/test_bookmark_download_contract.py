"""Download consent/checkpoint/editing carries only metadata, never full copied answer bytes."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.bookmark_download_schemas import (
    BookmarkDownloadInput,
    BookmarkDownloadPatch,
    BookmarkDownloadSnapshot,
)
from src.domains.agents.application.bookmark_download_spec import BOOKMARK_DOWNLOAD_OPERATION
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.effects.labels import build_effect_label
from src.domains.agents.tools.application_bookmark_tools import download_lia_saved_answer_tool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra",
    [
        {"user_id": uuid4()},
        {"content": "invented answer"},
        {"state_digest": "f" * 64},
        {"path": "private.bin"},
    ],
)
def test_download_does_not_accept_invented_content_authority_or_storage_path(extra):
    with pytest.raises(ValidationError):
        BookmarkDownloadInput.model_validate({"bookmark_id": uuid4(), **extra})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_download_consent_checkpoint_and_editor_keep_export_witness_private(language):
    scope = BookmarkDownloadSnapshot(
        request=BookmarkDownloadInput(bookmark_id=uuid4()),
        answered_at=datetime.now(UTC),
        answer_preview="<script>literal</script>",
        request_preview="Original request",
        filename="lia-answer.md",
        file_bytes=200_000,
        state_digest="f" * 64,
    )
    draft = build_action_content(
        uuid4(),
        BOOKMARK_DOWNLOAD_OPERATION,
        BookmarkDownloadPatch(saved_answer_to_download=scope),
        {"saved_answer_to_download": None},
        {"saved_answer_to_download": scope.public_scope()},
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    labels = get_draft_preview_labels(language)
    assert (
        labels["application_bookmark_download_note"]
        and labels["application_field_saved_answer_to_download"]
    )
    prompt = str(
        build_application_edit_prompt(
            draft.model_dump(mode="json"), "Download the same saved answer"
        )
    )
    assert "state_digest" not in prompt and "f" * 64 not in prompt
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    assert "f" * 64 not in str(rows)
    label = build_effect_label(
        "draft:application_action",
        {"draft": {"title": "Download saved answer", "operation_id": draft.operation_id}},
    )
    assert label["values"]["operation"] == BOOKMARK_DOWNLOAD_OPERATION.operation_id
    assert set(
        download_lia_saved_answer_tool.tool_call_schema.model_json_schema()["properties"]
    ) == {"request"}
