"""Pure serial cabinet authority: consent, exact operation deduplication and controller/round fences."""

from src.core.constants import WORLD_RECEIPT_RING_SIZE
from src.domains.world.emotes import record_receipt
from src.domains.world.game_commands import GameCommand, command_hash
from src.domains.world.game_context import GameLimits, GameScope
from src.domains.world.game_lifecycle import at_cabinet, finish_game, prune_games
from src.domains.world.game_membership import leave_table, rejoin_table, rematch_table
from src.domains.world.game_preparation import PreparedGame, prepared_position
from src.domains.world.game_rounds import (
    answer_request,
    apply_human_move,
    create_table,
    request_join,
)
from src.domains.world.game_state import GameOperationReceipt, GameTable
from src.domains.world.receipt_models import GameOutcome, GameOutcomeKind, GameReceipt
from src.domains.world.schemas import ActorState, WorldState


def _outcome(
    command: GameCommand, table: GameTable | None, result: GameOutcomeKind, scope: GameScope
) -> GameOutcome:
    """Build an explicit owner outcome without an account identifier or invented board result."""
    if table is not None and any(
        member.account not in scope.eligible or member.account in scope.blocked
        for member in table.members
    ):
        table = None
    return GameOutcome(
        action_id=command.action_id,
        result=result,
        round_id=table.round_id if table else None,
        revision=table.revision if table else 0,
    )


def _publish(actor: ActorState, command: GameCommand, outcome: GameOutcome) -> GameOutcome:
    """All fresh auxiliary commands clear the stale pose summary and acknowledge their own kind."""
    actor.seq = max(actor.seq, command.seq)
    actor.pose_result = None
    record_receipt(actor, GameReceipt(seq=command.seq, outcome=outcome))
    return outcome


def _cached(
    table: GameTable | None, scope: GameScope, command: GameCommand
) -> GameOperationReceipt | None:
    """Only the original account/controller generation can read its own exact operation receipt."""
    if table is None:
        return None
    return next(
        (
            receipt
            for receipt in table.receipts
            if receipt.account == scope.account
            and receipt.controller == scope.controller
            and receipt.outcome.action_id == command.action_id
        ),
        None,
    )


def _reserved_elsewhere(state: WorldState, scope: GameScope, command: GameCommand) -> bool:
    """Bound membership and pending requests to a single cabinet per account."""
    return any(
        cabinet != command.cabinet
        and (
            any(member.account == scope.account for member in table.members)
            or (table.pending is not None and table.pending.account == scope.account)
        )
        for cabinet, table in state.games.items()
    )


def _guard_table(table: GameTable | None, command: GameCommand) -> GameOutcomeKind | None:
    """Fence the exact observed match before any consent or move can take effect."""
    if table is None or table.phase == "empty":
        return None if command.round_id is None and command.expected_revision == 0 else "conflict"
    if table.round_id != command.round_id:
        return "conflict"
    if command.action != "leave" and table.revision != command.expected_revision:
        return "conflict"
    return None


def _dispatch(
    state: WorldState,
    scope: GameScope,
    command: GameCommand,
    now: float,
    limits: GameLimits,
    prepared: PreparedGame | None,
) -> GameOutcomeKind:
    """Dispatch bounded pure transitions, with no provider, CPU search or external effects."""
    table = state.games.get(command.cabinet)
    if command.action in {"wait", "start_computer"}:
        return _start_table(state, scope, command, now, limits)
    if table is None or table.phase == "empty":
        return "unavailable"
    if command.action == "request":
        if any(member.account == scope.account for member in table.members):
            return "occupied"
        return request_join(state, table, scope, now, limits)
    if command.action in {"accept", "decline"}:
        return answer_request(state, table, scope, command.action == "accept", now, limits)
    return _member_action(state, table, scope, command, now, limits, prepared)


def _start_table(
    state: WorldState, scope: GameScope, command: GameCommand, now: float, limits: GameLimits
) -> GameOutcomeKind:
    """Only the waiting host may switch an unclaimed lobby to a fresh solo round."""
    table = state.games.get(command.cabinet)
    own_wait = (
        table is not None
        and table.phase == "waiting"
        and table.pending is None
        and table.members[0].account == scope.account
        and command.action == "start_computer"
    )
    if table is not None and table.phase != "empty" and not own_wait:
        return "occupied"
    created = create_table(
        state, scope, command.cabinet, command.action == "start_computer", now, limits
    )
    if table is not None:
        created.receipts = table.receipts
    state.games[command.cabinet] = created
    return "accepted"


def _member_action(
    state: WorldState,
    table: GameTable,
    scope: GameScope,
    command: GameCommand,
    now: float,
    limits: GameLimits,
    prepared: PreparedGame | None,
) -> GameOutcomeKind:
    """Separate member lifecycle and turn actions from lobby admission."""
    if command.action == "leave":
        return leave_table(table, scope, now, limits)
    if command.action == "rejoin":
        return rejoin_table(state, table, scope, now, limits)
    member = next((member for member in table.members if member.account == scope.account), None)
    if member is None:
        return "not_participant"
    if member.controller != scope.controller:
        return "suspended"
    position = prepared_position(prepared, command, table)
    if command.action == "rematch":
        return rematch_table(table, scope, now, limits, position)
    if command.action == "move" and command.move is not None:
        return apply_human_move(table, scope, command.move, now, limits, position)
    return "unavailable"


def _policy_guard(
    table: GameTable | None, scope: GameScope, command: GameCommand, now: float, limits: GameLimits
) -> GameOutcomeKind | None:
    """Blocked/unavailable members end a round generically, without attributing who revoked contact."""
    if table is None:
        return None
    invalid = any(
        member.account not in scope.eligible or member.account in scope.blocked
        for member in table.members
    )
    if not invalid:
        return None
    if not any(member.account == scope.account for member in table.members):
        return "unavailable"
    if table.phase not in {"empty", "finished"}:
        finish_game(table, "unavailable", now, limits)
        table.revision += 1
    if any(member.account in scope.blocked for member in table.members):
        # Both projections are withdrawn on a block. Neither owner can see a
        # round to leave, so neither may retain its hidden reservation.
        table.members = []
        table.rematch = []
    return None if command.action == "leave" else "unavailable"


def _requires_rejoin(table: GameTable | None, scope: GameScope, command: GameCommand) -> bool:
    """Taking over World transport is not consent to inherit an active game interaction."""
    if table is None or command.action in {"leave", "rejoin"}:
        return False
    return any(
        member.account == scope.account and member.controller != scope.controller
        for member in table.members
    )


def _current_actor(
    state: WorldState, scope: GameScope, command: GameCommand, now: float
) -> ActorState | None:
    """A stale controller or scene cannot append receipts or alter a successor's membership."""
    actor = state.actors.get(scope.account)
    if (
        actor is None
        or actor.controller != scope.controller
        or actor.expires_at <= now
        or command.epoch != state.epoch
        or scope.account not in scope.eligible
    ):
        return None
    return actor


def _new_command_result(
    state: WorldState,
    scope: GameScope,
    command: GameCommand,
    actor: ActorState,
    now: float,
    limits: GameLimits,
    prepared: PreparedGame | None,
    forced: GameOutcomeKind | None,
) -> GameOutcomeKind:
    """Apply ordered authority guards before any new operation changes table state."""
    if forced is not None:
        return forced
    if command.action != "leave" and (not actor.visible or not at_cabinet(actor, command.cabinet)):
        return "out_of_reach"
    table = state.games.get(command.cabinet)
    refusal = _guard_table(table, command)
    if refusal is None:
        refusal = _policy_guard(table, scope, command, now, limits)
    if refusal is not None:
        return refusal
    if _requires_rejoin(table, scope, command):
        return "suspended"
    if command.action in {"wait", "start_computer", "request"} and _reserved_elsewhere(
        state, scope, command
    ):
        return "occupied"
    return _dispatch(state, scope, command, now, limits, prepared)


def apply_game_transition(
    state: WorldState,
    scope: GameScope,
    command: GameCommand,
    now: float,
    limits: GameLimits,
    prepared: PreparedGame | None = None,
    forced_result: GameOutcomeKind | None = None,
) -> GameOutcome:
    """Apply one pure CAS-ready intent; duplicate delivery never repeats a move or paid/external work.

    Args:
        state: Watched authority snapshot, mutated in place.
        scope: The commanding account and controller, with the fresh eligibility
            and block policy the command is judged under.
        command: The validated game command.
        now: Redis Unix time of the commit.
        limits: Effective lobby, request, reconnect, turn, round and result deadlines.
        prepared: The sealed computer answer computed before the commit, if any.
        forced_result: A refusal decided before the commit (input cap, disabled
            arcade): it consumes the sequence and changes no table.

    Returns:
        The outcome recorded under the command's sequence; an exact duplicate
        receives its original outcome, a stale or replaced controller an
        unrecorded ``unavailable``.
    """
    prune_games(state, now, limits)
    table, actor = state.games.get(command.cabinet), _current_actor(state, scope, command, now)
    if actor is None:
        return _outcome(command, table, "unavailable", scope)
    cached = _cached(table, scope, command)
    if cached is not None:
        outcome = (
            cached.outcome
            if cached.payload_hash == command_hash(command)
            else _outcome(command, table, "action_reused", scope)
        )
        return _publish(actor, command, outcome)
    if command.seq <= actor.seq:
        return _publish(actor, command, _outcome(command, table, "conflict", scope))
    result = _new_command_result(state, scope, command, actor, now, limits, prepared, forced_result)
    table = state.games.get(command.cabinet)
    outcome = _outcome(command, table, result, scope)
    if table is not None:
        table.receipts = [
            *table.receipts[-(WORLD_RECEIPT_RING_SIZE - 1) :],
            GameOperationReceipt(
                account=scope.account,
                controller=scope.controller,
                payload_hash=command_hash(command),
                outcome=outcome,
            ),
        ]
    if result == "accepted":
        actor.activity_at = now
    return _publish(actor, command, outcome)
