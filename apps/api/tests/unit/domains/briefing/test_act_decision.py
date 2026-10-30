"""A dashboard act shared by several requests is filed through the once-only door."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.briefing.act_decision import file_briefing_act

pytestmark = pytest.mark.unit

RECORDER = "src.domains.agents.effects.decision_recorder"


@pytest.mark.parametrize(
    ("once", "door"), [(True, "record_decision_once"), (False, "record_decision")]
)
async def test_the_act_goes_through_its_door(once: bool, door: str) -> None:
    once_door, plain_door = AsyncMock(), AsyncMock()
    with (
        patch(f"{RECORDER}.record_decision_once", once_door),
        patch(f"{RECORDER}.record_decision", plain_door),
    ):
        await file_briefing_act(user_id=uuid4(), run_id="briefing_act_x", route="r", once=once)

    called = once_door if door == "record_decision_once" else plain_door
    other = plain_door if called is once_door else once_door
    called.assert_awaited_once()
    assert called.await_args is not None
    decision = called.await_args.args[0]
    assert (decision.run_id, decision.route) == ("briefing_act_x", "r")
    other.assert_not_awaited()


async def test_a_register_failure_never_breaks_the_dashboard() -> None:
    with patch(f"{RECORDER}.record_decision_once", AsyncMock(side_effect=RuntimeError("down"))):
        await file_briefing_act(user_id=uuid4(), run_id="briefing_act_x", route="r", once=True)
