"""Deletion schema, literal scope, private-state exclusion and actual tool-mode binding."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.space_delete_manifest import SPACE_DELETE_MANIFEST
from src.domains.agents.application.space_delete_schemas import (
    SpaceDeleteDocument,
    SpaceDeleteInput,
    SpaceDeletePatch,
    SpaceDeleteSelection,
    SpaceDeleteSource,
)
from src.domains.agents.application.space_delete_spec import SPACE_DELETE_OPERATION
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.tools.application_space_tools import delete_lia_knowledge_space_tool

pytestmark = pytest.mark.unit


def test_both_modes_bind_one_real_space_id_and_mandatory_native_consent():
    assert SPACE_DELETE_MANIFEST.parameters[0].schema == SpaceDeleteInput.model_json_schema()
    assert (
        SPACE_DELETE_MANIFEST.mutation_policy == "draft"
        and not SPACE_DELETE_MANIFEST.permissions.hitl_required
    )
    schema = delete_lia_knowledge_space_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"request"}
    assert set(schema["$defs"]["SpaceDeleteInput"]["properties"]) == {"space_id"}
    for extra in ({"user_id": str(uuid4())}, {"delete_all": True}, {"space_id": "any"}):
        with pytest.raises(ValidationError):
            SpaceDeleteInput.model_validate({"space_id": str(uuid4()), **extra})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_preview_names_all_local_deletion_scope_and_editor_gets_only_the_source_id(language):
    identity = uuid4()
    selected = SpaceDeleteSelection(
        request=SpaceDeleteInput(space_id=identity),
        space=SpaceUpdateTarget(
            id=identity, name="My corpus", description=None, is_active=True, kind=None
        ),
        items=[
            SpaceDeleteDocument(
                id=uuid4(),
                original_filename="<script>Literal</script>.txt",
                status="ready",
                source_type="upload",
                file_size=17,
            )
        ],
        drive_sources=[SpaceDeleteSource(id=uuid4(), name="My folder")],
        mail_sources=[SpaceDeleteSource(id=uuid4(), name="My label")],
        chunks=2,
        owned_spaces=4,
        state_digest="a" * 64,
    )
    draft = build_action_content(
        uuid4(),
        SPACE_DELETE_OPERATION,
        SpaceDeletePatch(space_delete=selected),
        {"space_delete": selected.public_scope()},
        {"space_delete": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    assert labels["application_space_delete_note"] and labels["application_field_space_delete"]
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>Literal</script>" not in html and "&lt;script&gt;Literal&lt;/script&gt;" in html
    assert "My folder" in html and "My label" in html
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Confirm this space")
    assert json.loads(prompt[1]["content"])["intent"] == {"space_id": str(identity)}
    assert "state_digest" not in str(prompt) and "owned_spaces" not in str(prompt)
