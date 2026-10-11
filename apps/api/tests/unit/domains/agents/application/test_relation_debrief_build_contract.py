"""Paid build approval/editor shares public scope while withholding source proofs."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.relation_debrief_build_schemas import (
    RelationDebriefBuildPatch,
    RelationDebriefBuildRequest,
    RelationDebriefBuildScope,
)
from src.domains.agents.application.relation_debrief_build_spec import (
    RELATION_DEBRIEF_BUILD_OPERATION,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " "},
        {"name": "Alice", "force": "true"},
        {"name": "Alice", "user_id": "other"},
        {"name": "Alice", "input_digest": "forged"},
    ],
)
def test_build_inputs_reject_authority_and_boolean_coercion(payload):
    with pytest.raises(ValidationError):
        RelationDebriefBuildRequest.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_build_preview_and_editor_bound_public_source_scope(language):
    scope = RelationDebriefBuildScope(
        request=RelationDebriefBuildRequest(name="Alice", force=True),
        canonical_key="alice",
        input_digest="a" * 64,
        debrief_digest="b" * 64,
        status="ready",
        language="fr",
        scope={"sections": ["open_loops"], "max_items": 3},
    )
    draft = build_action_content(
        uuid4(),
        RELATION_DEBRIEF_BUILD_OPERATION,
        RelationDebriefBuildPatch(relation_debrief=scope),
        {"relation_debrief": scope.public_scope()},
        {"relation_debrief": {**scope.public_scope(), "requested": True}},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda v: v or "")
    )
    assert labels["application_relation_debrief_build_note"] in preview and "Alice" in preview
    assert "input_digest" not in preview and "debrief_digest" not in preview
    editor = build_application_edit_prompt(
        draft.model_dump(mode="json"), "Generate for Bob instead"
    )
    assert json.loads(editor[1]["content"])["intent"] == {"name": "Alice", "force": True}
    assert "input_digest" not in str(editor) and "debrief_digest" not in str(editor)
