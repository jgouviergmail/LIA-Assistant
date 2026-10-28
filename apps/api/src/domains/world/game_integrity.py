"""Storage invariants verify derived rule results and complete table transitions before publication."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domains.world.game_models import FourInRowPosition, GamePosition, ReversiPosition
from src.domains.world.game_rules import (
    FOUR_LINES,
    TIC_LINES,
    alignment_result,
    new_game,
    reversi_result,
)

if TYPE_CHECKING:
    from src.domains.world.game_state import GameTable


def _alignment_integrity(position: GamePosition) -> None:
    """Check turn parity and terminal counts independently of the declared result field."""
    one, two = position.board.count(1), position.board.count(2)
    if one not in {two, two + 1} or position.turn != (1 if one == two else 2):
        raise ValueError("game_position_integrity")
    lines = FOUR_LINES if isinstance(position, FourInRowPosition) else TIC_LINES
    result = alignment_result(position.board, lines)
    if (
        result != position.result
        or (result == "one" and one != two + 1)
        or (result == "two" and one != two)
    ):
        raise ValueError("game_position_integrity")


def _gravity_integrity(position: FourInRowPosition) -> None:
    """A disc cannot float above an empty cell in the same authoritative column."""
    for column in range(7):
        empty = False
        for row in range(5, -1, -1):
            value = position.board[row * 7 + column]
            if value == 0:
                empty = True
            elif empty:
                raise ValueError("game_gravity_integrity")


def validate_position(position: GamePosition) -> None:
    """Refuse shape-valid but logically corrupt boards without inventing repairs or scores."""
    if isinstance(position, ReversiPosition):
        if 64 - position.board.count(0) < 4 or position.result != reversi_result(position.board):
            raise ValueError("game_position_integrity")
        return
    _alignment_integrity(position)
    if isinstance(position, FourInRowPosition):
        _gravity_integrity(position)


def _roster_integrity(table: GameTable) -> None:
    """Require phase-appropriate membership and requests that cannot impersonate a joined player."""
    expected = {"empty": 0, "waiting": 1, "playing_computer": 1, "playing_human": 2}.get(
        table.phase
    )
    if expected is not None and len(table.members) != expected:
        raise ValueError("game_roster_integrity")
    accounts = {member.account for member in table.members}
    if any(owner not in accounts for owner in table.rematch) or len(set(table.rematch)) != len(
        table.rematch
    ):
        raise ValueError("game_rematch_integrity")
    if table.pending is not None and (
        table.phase not in {"waiting", "playing_computer"} or table.pending.account in accounts
    ):
        raise ValueError("game_request_integrity")


def _mode_integrity(table: GameTable) -> None:
    """A computer never occupies a human account slot, including in terminal records."""
    if table.phase == "playing_computer" and not table.computer:
        raise ValueError("game_mode_integrity")
    if table.phase in {"waiting", "playing_human"} and table.computer:
        raise ValueError("game_mode_integrity")
    if table.computer and len(table.members) > 1:
        raise ValueError("game_mode_integrity")


def _result_integrity(table: GameTable) -> None:
    """No outage awards a win; active boards and completed results have one coherent meaning."""
    if table.phase == "finished":
        _terminal_integrity(table)
    elif table.phase != "empty":
        if (
            table.reason is not None
            or table.winner is not None
            or table.position.result != "playing"
        ):
            raise ValueError("game_result_integrity")


def _terminal_integrity(table: GameTable) -> None:
    """Terminal cause, declared winner and actual rule result must agree independently."""
    if table.ended_at is None or table.reason is None:
        raise ValueError("game_result_integrity")
    if table.reason in {"unavailable", "abandoned", "draw"} and table.winner is not None:
        raise ValueError("game_result_integrity")
    if table.reason == "win" and table.winner is None:
        raise ValueError("game_result_integrity")
    expected = {1: "one", 2: "two", None: "draw"}[table.winner]
    if table.reason in {"win", "draw"} and table.position.result != expected:
        raise ValueError("game_result_integrity")


def validate_game_table(table: GameTable) -> None:
    """Validate a complete serial record, never an in-progress in-memory transition."""
    validate_position(table.position)
    _roster_integrity(table)
    _mode_integrity(table)
    _result_integrity(table)
    if (table.paused_at is None) != (table.remaining_turn is None):
        raise ValueError("game_pause_integrity")
    if table.expires_at < table.created_at or table.turn_until < table.created_at:
        raise ValueError("game_deadline_integrity")
    if table.phase == "waiting" and table.position != new_game(table.position.game):
        raise ValueError("game_lobby_integrity")
    if table.phase == "playing_computer" and table.position.turn != table.members[0].number:
        raise ValueError("game_computer_turn_integrity")
