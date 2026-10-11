"""Creation schema growth, normalized boundaries, exact draft rendering and safe edit input."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.space_create_manifest import SPACE_CREATE_MANIFEST
from src.domains.agents.application.space_create_schemas import (
    SpaceCreateInput,
    SpaceCreatePatch,
    SpaceCreateSelection,
)
from src.domains.agents.application.space_create_spec import SPACE_CREATE_OPERATION
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.tools.application_space_tools import create_lia_knowledge_space_tool
from src.domains.rag_spaces.schemas import RAGSpaceCreate, RAGSpaceUpdate

pytestmark = pytest.mark.unit


def test_creation_inherits_reviewed_source_fields_and_both_modes_publish_them():
    assert set(RAGSpaceCreate.model_fields) == {"name", "description"}
    assert set(SpaceCreateInput.model_fields) == set(RAGSpaceCreate.model_fields)
    assert SPACE_CREATE_MANIFEST.parameters[0].schema == SpaceCreateInput.model_json_schema()
    assert (
        SPACE_CREATE_MANIFEST.mutation_policy == "draft"
        and not SPACE_CREATE_MANIFEST.permissions.hitl_required
    )
    schema = create_lia_knowledge_space_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"request"}
    assert schema["$defs"]["SpaceCreateInput"]["properties"]["name"]["maxLength"] == 200


@pytest.mark.parametrize("model", [RAGSpaceCreate, RAGSpaceUpdate, SpaceCreateInput])
@pytest.mark.parametrize("name", ["  ", " x "])
def test_name_bounds_apply_after_source_whitespace_normalization(model, name):
    with pytest.raises(ValidationError):
        model(name=name)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_literal_scope_and_source_safe_editor_are_available_in_all_six_languages(language):
    selected = SpaceCreateSelection(
        request=SpaceCreateInput(name="<script>Literal</script>", description="My description"),
        owned_count=2,
        max_spaces=10,
    )
    draft = build_action_content(
        uuid4(),
        SPACE_CREATE_OPERATION,
        SpaceCreatePatch(space_create=selected),
        {"space_create": selected.public_scope()},
        {"space_create": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    assert labels["application_field_space_create"] and labels["application_space_create_note"]
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>Literal</script>" not in html and "&lt;script&gt;Literal&lt;/script&gt;" in html
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Change description")
    assert json.loads(prompt[1]["content"])["intent"] == selected.request.model_dump(mode="json")
    assert "owned_count" not in str(prompt) and "max_spaces" not in str(prompt)
    assert "actor_id" not in str(prompt) and "command_id" not in str(prompt)
