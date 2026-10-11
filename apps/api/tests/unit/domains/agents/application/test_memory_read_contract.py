"""Management selection is strictly bounded and accepts no actor or arbitrary query."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.application.memory_read_schemas import MemoryRead
from src.domains.agents.tools.application_memory_tools import get_lia_memories_tool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "selection",
    [
        {"limit": True},
        {"limit": "5"},
        {"limit": 0},
        {"limit": 51},
        {"category": "x' OR 1=1"},
        {"actor_id": str(uuid4())},
        {"memory_id": str(uuid4()), "category": "personal"},
        {"memory_id": str(uuid4()), "after_id": str(uuid4())},
    ],
)
def test_invalid_management_selection_fails_at_the_native_boundary(
    selection: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        MemoryRead.model_validate(selection)


def test_authenticated_runtime_is_not_an_argument_offered_to_the_model() -> None:
    assert "runtime" not in get_lia_memories_tool.tool_call_schema.model_fields
