"""Refresh exposes a finite explicit source selection, never an actor or cache policy."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.relation_context_refresh_schemas import (
    RelationContextRefreshPatch,
    RelationContextRefreshRequest,
)
from src.domains.agents.application.relation_context_refresh_spec import (
    RELATION_CONTEXT_REFRESH_OPERATION,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Alice", "sections": []},
        {"name": "Alice", "sections": ["contact", "contact"]},
        {"name": "Alice", "sections": ["all"]},
        {"name": "Alice", "sections": ["contact"], "actor_id": "other"},
        {"name": "Alice", "sections": ["contact"], "force": True},
    ],
)
def test_refresh_refuses_unconfirmed_scope(payload):
    with pytest.raises(ValidationError):
        RelationContextRefreshRequest.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_refresh_preview_and_editor_publish_exact_request(language):
    selected = RelationContextRefreshRequest(name="Alice", sections=["emails"])
    public = selected.model_dump(mode="json")
    draft = build_action_content(
        uuid4(),
        RELATION_CONTEXT_REFRESH_OPERATION,
        RelationContextRefreshPatch(relation_context=selected),
        {"relation_context": public},
        {"relation_context": {**public, "refresh_requested": True}},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda v: v or "")
    )
    assert labels["application_relation_context_refresh_note"] in preview and "Alice" in preview
    assert "emails" in preview
    editor = build_application_edit_prompt(
        draft.model_dump(mode="json"), "Refresh Bob's events instead"
    )
    assert json.loads(editor[1]["content"])["intent"] == public
