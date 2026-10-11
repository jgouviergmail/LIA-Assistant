"""Public source fields grow together and mutable/native authority never enters read inputs."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.agents.application.habit_detail_schemas import (
    HabitDetailProjection,
    HabitDetailRead,
)
from src.domains.agents.application.habit_read_schemas import (
    HabitProjection,
    HabitRead,
    HabitsProjection,
)
from src.domains.habits.models import HabitKind
from src.domains.habits.schemas import (
    HabitExplanationResponse,
    HabitResponse,
    HabitsOverviewResponse,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": True},
        {"limit": 0},
        {"limit": 51},
        {"user_id": str(uuid4())},
        {"recompute": True},
        {"presence": True},
    ],
)
def test_habit_reads_refuse_excessive_pages_effects_and_selected_accounts(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        HabitRead.model_validate(payload)


def test_habit_reader_keeps_the_complete_public_source_projection() -> None:
    assert set(HabitProjection.model_fields) == set(HabitResponse.model_fields)
    assert set(HabitsOverviewResponse.model_fields) <= set(HabitsProjection.model_fields)
    assert (
        "user_id" not in HabitProjection.model_fields
        and "muted_until_reproof" not in HabitProjection.model_fields
    )
    assert set(HabitExplanationResponse.model_fields) <= set(HabitDetailProjection.model_fields)
    assert set(HabitKind) == {
        HabitKind.ACTIVE_WINDOW,
        HabitKind.RECURRING_REQUEST,
    }, "A new habit kind requires reviewing its actual explanation detector"


@pytest.mark.parametrize("extra", ["user_id", "payload", "thresholds", "observed_days"])
def test_explanation_input_never_accepts_invented_evidence_or_authority(extra: str) -> None:
    with pytest.raises(ValidationError):
        HabitDetailRead.model_validate({"habit_id": str(uuid4()), extra: "invented"})
