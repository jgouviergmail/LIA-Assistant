"""Corrupt but syntactically bounded game records must fail closed at the storage boundary."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.world.game_models import GameKind
from src.domains.world.game_rules import new_game
from src.domains.world.game_state import GameMember, GameTable
from src.domains.world.schemas import WorldState
from src.domains.world.store import WorldStore

pytestmark = pytest.mark.unit


def raw_table(kind: GameKind = "tic_tac_toe") -> dict:
    cabinet = "arcade-" + kind.replace("_", "-")
    table = GameTable(
        cabinet=cabinet,
        phase="waiting",
        position=new_game(kind),
        members=[
            GameMember(account=str(uuid4()), public_id=str(uuid4()), controller="control", number=1)
        ],
        created_at=100,
        expires_at=160,
        turn_until=220,
    )
    return WorldState(games={cabinet: table}).model_dump(mode="json")


@pytest.mark.parametrize(
    "corruption",
    [
        "false_draw",
        "wrong_turn",
        "contradictory_winners",
        "wrong_mode",
        "invented_winner",
        "missing_pause_budget",
        "map_binding",
    ],
)
def test_logical_game_corruption_cannot_enter_authoritative_state(corruption: str) -> None:
    raw = raw_table()
    table = raw["games"]["arcade-tic-tac-toe"]
    if corruption == "false_draw":
        table["position"]["result"] = "draw"
    elif corruption == "wrong_turn":
        table["position"]["board"][0] = 1
    elif corruption == "contradictory_winners":
        table["position"]["board"] = [1, 1, 1, 2, 2, 2, 0, 0, 0]
    elif corruption == "wrong_mode":
        table["phase"] = "playing_human"
    elif corruption == "invented_winner":
        table.update(phase="finished", reason="unavailable", winner=1, ended_at=101, expires_at=131)
    elif corruption == "missing_pause_budget":
        table["paused_at"] = 101
    else:
        raw["games"] = {"arcade-reversi": table}
    with pytest.raises(ValidationError):
        WorldStore.decode(json.dumps(raw))


def test_gravity_corruption_is_not_a_legal_board_despite_valid_counts_and_cells() -> None:
    raw = raw_table("four_in_row")
    position = raw["games"]["arcade-four-in-row"]["position"]
    position["board"][0], position["turn"] = 1, 2
    with pytest.raises(ValidationError):
        WorldStore.decode(json.dumps(raw))


@pytest.mark.parametrize("reason,winner", [("win", None), ("draw", 1)])
def test_terminal_reason_agrees_with_winner_and_actual_board(
    reason: str, winner: int | None
) -> None:
    raw = raw_table()
    table = raw["games"]["arcade-tic-tac-toe"]
    board = [1, 2, 1, 1, 2, 2, 2, 1, 1] if winner is None else [1, 1, 1, 2, 2, 0, 0, 0, 0]
    table.update(phase="finished", reason=reason, winner=winner, ended_at=101, expires_at=131)
    table["position"].update(board=board, turn=2, result="draw" if winner is None else "one")
    with pytest.raises(ValidationError):
        WorldStore.decode(json.dumps(raw))


@pytest.mark.parametrize(
    "corruption",
    [
        "mode",
        "duplicate_member",
        "wrong_rule",
        "foreign_rematch",
        "duplicate_rematch",
        "self_request",
        "deadline",
        "nonfresh_lobby",
        "computer_turn",
        "terminal_time",
        "active_result",
        "reversi_discs",
        "terminal_computer_roster",
    ],
)
def test_storage_boundary_refuses_corrupt_roster_lifecycle_and_rule_context(
    corruption: str,
) -> None:
    raw = raw_table("reversi" if corruption == "reversi_discs" else "tic_tac_toe")
    table = next(iter(raw["games"].values()))
    member = table["members"][0]
    if corruption == "mode":
        table.update(phase="playing_computer", computer=False)
    elif corruption == "duplicate_member":
        table.update(phase="playing_human", members=[member, {**member, "number": 2}])
    elif corruption == "wrong_rule":
        table["cabinet"] = "arcade-reversi"
    elif corruption == "foreign_rematch":
        table["rematch"] = [str(uuid4())]
    elif corruption == "duplicate_rematch":
        table["rematch"] = [member["account"]] * 2
    elif corruption == "self_request":
        table["pending"] = {key: member[key] for key in ("account", "public_id", "controller")}
        table["pending"]["expires_at"] = 120
    elif corruption == "deadline":
        table["expires_at"] = 99
    elif corruption == "nonfresh_lobby":
        table["position"].update(board=[1, 2, 0, 0, 0, 0, 0, 0, 0])
    elif corruption == "computer_turn":
        table.update(phase="playing_computer", computer=True)
        member["number"] = 2
    elif corruption == "terminal_time":
        table.update(phase="finished", reason="abandoned")
    elif corruption == "active_result":
        table["winner"] = 1
    elif corruption == "reversi_discs":
        table["position"]["board"] = [0] * 64
    else:
        table.update(
            phase="finished",
            computer=True,
            reason="abandoned",
            ended_at=101,
            members=[
                member,
                {**member, "account": str(uuid4()), "public_id": str(uuid4()), "number": 2},
            ],
        )
    with pytest.raises(ValidationError):
        WorldStore.decode(json.dumps(raw))
