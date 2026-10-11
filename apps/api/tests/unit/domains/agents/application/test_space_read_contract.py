"""Both model modes see source-derived DTOs and the same strict finite query bounds."""

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.space_read_schemas import SPACE_READ_MAX_PAGE, SpaceUIQuery
from src.domains.agents.application.space_read_spec import (
    SPACE_UI_READ_MANIFEST,
    SPACE_UI_READ_OPERATION,
)
from src.domains.agents.tools.application_space_tools import get_lia_knowledge_spaces_tool
from src.domains.feature_switches.registry import PlatformCapability, disabled_tool_names
from src.domains.rag_spaces.document_catalogue import AttachableDocument
from src.domains.rag_spaces.schemas import (
    RAGDocumentResponse,
    RAGDriveSourceResponse,
    RAGMailSourceResponse,
    RAGSpaceResponse,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"section": "documents"},
        {"section": "system"},
        {"user_id": "forged"},
        {"limit": True},
        {"limit": "2"},
        {"limit": 0},
        {"limit": SPACE_READ_MAX_PAGE + 1},
        {"offset": -1},
        {"offset": 1.5},
        {"section": "spaces", "space_id": "00000000-0000-0000-0000-000000000001"},
        {"section": "attachable_documents", "space_id": "00000000-0000-0000-0000-000000000001"},
        {"section": "spaces", "q": "some name"},
        {"section": "attachable_documents", "q": "x" * 201},
    ],
)
def test_finite_space_query_rejects_ambiguous_or_coercible_values(payload):
    with pytest.raises(ValidationError):
        SpaceUIQuery.model_validate(payload)


def test_space_read_schema_and_authorities_are_bound_to_both_modes():
    spec = SPACE_UI_READ_OPERATION
    assert APPLICATION_OPERATIONS.get(spec.operation_id) is spec
    assert spec.tool_name in APPLICATION_TOOL_NAMES
    assert not spec.administrative and spec.required_capabilities == (
        PlatformCapability.RAG_SPACES,
    )
    assert (
        SPACE_UI_READ_MANIFEST.mutation_policy == "read"
        and not SPACE_UI_READ_MANIFEST.initiative_eligible
    )
    query = next(
        parameter for parameter in SPACE_UI_READ_MANIFEST.parameters if parameter.name == "query"
    )
    assert query.schema == SpaceUIQuery.model_json_schema()
    schema = get_lia_knowledge_spaces_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"query"}
    assert schema["$defs"]["SpaceUIQuery"]["properties"]["limit"]["maximum"] == SPACE_READ_MAX_PAGE
    assert spec.tool_name in disabled_tool_names({PlatformCapability.APPLICATION_TOOLS: False})


@pytest.mark.parametrize(
    "model,reviewed",
    [
        (
            AttachableDocument,
            {
                "id",
                "space_id",
                "space_name",
                "space_is_active",
                "original_filename",
                "content_type",
                "file_size",
                "created_at",
            },
        ),
        (
            RAGSpaceResponse,
            {
                "id",
                "name",
                "description",
                "is_active",
                "kind",
                "document_count",
                "total_size",
                "ready_document_count",
                "created_at",
                "updated_at",
            },
        ),
        (
            RAGDocumentResponse,
            {
                "id",
                "original_filename",
                "file_size",
                "content_type",
                "status",
                "error_message",
                "error_code",
                "chunk_count",
                "embedding_model",
                "embedding_tokens",
                "embedding_cost_eur",
                "source_type",
                "drive_file_id",
                "mail_thread_id",
                "created_at",
            },
        ),
        (
            RAGDriveSourceResponse,
            {
                "id",
                "folder_id",
                "folder_name",
                "sync_status",
                "last_sync_at",
                "file_count",
                "synced_file_count",
                "error_message",
                "created_at",
            },
        ),
        (
            RAGMailSourceResponse,
            {
                "id",
                "label_id",
                "label_name",
                "sync_status",
                "last_sync_at",
                "thread_count",
                "synced_thread_count",
                "error_message",
                "created_at",
            },
        ),
    ],
)
def test_source_ui_field_growth_requires_explicit_model_exposure_review(model, reviewed):
    # Reuse preserves source UI fields; a newly added secret/support field must
    # never silently acquire permission to enter model context.
    assert set(model.model_fields) == reviewed
