"""Exact public browser handoff survives both modes, six locales and safe draft amendment."""

from uuid import uuid4

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.document_upload_manifest import DOCUMENT_UPLOAD_MANIFEST
from src.domains.agents.application.document_upload_schemas import (
    DocumentUploadInput,
    DocumentUploadPatch,
    DocumentUploadSelection,
)
from src.domains.agents.application.document_upload_spec import DOCUMENT_UPLOAD_OPERATION
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.secure_handoff import secure_handoff_outcome
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.tools.application_space_tools import upload_lia_knowledge_document_tool

pytestmark = pytest.mark.unit


def test_upload_schema_binds_only_a_destination_and_never_initiates_file_material():
    schema = upload_lia_knowledge_document_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"request"}
    assert set(schema["$defs"]["DocumentUploadInput"]["properties"]) == {"space_id"}
    assert DOCUMENT_UPLOAD_MANIFEST.parameters[0].schema == DocumentUploadInput.model_json_schema()
    assert DOCUMENT_UPLOAD_MANIFEST.mutation_policy == "draft"
    assert not DOCUMENT_UPLOAD_MANIFEST.initiative_eligible
    assert not DOCUMENT_UPLOAD_MANIFEST.permissions.hitl_required


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_upload_preview_and_amendment_never_reveal_private_proof(language):
    identity = uuid4()
    selected = DocumentUploadSelection.model_validate(
        {
            "space": {
                "id": identity,
                "name": "<script>Literal space</script>",
                "description": None,
                "is_active": False,
                "kind": None,
            },
            "document_count": 1,
            "max_documents": 200,
            "max_file_size_bytes": 20 * 1024 * 1024,
            "allowed_content_types": ["text/plain"],
            "state_digest": "f" * 64,
        }
    )
    draft = build_action_content(
        uuid4(),
        DOCUMENT_UPLOAD_OPERATION,
        DocumentUploadPatch(document_to_upload=selected),
        {"document_to_upload": None},
        {"document_to_upload": selected.public_scope()},
    )
    labels = get_draft_preview_labels(language)
    assert labels["application_document_upload_note"]
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Change destination"))
    assert str(identity) in prompt
    handoff = secure_handoff_outcome(draft)
    assert handoff is not None and handoff.values == draft.after and not handoff.committed
    assert handoff.interaction.kind == "device"
    for private in ("state_digest", "f" * 64):
        assert private not in prompt and private not in html and private not in str(handoff.values)
