"""Picker sections cannot widen provider queries or turn reads into indexing."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.application.source_options_schemas import SourceOptionsQuery

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "values",
    [
        {"section": "unknown"},
        {"section": "drive_contents", "folder_id": "x' or 'any' in parents"},
        {"section": "drive_contents", "offset": 1},
        {"section": "mail_labels", "folder_id": "root"},
        {"section": "mail_labels", "page_token": "a-provider-token"},
        {"section": "mail_labels", "limit": True},
        {"section": "mail_labels", "limit": 51},
        {"section": "mail_labels", "user_id": str(uuid4())},
        {"section": "drive_preflight"},
        {"section": "drive_preflight", "source_id": str(uuid4()), "folder_id": "root"},
        {"section": "drive_preflight", "source_id": str(uuid4()), "page_token": "token"},
        {"section": "drive_preflight", "source_id": str(uuid4()), "offset": 1},
        {"section": "drive_contents", "source_id": str(uuid4())},
    ],
)
def test_picker_query_is_section_specific_and_actor_is_injected(values):
    with pytest.raises(ValidationError):
        SourceOptionsQuery.model_validate({"space_id": uuid4(), **values})


def test_picker_manifest_and_actual_tool_publish_one_read_contract():
    from src.domains.agents.application.operation_spec import OperationKind
    from src.domains.agents.application.source_options_spec import (
        SOURCE_OPTIONS_MANIFEST,
        SOURCE_OPTIONS_OPERATION,
    )
    from src.domains.agents.tools.application_source_options_tools import (
        get_lia_knowledge_source_options_tool,
    )

    actual = get_lia_knowledge_source_options_tool.tool_call_schema.model_json_schema()
    assert set(actual["properties"]) == {"query"}
    assert SOURCE_OPTIONS_OPERATION.kind == OperationKind.READ
    assert SOURCE_OPTIONS_MANIFEST.mutation_policy == "read"
    assert not SOURCE_OPTIONS_MANIFEST.initiative_eligible
    assert SOURCE_OPTIONS_MANIFEST.parameters[0].schema == SourceOptionsQuery.model_json_schema()


def test_preflight_reads_an_existing_source_without_an_import_intent():
    source = uuid4()
    query = SourceOptionsQuery(section="drive_preflight", space_id=uuid4(), source_id=source)
    assert query.source_id == source
