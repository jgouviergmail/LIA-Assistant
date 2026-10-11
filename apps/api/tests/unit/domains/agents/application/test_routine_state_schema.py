"""Desired routine-state commands cover source configuration and forbid extra fields."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.routine_schemas import RoutineStateRequest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("enabled", [True, False])
def test_routine_state_requires_an_explicit_desired_boolean(enabled: bool) -> None:
    request = RoutineStateRequest.model_validate(
        {"routine_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "enabled": enabled}
    )
    assert request.enabled is enabled


@pytest.mark.parametrize(
    "extra", [{"enabled": "false"}, {"enabled": True, "owner_id": "foreign"}, {"enabled": None}, {}]
)
def test_routine_state_cannot_inject_actor_or_ambiguous_state(extra: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RoutineStateRequest.model_validate(
            {"routine_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", **extra}
        )
