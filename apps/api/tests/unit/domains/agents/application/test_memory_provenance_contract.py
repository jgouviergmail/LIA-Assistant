"""Provenance distinguishes malformed selection from malformed stored response data."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from pydantic import ValidationError

from src.domains.agents.application.memory_provenance_schemas import MemoryProvenanceRequest
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.tools.application_memory_tools import get_lia_memory_provenance_tool
from src.domains.shared.schemas import ProvenanceResponse
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "values",
    [
        {"memory_id": "invalid"},
        {"memory_id": str(uuid4()), "actor_id": str(uuid4())},
        {"memory_id": str(uuid4()), "conversation_id": str(uuid4())},
        {"memory_id": str(uuid4()), "limit": 100},
        {"memory_id": str(uuid4()), "excerpt": "Injected signal"},
    ],
)
def test_provenance_scope_is_only_one_identity(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MemoryProvenanceRequest.model_validate(values)
    assert set(
        get_lia_memory_provenance_tool.tool_call_schema.model_json_schema()["properties"]
    ) == {"selection"}


async def test_corrupt_source_data_is_not_misreported_as_a_user_input_error() -> None:
    with pytest.raises(ValidationError) as invalid:
        ProvenanceResponse.model_validate({"references": [], "total": -1, "kept_at_most": 0})

    @asynccontextmanager
    async def session():
        yield MagicMock()

    owner = uuid4()
    # A real turn publishes its consultation register; once a registration has
    # gated this tool, a call without one schedules a real database write.
    with (
        installed_runtime_context(user_id=owner),
        treatment_collector(run_id="memory-provenance-tool"),
        patch("src.domains.agents.tools.application_memory_tools.get_db_context", session),
        patch(
            "src.domains.agents.tools.application_memory_tools.read_memory_provenance",
            AsyncMock(side_effect=invalid.value),
        ),
    ):
        output = await get_lia_memory_provenance_tool.coroutine(
            selection=MemoryProvenanceRequest(memory_id=uuid4()),
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert not output.success and output.error_code == "INVALID_RESPONSE_FORMAT"
