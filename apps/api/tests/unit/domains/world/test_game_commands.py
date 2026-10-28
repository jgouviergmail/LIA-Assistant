"""Reject malformed commands at the socket boundary before policy, accounting or authority work."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.world.schemas import COMMAND_ADAPTER

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "patch",
    [
        {"version": True},
        {"version": 2.0},
        {"seq": False},
        {"board": [0] * 9},
        {"action_id": "11111111-1111-0111-1111-111111111111"},
        {"action": "move", "move": {"game": "tic_tac_toe", "cell": True}},
        {"move": {"game": "tic_tac_toe", "cell": 0}},
    ],
)
def test_malformed_game_commands_fail_closed_before_dispatch(patch: dict[str, object]) -> None:
    raw = {
        "version": 2,
        "type": "game",
        "epoch": str(uuid4()),
        "seq": 1,
        "cabinet": "arcade-tic-tac-toe",
        "action_id": str(uuid4()),
        "action": "wait",
        "expected_revision": 0,
        **patch,
    }
    with pytest.raises(ValidationError):
        COMMAND_ADAPTER.validate_python(raw)
