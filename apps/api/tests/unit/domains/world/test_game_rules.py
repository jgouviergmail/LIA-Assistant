"""Game results are derived from immutable legal moves, independently of transport or rendering."""

import pytest
from pydantic import ValidationError

from src.domains.world.game_models import FourInRowMove, ReversiMove, TicTacToeMove
from src.domains.world.game_rules import InvalidMove, apply_game_move, legal_moves, new_game

pytestmark = pytest.mark.unit


def test_every_reachable_tic_tac_toe_position_is_finite_and_terminal_states_are_immutable() -> None:
    first = new_game("tic_tac_toe")
    pending, seen, terminal = [first], set(), 0
    while pending:
        position = pending.pop()
        key = (position.board, position.turn, position.result)
        if key in seen:
            continue
        seen.add(key)
        before = position.model_dump_json()
        moves = legal_moves(position)
        if position.result != "playing":
            terminal += 1
            assert moves == ()
            with pytest.raises(InvalidMove):
                apply_game_move(position, TicTacToeMove(cell=0))
        for move in moves:
            after = apply_game_move(position, move)
            assert after.board.count(0) == position.board.count(0) - 1
            assert after.turn == 3 - position.turn
            assert position.model_dump_json() == before
            pending.append(after)
    assert len(seen) == 5478 and terminal == 958


def test_tic_tac_toe_refuses_an_occupied_cell_wrong_game_and_post_terminal_move() -> None:
    position = apply_game_move(new_game("tic_tac_toe"), TicTacToeMove(cell=0))
    with pytest.raises(InvalidMove):
        apply_game_move(position, TicTacToeMove(cell=0))
    with pytest.raises(InvalidMove):
        apply_game_move(position, FourInRowMove(column=0))


@pytest.mark.parametrize("value", [True, False, -1, 9, 1.0, "1"])
def test_tic_tac_toe_coordinates_are_strict_and_bounded(value: object) -> None:
    with pytest.raises(ValidationError):
        TicTacToeMove.model_validate({"cell": value})


@pytest.mark.parametrize(
    "columns",
    [
        [0, 6, 1, 6, 2, 5, 3],
        [0, 1, 0, 1, 0, 1, 0],
        [0, 1, 1, 2, 4, 2, 2, 3, 4, 3, 5, 3, 3],
        [6, 5, 5, 4, 2, 4, 4, 3, 2, 3, 1, 3, 3],
    ],
)
def test_four_in_row_all_winning_directions(columns: list[int]) -> None:
    position = new_game("four_in_row")
    for column in columns:
        position = apply_game_move(position, FourInRowMove(column=column))
    assert position.result == "one" and legal_moves(position) == ()


def test_four_in_row_obeys_gravity_and_full_columns() -> None:
    position = new_game("four_in_row")
    for _ in range(6):
        position = apply_game_move(position, FourInRowMove(column=0))
    assert all(position.board[row * 7] != 0 for row in range(6))
    assert FourInRowMove(column=0) not in legal_moves(position)
    with pytest.raises(InvalidMove):
        apply_game_move(position, FourInRowMove(column=0))


def test_four_in_row_can_finish_a_full_legal_draw_without_an_invented_winner() -> None:
    position = new_game("four_in_row")
    columns = [
        6,
        6,
        6,
        6,
        6,
        5,
        5,
        5,
        5,
        5,
        5,
        4,
        4,
        4,
        4,
        4,
        4,
        6,
        3,
        3,
        3,
        3,
        3,
        3,
        2,
        2,
        2,
        2,
        2,
        1,
        1,
        1,
        1,
        1,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        2,
    ]
    for column in columns:
        position = apply_game_move(position, FourInRowMove(column=column))
    assert position.result == "draw" and position.board.count(0) == 0
    assert legal_moves(position) == ()


@pytest.mark.parametrize("value", [True, -1, 7, 1.0, "1"])
def test_four_in_row_columns_are_strict_and_bounded(value: object) -> None:
    with pytest.raises(ValidationError):
        FourInRowMove.model_validate({"column": value})


def test_reversi_opening_flips_and_cannot_pass_while_a_capture_exists() -> None:
    position = new_game("reversi")
    assert {move.cell for move in legal_moves(position) if isinstance(move, ReversiMove)} == {
        19,
        26,
        37,
        44,
    }
    with pytest.raises(InvalidMove):
        apply_game_move(position, ReversiMove(cell=None))
    with pytest.raises(InvalidMove):
        apply_game_move(position, ReversiMove(cell=27))
    after = apply_game_move(position, ReversiMove(cell=19))
    assert after.board.count(1) == 4 and after.board.count(2) == 1
    assert position.board.count(1) == position.board.count(2) == 2


def test_reversi_capture_requires_a_bracket_without_wrapping_at_board_edges() -> None:
    from src.domains.world.game_models import ReversiPosition

    board = [0] * 64
    board[7], board[8] = 2, 1
    position = ReversiPosition(board=tuple(board))
    assert ReversiMove(cell=6) not in legal_moves(position)
    with pytest.raises(InvalidMove):
        apply_game_move(position, ReversiMove(cell=6))


@pytest.mark.parametrize(
    "dx,dy", [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]
)
def test_reversi_captures_in_each_of_eight_directions(dx: int, dy: int) -> None:
    from src.domains.world.game_models import ReversiPosition

    board = [0] * 64
    board[(3 + dy) * 8 + 3 + dx] = 2
    board[(3 + 2 * dy) * 8 + 3 + 2 * dx] = 1
    after = apply_game_move(ReversiPosition(board=tuple(board)), ReversiMove(cell=27))
    assert after.board[(3 + dy) * 8 + 3 + dx] == 1


def test_reversi_forced_pass_then_double_no_move_finishes_with_exact_counts() -> None:
    from src.domains.world.game_models import ReversiPosition

    board = [1] * 64
    board[0], board[1], board[63] = 0, 2, 0
    position = ReversiPosition(board=tuple(board), turn=2)
    assert legal_moves(position) == (ReversiMove(cell=None),)
    after_pass = apply_game_move(position, ReversiMove(cell=None))
    assert after_pass.board == position.board and after_pass.turn == 1
    finished = apply_game_move(after_pass, ReversiMove(cell=0))
    assert finished.result == "one" and finished.board.count(1) == 63
    assert finished.board.count(0) == 1
    assert legal_moves(finished) == ()


def test_reversi_final_capture_can_draw_with_exact_disc_counts() -> None:
    from src.domains.world.game_models import ReversiPosition

    board = [2] * 64
    board[0] = 0
    for cell in range(2, 32):
        board[cell] = 1
    finished = apply_game_move(ReversiPosition(board=tuple(board)), ReversiMove(cell=0))
    assert finished.result == "draw"
    assert finished.board.count(1) == finished.board.count(2) == 32


def test_contradictory_or_already_winning_boards_never_accept_a_new_move() -> None:
    from src.domains.world.game_models import FourInRowPosition, TicTacToePosition

    contradictory = TicTacToePosition(board=(1, 1, 1, 2, 2, 2, 0, 0, 0))
    with pytest.raises(InvalidMove, match="game_inconsistent"):
        legal_moves(contradictory)
    board = (0,) * 35 + (1, 1, 1, 1, 0, 0, 0)
    finished = FourInRowPosition(board=board)
    assert legal_moves(finished) == ()
    with pytest.raises(InvalidMove, match="game_finished"):
        apply_game_move(finished, FourInRowMove(column=6))


@pytest.mark.parametrize(
    "patch",
    [
        {"board": [0] * 8},
        {"board": [True] + [0] * 8},
        {"board": [3] + [0] * 8},
        {"turn": True},
        {"account_id": "private"},
        {"result": "invented"},
    ],
)
def test_corrupt_or_private_position_fields_do_not_enter_the_rule_registry(
    patch: dict[str, object],
) -> None:
    import json

    from pydantic import TypeAdapter

    from src.domains.world.game_models import GamePosition

    with pytest.raises(ValidationError):
        TypeAdapter(GamePosition).validate_json(json.dumps({"game": "tic_tac_toe", **patch}))


@pytest.mark.parametrize("value", [True, -1, 64, 1.0, "1"])
def test_reversi_cells_are_strict_and_bounded(value: object) -> None:
    with pytest.raises(ValidationError):
        ReversiMove.model_validate({"cell": value})
