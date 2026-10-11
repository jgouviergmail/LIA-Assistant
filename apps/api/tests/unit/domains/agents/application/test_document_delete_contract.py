"""Exact deletion consent excludes private witnesses in both tool modes and six locales."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.constants import RAG_SPACES_BULK_MAX
from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.document_delete_manifest import DOCUMENT_DELETE_MANIFEST
from src.domains.agents.application.document_delete_schemas import (
    DocumentDeleteFile,
    DocumentDeleteInput,
    DocumentDeletePatch,
    DocumentDeleteSelection,
)
from src.domains.agents.application.document_delete_spec import DOCUMENT_DELETE_OPERATION
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.space_delete_schemas import SpaceDeleteDocument
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.tools.application_space_tools import delete_lia_knowledge_documents_tool

pytestmark = pytest.mark.unit


def test_selected_deletion_is_closed_bounded_and_requires_native_confirmation():
    assert DOCUMENT_DELETE_MANIFEST.parameters[0].schema == DocumentDeleteInput.model_json_schema()
    assert DOCUMENT_DELETE_MANIFEST.mutation_policy == "draft"
    assert not DOCUMENT_DELETE_MANIFEST.permissions.hitl_required
    schema = delete_lia_knowledge_documents_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"request"}
    assert (
        schema["$defs"]["DocumentDeleteInput"]["properties"]["document_ids"]["maxItems"]
        == RAG_SPACES_BULK_MAX
    )
    identifier = uuid4()
    assert DocumentDeleteInput(
        space_id=uuid4(), document_ids=[identifier, identifier]
    ).document_ids == (identifier,)
    for ids in ([], [uuid4() for _ in range(RAG_SPACES_BULK_MAX + 1)]):
        with pytest.raises(ValidationError):
            DocumentDeleteInput(space_id=uuid4(), document_ids=ids)
    with pytest.raises(ValidationError):
        DocumentDeleteInput(space_id=uuid4(), document_ids=[identifier], user_id=uuid4())


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
@pytest.mark.parametrize("action", ["delete", "move"])
def test_selected_deletion_preview_and_editor_expose_only_the_exact_public_scope(language, action):
    identity, identifier = uuid4(), uuid4()
    selected = DocumentDeleteSelection(
        request=DocumentDeleteInput(space_id=identity, document_ids=[identifier]),
        space=SpaceUpdateTarget(
            id=identity, name="Personal corpus", description=None, is_active=True, kind=None
        ),
        items=(
            SpaceDeleteDocument(
                id=identifier,
                original_filename="<script>Literal</script>.txt",
                status="ready",
                source_type="upload",
                file_size=17,
            ),
        ),
        chunks=2,
        space_documents=3,
        state_digest="a" * 64,
        files=(
            DocumentDeleteFile(
                document_id=identifier, stored_filename="private-server-name", file_digest="b" * 64
            ),
        ),
    )
    operation, field, patch = (
        DOCUMENT_DELETE_OPERATION,
        "documents_to_delete",
        DocumentDeletePatch(documents_to_delete=selected),
    )
    if action == "move":
        from src.domains.agents.application.document_move_schemas import (
            DocumentMoveInput,
            DocumentMovePatch,
            DocumentMoveSelection,
        )
        from src.domains.agents.application.document_move_spec import DOCUMENT_MOVE_OPERATION

        target = uuid4()
        selected = DocumentMoveSelection(
            request=DocumentMoveInput(
                space_id=identity, document_ids=[identifier], target_space_id=target
            ),
            documents=selected,
            target=SpaceUpdateTarget(
                id=target, name="Target", description=None, is_active=False, kind=None
            ),
            target_documents=1,
            max_documents=5,
            source_digest="c" * 64,
            target_digest="d" * 64,
            result_digest="e" * 64,
        )
        operation, field, patch = (
            DOCUMENT_MOVE_OPERATION,
            "documents_to_move",
            DocumentMovePatch(documents_to_move=selected),
        )
    draft = build_action_content(
        uuid4(),
        operation,
        patch,
        {field: selected.public_scope()},
        {field: selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    assert labels[f"application_document_{action}_note"] and labels[f"application_field_{field}"]
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    assert "Literal" in str(rows) and "chunks" in str(rows) and "17" in str(rows)
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Refresh selection"))
    assert str(identifier) in prompt and str(identity) in prompt
    for private in (
        "state_digest",
        "space_documents",
        "stored_filename",
        "file_digest",
        "private-server-name",
        "a" * 64,
        "b" * 64,
    ):
        assert private not in prompt and private not in str(rows)
