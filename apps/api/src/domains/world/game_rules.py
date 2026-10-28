"""Deterministic legal rules, independent of networking, bots, billing and rendering."""

from src.domains.world.game_models import (
    FourInRowMove,
    FourInRowPosition,
    GameKind,
    GameMove,
    GamePosition,
    GameResult,
    ReversiMove,
    ReversiPosition,
    TicTacToeMove,
    TicTacToePosition,
)

DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))


class InvalidMove(ValueError):
    """A bounded syntactic move is not legal in this authoritative position."""


def winning_lines(width: int, height: int, length: int) -> tuple[tuple[int, ...], ...]:
    """Compile complete non-wrapping line windows once for the two alignment games.

    Args:
        width: Board columns.
        height: Board rows.
        length: Cells a winning line aligns.

    Returns:
        Every horizontal, vertical and diagonal window, as row-major cell indexes.
    """
    return tuple(
        tuple((y + step * dy) * width + x + step * dx for step in range(length))
        for y in range(height)
        for x in range(width)
        for dx, dy in ((1, 0), (0, 1), (1, 1), (-1, 1))
        if 0 <= x + (length - 1) * dx < width and y + (length - 1) * dy < height
    )


TIC_LINES = winning_lines(3, 3, 3)
FOUR_LINES = winning_lines(7, 6, 4)


def new_game(kind: GameKind) -> GamePosition:
    """Create one fresh initial position; member/color alternation belongs to the table."""
    if kind == "tic_tac_toe":
        return TicTacToePosition()
    if kind == "four_in_row":
        return FourInRowPosition()
    if kind == "reversi":
        board = [0] * 64
        board[27], board[28], board[35], board[36] = 2, 1, 1, 2
        return ReversiPosition(board=tuple(board))
    raise ValueError("unknown_game")


def alignment_result(board: tuple[int, ...], lines: tuple[tuple[int, ...], ...]) -> GameResult:
    """Derive a win/draw without row wrapping; contradictory winners fail closed.

    Args:
        board: Row-major cells; zero empty, one/two players.
        lines: The game's winning windows.

    Returns:
        ``one``, ``two``, ``draw`` on a full board, or ``playing``.

    Raises:
        InvalidMove: Both players hold a complete line.
    """
    winners = {
        board[line[0]]
        for line in lines
        if board[line[0]] and all(board[cell] == board[line[0]] for cell in line)
    }
    if len(winners) > 1:
        raise InvalidMove("game_inconsistent")
    if winners:
        return "one" if 1 in winners else "two"
    return "playing" if 0 in board else "draw"


def reversi_flips(board: tuple[int, ...], cell: int, player: int) -> tuple[int, ...]:
    """Return bracketed opponent discs in all eight bounded directions.

    Args:
        board: Row-major eight-by-eight discs.
        cell: Candidate destination.
        player: The color placing the disc.

    Returns:
        The opponent discs the placement would flip; empty when it captures none.
    """
    if board[cell] != 0:
        return ()
    origin_x, origin_y = cell % 8, cell // 8
    flips: list[int] = []
    for dx, dy in DIRECTIONS:
        x, y = origin_x + dx, origin_y + dy
        ray: list[int] = []
        while 0 <= x < 8 and 0 <= y < 8 and board[y * 8 + x] == 3 - player:
            ray.append(y * 8 + x)
            x, y = x + dx, y + dy
        if ray and 0 <= x < 8 and 0 <= y < 8 and board[y * 8 + x] == player:
            flips.extend(ray)
    return tuple(flips)


def reversi_cells(board: tuple[int, ...], player: int) -> tuple[int, ...]:
    """Enumerate capturing cells in a deterministic row-major order.

    Args:
        board: Row-major eight-by-eight discs.
        player: The color to move.

    Returns:
        Every empty cell where that color captures at least one disc.
    """
    return tuple(
        cell
        for cell, value in enumerate(board)
        if value == 0 and reversi_flips(board, cell, player)
    )


def reversi_result(board: tuple[int, ...]) -> GameResult:
    """Finish when neither color can capture, even if empty cells remain."""
    if 0 in board and (reversi_cells(board, 1) or reversi_cells(board, 2)):
        return "playing"
    one, two = board.count(1), board.count(2)
    return "draw" if one == two else "one" if one > two else "two"


def legal_moves(position: GamePosition) -> tuple[GameMove, ...]:
    """Enumerate legal moves, including the sole explicit forced-pass alternative."""
    if position.result != "playing":
        return ()
    if isinstance(position, TicTacToePosition):
        return (
            tuple(
                TicTacToeMove(cell=cell) for cell, value in enumerate(position.board) if value == 0
            )
            if alignment_result(position.board, TIC_LINES) == "playing"
            else ()
        )
    if isinstance(position, FourInRowPosition):
        return (
            tuple(
                FourInRowMove(column=column) for column in range(7) if position.board[column] == 0
            )
            if alignment_result(position.board, FOUR_LINES) == "playing"
            else ()
        )
    cells = reversi_cells(position.board, position.turn)
    if cells:
        return tuple(ReversiMove(cell=cell) for cell in cells)
    return (ReversiMove(cell=None),) if reversi_cells(position.board, 3 - position.turn) else ()


def apply_game_move(position: GamePosition, move: GameMove) -> GamePosition:
    """Return a new position; invalid moves and terminal states never mutate their input.

    Args:
        position: The authoritative board.
        move: A move of the same rule family.

    Returns:
        The board after the move, with its derived turn and result.

    Raises:
        InvalidMove: The board is finished, or the move is not legal on it.
    """
    if position.result != "playing":
        raise InvalidMove("game_finished")
    if isinstance(position, TicTacToePosition) and isinstance(move, TicTacToeMove):
        if position.board[move.cell] or alignment_result(position.board, TIC_LINES) != "playing":
            raise InvalidMove("illegal_cell")
        board = list(position.board)
        board[move.cell] = position.turn
        return TicTacToePosition(
            board=tuple(board),
            turn=3 - position.turn,
            result=alignment_result(tuple(board), TIC_LINES),
        )
    if isinstance(position, FourInRowPosition) and isinstance(move, FourInRowMove):
        return _drop(position, move)
    if isinstance(position, ReversiPosition) and isinstance(move, ReversiMove):
        return _capture(position, move)
    raise InvalidMove("wrong_game")


def _drop(position: FourInRowPosition, move: FourInRowMove) -> FourInRowPosition:
    """Place a disc at the lowest empty cell in a legal gravity column."""
    if alignment_result(position.board, FOUR_LINES) != "playing":
        raise InvalidMove("game_finished")
    cell = next(
        (
            row * 7 + move.column
            for row in range(5, -1, -1)
            if position.board[row * 7 + move.column] == 0
        ),
        None,
    )
    if cell is None:
        raise InvalidMove("full_column")
    board = list(position.board)
    board[cell] = position.turn
    return FourInRowPosition(
        board=tuple(board),
        turn=3 - position.turn,
        result=alignment_result(tuple(board), FOUR_LINES),
    )


def _capture(position: ReversiPosition, move: ReversiMove) -> ReversiPosition:
    """Apply every bracketed ray or a provably forced pass, then count terminal discs."""
    if move.cell is None:
        if reversi_cells(position.board, position.turn) or not reversi_cells(
            position.board, 3 - position.turn
        ):
            raise InvalidMove("illegal_pass")
        return ReversiPosition(board=position.board, turn=3 - position.turn)
    flips = reversi_flips(position.board, move.cell, position.turn)
    if not flips:
        raise InvalidMove("no_capture")
    board = list(position.board)
    for cell in (*flips, move.cell):
        board[cell] = position.turn
    result_board = tuple(board)
    return ReversiPosition(
        board=result_board, turn=3 - position.turn, result=reversi_result(result_board)
    )
