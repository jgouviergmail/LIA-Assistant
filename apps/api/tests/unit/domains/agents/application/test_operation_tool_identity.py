"""A native tool name cannot choose between conflicting operation authorities."""

from dataclasses import replace

import pytest
from pydantic import BaseModel

from src.domains.agents.application.operation_spec import (
    ApplicationOperationSpec,
    OperationKind,
    OperationRegistry,
)

pytestmark = pytest.mark.unit


def test_tool_identity_collision_cannot_replace_or_ambiguate_registered_authority():
    registry = OperationRegistry()
    original = ApplicationOperationSpec(
        operation_id="preferences.read",
        tool_name="get_lia_preferences_tool",
        sections=("theme",),
        input_model=BaseModel,
        output_model=BaseModel,
        kind=OperationKind.READ,
    )
    registry.register(original)
    with pytest.raises(ValueError):
        registry.register(replace(original, operation_id="admin.write", administrative=True))
    assert registry.all() == (original,)
    assert registry.get_by_tool_name(original.tool_name) is original
    assert registry.get_by_tool_name("unknown_tool") is None


def test_actual_operation_catalogue_has_one_authority_per_native_tool():
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS

    for operation in APPLICATION_OPERATIONS.all():
        assert APPLICATION_OPERATIONS.get_by_tool_name(operation.tool_name) is operation
