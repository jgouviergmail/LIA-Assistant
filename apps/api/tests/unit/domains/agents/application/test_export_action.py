"""A full-account export is confirmed intent, never an archive or credential payload."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.exceptions import AuthorizationError
from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.export_action import (
    EXPORT_REQUEST_OPERATION,
    AccountExportRequest,
    prepare_account_export,
)
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.drafts.card_spec import Note

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "intent", [{"account_export": False}, {"password": "private"}, {"scope": ["users"]}]
)
def test_export_request_cannot_select_partial_scope_or_carry_credentials(
    intent: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AccountExportRequest.model_validate(intent)


async def test_preparation_requires_the_originating_browser_before_reading_account_data() -> None:
    db = AsyncMock()
    with pytest.raises(AuthorizationError):
        await prepare_account_export(db, uuid4(), origin=None)
    db.execute.assert_not_awaited()
    db.scalar.assert_not_awaited()


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_export_preview_and_editor_keep_full_scope_and_credentials_out_of_the_model(
    language: str,
) -> None:
    content = build_action_content(
        uuid4(),
        EXPORT_REQUEST_OPERATION,
        AccountExportRequest(account_export=True),
        {"account_export": False},
        {"account_export": True},
    ).model_dump(mode="json")
    labels = get_draft_preview_labels(language)
    lines = render_application_preview(content, labels, lambda value: value or "")
    assert len(lines) == 2 and lines[0] == Note(text=labels["application_export_note"])
    prompt = str(build_application_edit_prompt(content, "refresh"))
    assert str(content["actor_id"]) not in prompt and "password" not in prompt
    assert '"intent": {}' in prompt
    content["before"] = {"account_export": True}
    assert render_application_preview(content, labels, lambda value: value or "") == [
        Note(text=labels["application_unavailable"])
    ]
