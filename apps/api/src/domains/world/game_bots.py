"""Bounded deterministic search; no model, randomness, network or process-local match state."""

from contextlib import suppress
from dataclasses import dataclass

from src.core.constants import WORLD_ARCADE_BOT_MAX_NODES
from src.domains.world.game_models import (
    FourInRowMove,
    FourInRowPosition,
    GameMove,
    GamePosition,
    OptionalGameMove,
    TicTacToeMove,
    TicTacToePosition,
)
from src.domains.world.game_rules import (
    FOUR_LINES,
    TIC_LINES,
    apply_game_move,
    legal_moves,
    reversi_cells,
)

INFINITY = 10**9
CORNERS = (0, 7, 56, 63)


@dataclass(frozen=True)
class BotChoice:
    """A legal computer move, or None on a finished board, with the search work it charged."""

    move: OptionalGameMove
    nodes: int


class _Exhausted(Exception):
    """Internal bounded-search exit; the caller retains a legal deterministic fallback."""


@dataclass
class _Budget:
    limit: int
    nodes: int = 0

    def charge(self) -> None:
        """Count a child before constructing/evaluating it, never after exceeding the cap."""
        if self.nodes >= self.limit:
            raise _Exhausted
        self.nodes += 1


def _order(move: GameMove) -> tuple[int, int]:
    """Prefer central alignment moves and stable Reversi corners, with fixed tie breaks."""
    if isinstance(move, TicTacToeMove):
        return (0 if move.cell == 4 else 1 if move.cell in (0, 2, 6, 8) else 2, move.cell)
    if isinstance(move, FourInRowMove):
        return abs(move.column - 3), move.column
    if move.cell is None:
        return 0, -1
    return (
        (
            0
            if move.cell in CORNERS
            else 1 if move.cell // 8 in (0, 7) or move.cell % 8 in (0, 7) else 2
        ),
        move.cell,
    )


def _line_score(position: GamePosition, lines: tuple[tuple[int, ...], ...]) -> int:
    """Value unblocked alignment windows from the current player's perspective."""
    weights = (0, 1, 8, 64, 1000)
    score = 0
    for line in lines:
        own = sum(position.board[cell] == position.turn for cell in line)
        other = sum(position.board[cell] == 3 - position.turn for cell in line)
        if own and not other:
            score += weights[own]
        elif other and not own:
            score -= weights[other]
    return score


def _evaluate(position: GamePosition) -> int:
    """Apply small authored positional heuristics without inventing a terminal winner."""
    if isinstance(position, TicTacToePosition):
        return _line_score(position, TIC_LINES)
    if isinstance(position, FourInRowPosition):
        return _line_score(position, FOUR_LINES)
    player, other = position.turn, 3 - position.turn
    discs = position.board.count(player) - position.board.count(other)
    corners = sum(
        1 if position.board[cell] == player else -1 if position.board[cell] == other else 0
        for cell in CORNERS
    )
    mobility = len(reversi_cells(position.board, player)) - len(
        reversi_cells(position.board, other)
    )
    return discs + 25 * corners + 3 * mobility


def _search(position: GamePosition, depth: int, alpha: int, beta: int, budget: _Budget) -> int:
    """Negamax with alpha/beta pruning and a shared hard counter for every expanded child."""
    if position.result != "playing":
        if position.result == "draw":
            return 0
        winner = 1 if position.result == "one" else 2
        return (10000 + depth) * (1 if winner == position.turn else -1)
    if depth == 0:
        return _evaluate(position)
    moves = legal_moves(position)
    if not moves:
        return 0
    best = -INFINITY
    for move in sorted(moves, key=_order):
        budget.charge()
        child = apply_game_move(position, move)
        score = -_search(child, depth - 1, -beta, -alpha, budget)
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def choose_computer_action(
    position: GamePosition, node_budget: int = WORLD_ARCADE_BOT_MAX_NODES
) -> BotChoice:
    """Return a legal choice and counted work; an exhausted search retains its best completed branch.

    Args:
        position: The board on the computer's turn.
        node_budget: Children the search may expand, at most the hard node bound;
            zero plays the ordered legal fallback without searching.

    Returns:
        The chosen move (None when the board has no legal move) and the nodes charged.

    Raises:
        ValueError: The budget is not an integer within the hard node bound.
    """
    if type(node_budget) is not int or not 0 <= node_budget <= WORLD_ARCADE_BOT_MAX_NODES:
        raise ValueError("bot_budget")
    moves = sorted(legal_moves(position), key=_order)
    if not moves:
        return BotChoice(None, 0)
    fallback = moves[0]
    if node_budget == 0:
        return BotChoice(fallback, 0)
    budget = _Budget(node_budget)
    best, best_score = fallback, -INFINITY
    depth = (
        9
        if isinstance(position, TicTacToePosition)
        else 4 if isinstance(position, FourInRowPosition) else 3
    )
    # Reaching the node bound ends the search; the best completed branch still stands.
    with suppress(_Exhausted):
        for move in moves:
            budget.charge()
            child = apply_game_move(position, move)
            score = -_search(child, depth - 1, -INFINITY, -best_score, budget)
            if score > best_score:
                best, best_score = move, score
    return BotChoice(best, budget.nodes)
