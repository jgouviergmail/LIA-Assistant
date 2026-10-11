"""Source schema growth, actual tool binding, sparse intent and literal consent rendering."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.space_update_manifest import SPACE_UPDATE_MANIFEST
from src.domains.agents.application.space_update_schemas import (
    SpaceUpdateInput,
    SpaceUpdatePatch,
    SpaceUpdateSelection,
    SpaceUpdateTarget,
)
from src.domains.agents.application.space_update_spec import SPACE_UPDATE_OPERATION
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.tools.application_space_tools import update_lia_knowledge_space_tool
from src.domains.rag_spaces.schemas import RAGSpaceUpdate

pytestmark = pytest.mark.unit


def test_update_inherits_source_fields_and_actual_tool_schema_in_both_modes():
    assert set(RAGSpaceUpdate.model_fields) == {"name", "description"}
    assert set(SpaceUpdateInput.model_fields) == {
        *RAGSpaceUpdate.model_fields,
        "space_id",
        "is_active",
    }
    assert SPACE_UPDATE_MANIFEST.parameters[0].schema == SpaceUpdateInput.model_json_schema()
    assert (
        SPACE_UPDATE_MANIFEST.mutation_policy == "draft"
        and not SPACE_UPDATE_MANIFEST.permissions.hitl_required
    )
    bound = update_lia_knowledge_space_tool.tool_call_schema.model_json_schema()
    assert set(bound["properties"]) == {"request"}
    assert set(bound["$defs"]["SpaceUpdateInput"]["properties"]) == set(
        SpaceUpdateInput.model_fields
    )


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"description": None},
        {"is_active": "false"},
        {"is_active": 0},
        {"user_id": str(uuid4())},
        {"name": " x "},
    ],
)
def test_empty_coerced_or_unowned_requests_are_refused(changes):
    with pytest.raises(ValidationError):
        SpaceUpdateInput.model_validate({"space_id": uuid4(), **changes})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_exact_literal_preview_and_safe_sparse_edit_input(language):
    identity = uuid4()
    before = SpaceUpdateTarget(
        id=identity, name="Original", description="Purpose", is_active=True, kind="meetings"
    )
    after = SpaceUpdateTarget(
        id=identity,
        name="<script>Literal</script>",
        description="Purpose",
        is_active=False,
        kind="meetings",
    )
    selected = SpaceUpdateSelection(
        request=SpaceUpdateInput(space_id=identity, name=after.name, is_active=False),
        expected=before,
        proposed=after,
        state_digest="a" * 64,
        result_digest="b" * 64,
    )
    draft = build_action_content(
        uuid4(),
        SPACE_UPDATE_OPERATION,
        SpaceUpdatePatch(space_update=selected),
        {"space_update": selected.public_scope()},
        {"space_update": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    assert labels["application_field_space_update"] and labels["application_space_update_note"]
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>Literal</script>" not in html and "&lt;script&gt;Literal&lt;/script&gt;" in html
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Change description")
    assert json.loads(prompt[1]["content"])["intent"] == selected.request.model_dump(
        mode="json", exclude_unset=True
    )
    assert "state_digest" not in str(prompt) and "result_digest" not in str(prompt)
    assert "actor_id" not in str(prompt) and "command_id" not in str(prompt)
