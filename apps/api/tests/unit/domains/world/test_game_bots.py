"""Computer choices are legal, reproducible and bounded by counted search work."""

from functools import lru_cache

import pytest

from src.domains.world.game_bots import choose_computer_action
from src.domains.world.game_models import FourInRowMove, GameKind, GamePosition, TicTacToeMove
from src.domains.world.game_rules import apply_game_move, legal_moves, new_game

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("kind", ["tic_tac_toe", "four_in_row", "reversi"])
@pytest.mark.parametrize("budget", [0, 1, 12, 6000])
def test_choices_are_legal_deterministic_and_within_the_explicit_node_budget(
    kind: GameKind, budget: int
) -> None:
    position = new_game(kind)
    result = choose_computer_action(position, node_budget=budget)
    assert result.move in legal_moves(position)
    assert 0 <= result.nodes <= budget
    assert choose_computer_action(position, node_budget=budget) == result


@pytest.mark.parametrize("cells,expected", [([0, 3, 1, 4], 2), ([0, 4, 1], 2)])
def test_tic_tac_toe_takes_a_win_and_blocks_an_immediate_loss(
    cells: list[int], expected: int
) -> None:
    position = new_game("tic_tac_toe")
    for cell in cells:
        position = apply_game_move(position, TicTacToeMove(cell=cell))
    assert choose_computer_action(position).move == TicTacToeMove(cell=expected)


@pytest.mark.parametrize("columns", [[0, 6, 1, 6, 2, 5], [0, 6, 1, 6, 2]])
def test_four_in_row_takes_a_win_or_blocks_a_loss(columns: list[int]) -> None:
    position = new_game("four_in_row")
    for column in columns:
        position = apply_game_move(position, FourInRowMove(column=column))
    assert choose_computer_action(position).move == FourInRowMove(column=3)


def test_tic_tac_toe_computer_cannot_lose_against_any_legal_human_continuation() -> None:
    @lru_cache(maxsize=6000)
    def explore(position: GamePosition, computer: int) -> None:
        if position.result != "playing":
            assert position.result in {"draw", "one" if computer == 1 else "two"}
            assert choose_computer_action(position).move is None
            return
        if position.turn == computer:
            move = choose_computer_action(position).move
            assert move is not None
            explore(apply_game_move(position, move), computer)
        else:
            for move in legal_moves(position):
                explore(apply_game_move(position, move), computer)

    explore(new_game("tic_tac_toe"), 1)
    explore(new_game("tic_tac_toe"), 2)


@pytest.mark.parametrize("budget", [True, -1, 6001, 1.0])
def test_invalid_budget_is_refused_instead_of_silently_becoming_unbounded(budget: object) -> None:
    with pytest.raises(ValueError, match="bot_budget"):
        choose_computer_action(new_game("tic_tac_toe"), node_budget=budget)


@pytest.mark.parametrize("kind", ["tic_tac_toe", "four_in_row", "reversi"])
def test_bounded_opponents_can_finish_each_game_without_a_loop_or_illegal_fallback(
    kind: GameKind,
) -> None:
    position = new_game(kind)
    for _ in range(128):
        if position.result != "playing":
            break
        move = choose_computer_action(position, node_budget=12).move
        assert move in legal_moves(position)
        assert move is not None
        position = apply_game_move(position, move)
    assert position.result != "playing"
    assert choose_computer_action(position).move is None
