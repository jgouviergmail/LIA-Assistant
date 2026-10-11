"""Favorite editors receive only the public selector; full identity proof stays private."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.relation_favorite_schemas import (
    RelationFavoritePatch,
    RelationFavoriteRequest,
    RelationFavoriteValues,
)
from src.domains.agents.application.relation_favorite_spec import RELATION_FAVORITE_OPERATION
from src.domains.relations.favorite_commands import RelationFavoriteSelection

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "starred": False},
        {"name": "Alice", "starred": "true"},
        {"name": "Alice", "starred": None},
        {"name": "Alice", "starred": True, "user_id": "other"},
        {"name": "Alice", "starred": True, "scope_digest": "forged"},
    ],
)
def test_favorite_input_rejects_coercions_and_forged_authority(payload):
    with pytest.raises(ValidationError):
        RelationFavoriteRequest.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_favorite_preview_and_editor_show_only_the_approved_display_state(language):
    expected = RelationFavoriteSelection(
        name="Alice", canonical_key="alice", starred=True, scope_digest="a" * 64
    )
    patch = RelationFavoritePatch(
        relation_favorite=RelationFavoriteValues(expected=expected, starred=False)
    )
    draft = build_action_content(
        uuid4(),
        RELATION_FAVORITE_OPERATION,
        patch,
        {"relation_favorite": expected.public_scope()},
        {"relation_favorite": {**expected.public_scope(), "starred": False}},
    )
    labels = get_draft_preview_labels(language)
    rendered = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_relation_favorite_note"] in rendered and "Alice" in rendered
    assert "scope_digest" not in rendered
    editor = build_application_edit_prompt(draft.model_dump(mode="json"), "Star Bob instead")
    assert json.loads(editor[1]["content"])["intent"] == {"name": "Alice", "starred": False}
    assert "scope_digest" not in str(editor)
