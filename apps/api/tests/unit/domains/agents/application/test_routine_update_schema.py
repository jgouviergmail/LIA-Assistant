"""Routine edits are strict deltas with one source-validated clock."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.routine_update_schemas import RoutineUpdateRequest

pytestmark = pytest.mark.unit


def test_native_update_preserves_an_explicit_false_approval_choice() -> None:
    request = RoutineUpdateRequest.model_validate(
        {
            "routine_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "changes": {"requires_approval": False},
        }
    )
    assert request.changes.requires_approval is False
    assert request.changes.model_fields_set == {"requires_approval"}


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"title": None},
        {"requires_approval": "false"},
        {"trigger_kind": None},
        {"execution_mode": None},
        {"owner_id": "foreign"},
    ],
)
def test_native_update_cannot_clear_required_configuration_or_inject_an_actor(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        RoutineUpdateRequest.model_validate(
            {"routine_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "changes": changes}
        )
