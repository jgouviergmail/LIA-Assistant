"""Immutable, revision-fenced human/computer preparation; invoked before any watched commit."""

from dataclasses import dataclass

from src.core.constants import WORLD_ARCADE_BOT_MAX_NODES
from src.domains.world.game_bots import choose_computer_action
from src.domains.world.game_commands import GameCommand, command_hash
from src.domains.world.game_context import GameScope
from src.domains.world.game_lifecycle import at_cabinet
from src.domains.world.game_models import GamePosition, OptionalGamePosition
from src.domains.world.game_rules import InvalidMove, apply_game_move, new_game
from src.domains.world.game_state import GameTable
from src.domains.world.schemas import WorldState


@dataclass(frozen=True)
class PreparedGame:
    """One complete human-plus-computer position, sealed to the exact command and round it answers."""

    round_id: str
    revision: int
    source: GamePosition
    action_id: str
    payload_hash: str
    position: GamePosition
    nodes: int

    def matches(
        self, command: GameCommand, position: GamePosition, round_id: str, revision: int
    ) -> bool:
        """An unrelated scene revision does not matter; round, operation and source board all do.

        Args:
            command: The command now being committed.
            position: The table's current board.
            round_id: The table's current round lifetime.
            revision: The table's current match revision.

        Returns:
            Whether this preparation answers exactly that command on that board.
        """
        return (
            self.round_id == round_id
            and self.revision == revision
            and self.action_id == command.action_id
            and self.payload_hash == command_hash(command)
            and self.source == position
            and self.position.game == position.game
        )


def prepared_position(
    prepared: PreparedGame | None, command: GameCommand, table: GameTable
) -> OptionalGamePosition:
    """Only exact source/command/round work may enter a later bounded authority commit.

    Args:
        prepared: The preparation computed before the commit, if any.
        command: The command now being committed.
        table: The table as the commit sees it.

    Returns:
        The prepared position, or None when it answers another command, board,
        round or revision.
    """
    return (
        prepared.position
        if prepared is not None
        and prepared.matches(command, table.position, table.round_id, table.revision)
        else None
    )


def _human_position(
    table: GameTable, scope: GameScope, command: GameCommand
) -> tuple[GamePosition, int] | None:
    """Determine a legal move or fresh alternate-color rematch without changing live state."""
    member = next((member for member in table.members if member.account == scope.account), None)
    if member is None or member.controller != scope.controller:
        return None
    if command.action == "rematch" and table.phase == "finished" and member.number == 1:
        return new_game(table.position.game), 2
    if command.action != "move" or command.move is None or table.position.turn != member.number:
        return None
    try:
        return apply_game_move(table.position, command.move), member.number
    except InvalidMove:
        return None


def can_prepare(state: WorldState, scope: GameScope, command: GameCommand) -> bool:
    """Reject obsolete, hidden, remote or suspended intents before acquiring a CPU slot.

    Args:
        state: Observed authority.
        scope: The commanding account and controller generation.
        command: The command a computer answer would serve.

    Returns:
        Whether the command is a current, reachable solo move or solo rematch.
    """
    actor, table = state.actors.get(scope.account), state.games.get(command.cabinet)
    if actor is None or table is None:
        return False
    member = next((member for member in table.members if member.account == scope.account), None)
    if member is None or member.controller != scope.controller:
        return False
    actor_valid = (
        actor.controller == scope.controller
        and actor.visible
        and command.seq > actor.seq
        and command.epoch == state.epoch
        and at_cabinet(actor, command.cabinet)
    )
    return actor_valid and _table_preparable(table, command)


def _table_preparable(table: GameTable, command: GameCommand) -> bool:
    """Only a matching solo move or explicit solo rematch can need a computer response."""
    return (
        table.computer
        and table.round_id == command.round_id
        and table.revision == command.expected_revision
        and table.paused_at is None
        and (
            (command.action == "move" and table.phase == "playing_computer")
            or (command.action == "rematch" and table.phase == "finished")
        )
    )


def prepare_game(
    state: WorldState,
    scope: GameScope,
    command: GameCommand,
    node_budget: int = WORLD_ARCADE_BOT_MAX_NODES,
) -> PreparedGame | None:
    """Compute at most one complete human-plus-computer position before CAS and SQL locks.

    Args:
        state: Observed authority, read before the commit.
        scope: The commanding account and controller generation.
        command: The solo move or solo rematch to answer.
        node_budget: Search children the computer may expand; zero plays the
            ordered legal fallback.

    Returns:
        The sealed preparation, or None when the command needs no computer answer
        or could not be committed anyway.
    """
    table = state.games.get(command.cabinet)
    if table is None or not can_prepare(state, scope, command):
        return None
    pending = _human_position(table, scope, command)
    if pending is None:
        return None
    position, human_number = pending
    nodes = 0
    if position.result == "playing" and position.turn != human_number:
        choice = choose_computer_action(position, node_budget)
        if choice.move is None:
            return None
        position, nodes = apply_game_move(position, choice.move), choice.nodes
    return PreparedGame(
        table.round_id,
        table.revision,
        table.position,
        command.action_id,
        command_hash(command),
        position,
        nodes,
    )
