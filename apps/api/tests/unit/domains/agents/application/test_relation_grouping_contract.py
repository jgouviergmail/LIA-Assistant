"""Grouping is an explicit local identity change, never inferred account sharing."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.relation_grouping_schemas import (
    RelationGroupingPatch,
    RelationGroupingRequest,
)
from src.domains.agents.application.relation_grouping_spec import RELATION_GROUPING_OPERATION
from src.domains.relations.grouping_commands import RelationGroupingSelection

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "merge", "source": "Alice"},
        {"action": "merge", "source": "Alice", "target": "ALICE"},
        {"action": "merge", "source": " ", "target": "Bob"},
        {"action": "split", "source": "Alice", "target": "Bob"},
        {"action": "share", "source": "Alice"},
        {"action": "split", "source": "Alice", "user_id": "other"},
        {"action": "split", "source": "Alice", "scope_digest": "forged"},
    ],
)
def test_grouping_requires_valid_explicit_source_names_and_no_authority_input(payload):
    with pytest.raises(ValidationError):
        RelationGroupingRequest.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_grouping_confirmation_and_editor_hide_private_source_proof(language):
    selected = RelationGroupingSelection(
        action="merge",
        source="Papa",
        target="Bob",
        source_key="papa",
        source_canonical="jean dupont",
        target_canonical="bob",
        affected_spellings=1,
        debriefs_to_invalidate=3,
        no_op=False,
        scope_digest="a" * 64,
    )
    draft = build_action_content(
        uuid4(),
        RELATION_GROUPING_OPERATION,
        RelationGroupingPatch(relation_grouping=selected),
        {"relation_grouping": selected.public_scope()},
        {"relation_grouping": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    rendered = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_relation_grouping_note"] in rendered
    assert "Papa" in rendered and "Bob" in rendered
    assert "scope_digest" not in rendered
    editor = build_application_edit_prompt(draft.model_dump(mode="json"), "Choose Carol instead")
    assert json.loads(editor[1]["content"])["intent"] == {
        "action": "merge",
        "source": "Papa",
        "target": "Bob",
    }
    assert "scope_digest" not in str(editor)
