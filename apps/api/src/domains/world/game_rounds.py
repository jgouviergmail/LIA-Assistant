"""Pure round transitions, with explicit consent and no search inside an authority commit."""

from uuid import uuid4

from src.domains.world.game_catalogue import CABINETS
from src.domains.world.game_context import GameLimits, GameScope
from src.domains.world.game_lifecycle import finish_game
from src.domains.world.game_models import CabinetId, GameMove, OptionalGamePosition
from src.domains.world.game_rules import InvalidMove, apply_game_move, new_game
from src.domains.world.game_state import GameJoinRequest, GameMember, GameTable
from src.domains.world.receipt_models import GameOutcomeKind
from src.domains.world.schemas import WorldState


def make_member(state: WorldState, scope: GameScope, number: int) -> GameMember:
    """Copy only opaque authority fences; public aliases remain owned by the live actor projection.

    Args:
        state: Authority whose live actor supplies the public identity.
        scope: Account and controller generation joining the table.
        number: Rule color the member holds in the current round.

    Returns:
        The member record, without a copied alias or profile.
    """
    actor = state.actors[scope.account]
    return GameMember(
        account=scope.account, public_id=actor.public_id, controller=scope.controller, number=number
    )


def create_table(
    state: WorldState,
    scope: GameScope,
    cabinet: CabinetId,
    computer: bool,
    now: float,
    limits: GameLimits,
) -> GameTable:
    """Create a fresh lobby or solo round at the cabinet's own rule family.

    Args:
        state: Authority whose live actor becomes the host.
        scope: Host account and controller generation.
        cabinet: Authored cabinet whose rule family the board follows.
        computer: Start a solo round against the computer instead of a lobby.
        now: Redis Unix time of the commit.
        limits: Effective lobby, round and turn deadlines.

    Returns:
        The new table; the host always holds the first color.
    """
    definition = CABINETS[cabinet]
    return GameTable(
        cabinet=definition.id,
        computer=computer,
        phase="playing_computer" if computer else "waiting",
        position=new_game(definition.game),
        members=[make_member(state, scope, 1)],
        created_at=now,
        expires_at=now + (limits.round_seconds if computer else limits.wait_seconds),
        turn_until=now + limits.turn_seconds,
    )


def fresh_round(
    table: GameTable, now: float, limits: GameLimits, *, computer: bool, alternate: bool = False
) -> None:
    """Replace a board and round identity, retaining only bounded operation deduplication.

    Args:
        table: Table whose round is replaced in place.
        now: Redis Unix time of the commit.
        limits: Effective round and turn deadlines.
        computer: Whether the fresh round is played against the computer.
        alternate: Swap every member's color — a rematch's alternation only.
    """
    table.round_id, table.revision = str(uuid4()), 0
    table.phase = "playing_computer" if computer else "playing_human"
    table.computer = computer
    table.position = new_game(table.position.game)
    table.created_at, table.expires_at, table.turn_until = (
        now,
        now + limits.round_seconds,
        now + limits.turn_seconds,
    )
    table.pending, table.paused_at, table.remaining_turn = None, None, None
    table.ended_at, table.reason, table.winner = None, None, None
    table.rematch = []
    for member in table.members:
        member.number = 3 - member.number if alternate else member.number
        member.offline_until = None


def request_join(
    state: WorldState, table: GameTable, scope: GameScope, now: float, limits: GameLimits
) -> GameOutcomeKind:
    """Reserve only one requesting account, without publishing a board or assigning a human slot.

    Args:
        state: Authority whose live actor supplies the requester's public identity.
        table: Lobby or solo round the request addresses.
        scope: Requesting account and controller generation.
        now: Redis Unix time of the commit.
        limits: Effective request deadline.

    Returns:
        ``accepted`` once reserved, ``full`` when the table cannot take a request.
    """
    if (
        table.phase not in {"waiting", "playing_computer"}
        or len(table.members) != 1
        or table.pending is not None
    ):
        return "full"
    actor = state.actors[scope.account]
    table.pending = GameJoinRequest(
        account=scope.account,
        public_id=actor.public_id,
        controller=scope.controller,
        expires_at=min(now + limits.request_seconds, table.expires_at),
    )
    table.revision += 1
    return "accepted"


def answer_request(
    state: WorldState,
    table: GameTable,
    scope: GameScope,
    accept: bool,
    now: float,
    limits: GameLimits,
) -> GameOutcomeKind:
    """Only the host may explicitly accept the currently fenced request into a fresh board.

    An accepted request starts a new pairing, not a rematch: the board is the
    canonical fresh one, the host on the first color and the joiner on the second,
    whatever color an earlier solo rematch had alternated the host to.

    Args:
        state: Authority whose live actor supplies the joiner's public identity.
        table: Table holding the pending request.
        scope: The host's account, controller and fresh native policy.
        accept: Admit the requester, or decline the request.
        now: Redis Unix time of the commit.
        limits: Effective round and turn deadlines.

    Returns:
        ``accepted``, ``not_participant`` for anyone but the host, ``conflict``
        without a pending request, or ``unavailable`` for an ineligible or
        blocked requester.
    """
    if not table.members or table.members[0].account != scope.account:
        return "not_participant"
    request = table.pending
    if request is None:
        return "conflict"
    if not accept:
        table.pending = None
        table.revision += 1
        return "accepted"
    if request.account not in scope.eligible or request.account in scope.blocked:
        return "unavailable"
    table.members[0].number = 1
    table.members.append(
        make_member(state, GameScope(request.account, request.controller, scope.eligible), 2)
    )
    fresh_round(table, now, limits, computer=False)
    return "accepted"


def _move_guard(table: GameTable, scope: GameScope) -> GameOutcomeKind | None:
    """Refuse nonmembers, inactive/suspended rounds and out-of-turn play before board work."""
    member = next((member for member in table.members if member.account == scope.account), None)
    if member is None:
        return "not_participant"
    if table.phase not in {"playing_computer", "playing_human"}:
        return "unavailable"
    if table.paused_at is not None:
        return "suspended"
    if table.position.turn != member.number:
        return "wrong_turn"
    return None


def apply_human_move(
    table: GameTable,
    scope: GameScope,
    move: GameMove,
    now: float,
    limits: GameLimits,
    prepared: OptionalGamePosition = None,
) -> GameOutcomeKind:
    """Apply a legal human turn; a solo response must have been prepared outside this transition.

    Args:
        table: Active round receiving the move.
        scope: Moving account and controller generation.
        move: Closed game-specific coordinate.
        now: Redis Unix time of the commit.
        limits: Effective turn and result deadlines.
        prepared: The exact human-plus-computer position computed before the commit,
            required for a solo round that continues.

    Returns:
        ``accepted``, or the refusal (``not_participant``, ``unavailable``,
        ``suspended``, ``wrong_turn``, ``illegal_move``).
    """
    refusal = _move_guard(table, scope)
    if refusal is not None:
        return refusal
    try:
        position = apply_game_move(table.position, move)
    except InvalidMove:
        return "illegal_move"
    if table.phase == "playing_computer" and position.result == "playing":
        if prepared is None or (
            prepared.result == "playing" and prepared.turn != table.position.turn
        ):
            return "unavailable"
        position = prepared
    table.position, table.turn_until = position, now + limits.turn_seconds
    table.revision += 1
    if position.result != "playing":
        winner = 1 if position.result == "one" else 2 if position.result == "two" else None
        finish_game(table, "draw" if winner is None else "win", now, limits, winner)
    return "accepted"
