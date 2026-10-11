"""Source file transfer has one closed input, private comparisons and literal consent in six languages."""

import json
from uuid import uuid4

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.document_archive_manifest import DOCUMENT_ARCHIVE_MANIFEST
from src.domains.agents.application.document_archive_schemas import (
    DocumentArchiveInput,
    DocumentArchivePatch,
)
from src.domains.agents.application.document_archive_spec import DOCUMENT_ARCHIVE_OPERATION
from src.domains.agents.application.document_download_manifest import DOCUMENT_DOWNLOAD_MANIFEST
from src.domains.agents.application.document_download_schemas import (
    DocumentDownloadInput,
    DocumentDownloadPatch,
)
from src.domains.agents.application.document_download_spec import DOCUMENT_DOWNLOAD_OPERATION
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.tools.application_space_tools import download_lia_knowledge_document_tool
from src.domains.rag_spaces.archive_schemas import ArchiveDocumentSnapshot, DocumentArchiveSnapshot
from src.domains.rag_spaces.download_schemas import DocumentDownloadSnapshot

pytestmark = pytest.mark.unit


def test_both_modes_publish_exact_ids_and_use_mandatory_original_browser_consent():
    assert (
        DOCUMENT_DOWNLOAD_MANIFEST.parameters[0].schema == DocumentDownloadInput.model_json_schema()
    )
    assert (
        DOCUMENT_DOWNLOAD_MANIFEST.mutation_policy == "draft"
        and not DOCUMENT_DOWNLOAD_MANIFEST.permissions.hitl_required
    )
    assert DOCUMENT_DOWNLOAD_OPERATION.interaction_kind == "device"
    schema = download_lia_knowledge_document_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"request"}
    assert set(schema["$defs"]["DocumentDownloadInput"]["properties"]) == {
        "space_id",
        "document_id",
    }


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
@pytest.mark.parametrize("archive", [False, True])
def test_preview_names_the_file_without_hashes_and_editor_exposes_only_ids(language, archive):
    selected = DocumentDownloadSnapshot(
        space_id=uuid4(),
        document_id=uuid4(),
        space_name="Personal space",
        original_filename="<script>Literal</script>.txt",
        content_type="text/plain",
        file_size_bytes=4,
        file_digest="a" * 64,
        source_digest="b" * 64,
    )
    if archive:
        snapshot = DocumentArchiveSnapshot(
            space_id=selected.space_id,
            space_name=selected.space_name,
            documents=(
                ArchiveDocumentSnapshot(
                    document_id=selected.document_id,
                    original_filename=selected.original_filename,
                    member_name="Literal.txt",
                    file_size_bytes=4,
                    present=True,
                    file_digest="a" * 64,
                    source_digest="b" * 64,
                ),
            ),
        )
        operation, intent = DOCUMENT_ARCHIVE_OPERATION, DocumentArchivePatch(
            archive_to_download=snapshot
        )
        before, after = {"archive_to_download": None}, {
            "archive_to_download": snapshot.public_scope()
        }
    else:
        operation, intent = DOCUMENT_DOWNLOAD_OPERATION, DocumentDownloadPatch(
            document_to_download=selected
        )
        before, after = {"document_to_download": None}, {
            "document_to_download": selected.public_scope()
        }
    draft = build_action_content(
        uuid4(),
        operation,
        intent,
        before,
        after,
    )
    labels = get_draft_preview_labels(language)
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>Literal</script>" not in html and "&lt;script&gt;Literal&lt;/script&gt;" in html
    assert "file_digest" not in html and "source_digest" not in html
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Download the same file")
    assert json.loads(prompt[1]["content"])["intent"] == {
        "space_id": str(selected.space_id),
        **(
            {"document_ids": [str(selected.document_id)]}
            if archive
            else {"document_id": str(selected.document_id)}
        ),
    }
    assert "file_digest" not in str(prompt) and "source_digest" not in str(prompt)


def test_archive_modes_use_the_source_batch_bound_and_closed_exact_id_selection():
    from pydantic import ValidationError

    from src.core.constants import RAG_SPACES_BULK_MAX
    from src.domains.agents.tools.application_space_tools import download_lia_knowledge_archive_tool

    assert (
        DOCUMENT_ARCHIVE_MANIFEST.parameters[0].schema == DocumentArchiveInput.model_json_schema()
    )
    assert DOCUMENT_ARCHIVE_OPERATION.interaction_kind == "device"
    schema = download_lia_knowledge_archive_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"request"}
    ids_schema = schema["$defs"]["DocumentArchiveInput"]["properties"]["document_ids"]
    assert ids_schema["maxItems"] == RAG_SPACES_BULK_MAX
    identifier = uuid4()
    assert DocumentArchiveInput(
        space_id=uuid4(), document_ids=[identifier, identifier]
    ).document_ids == (identifier,)
    for invalid in ([], [uuid4() for _ in range(RAG_SPACES_BULK_MAX + 1)]):
        with pytest.raises(ValidationError):
            DocumentArchiveInput(space_id=uuid4(), document_ids=invalid)
    with pytest.raises(ValidationError):
        DocumentArchiveInput.model_validate(
            {"space_id": uuid4(), "document_ids": [identifier], "user_id": uuid4()}
        )


def test_archive_snapshot_refuses_unbounded_public_names_instead_of_truncating_consent():
    from pydantic import ValidationError

    document = ArchiveDocumentSnapshot(
        document_id=uuid4(),
        original_filename="x" * 70_000,
        member_name="literal.txt",
        file_size_bytes=0,
        present=False,
        source_digest="a" * 64,
    )
    with pytest.raises(ValidationError):
        DocumentArchiveSnapshot(space_id=uuid4(), space_name="Personal", documents=(document,))
