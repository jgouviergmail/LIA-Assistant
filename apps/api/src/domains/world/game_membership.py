"""Explicit resignation, rejoin and rematch; no implicit controller transfer or CPU search."""

from src.domains.world.game_context import GameLimits, GameScope
from src.domains.world.game_lifecycle import finish_game, prune_games
from src.domains.world.game_models import OptionalGamePosition
from src.domains.world.game_rounds import fresh_round
from src.domains.world.game_state import GameMember, GameTable
from src.domains.world.receipt_models import GameOutcomeKind
from src.domains.world.schemas import WorldState


def leave_table(
    table: GameTable, scope: GameScope, now: float, limits: GameLimits
) -> GameOutcomeKind:
    """Withdraw an own request or resign an own membership, retaining a bounded delivery tombstone.

    Args:
        table: Table the account requested or belongs to.
        scope: Departing account and controller generation.
        now: Redis Unix time of the commit.
        limits: Effective result deadline of the tombstone.

    Returns:
        ``accepted``, or ``not_participant`` for an account with no request or seat.
    """
    if table.pending is not None and table.pending.account == scope.account:
        table.pending = None
        table.revision += 1
        return "accepted"
    member = next((member for member in table.members if member.account == scope.account), None)
    if member is None:
        return "not_participant"
    table.members = [other for other in table.members if other is not member]
    table.rematch = [account for account in table.rematch if account != scope.account]
    if table.phase not in {"finished", "empty"}:
        finish_game(
            table, "resigned", now, limits, 3 - member.number if table.phase != "waiting" else None
        )
    if not table.members:
        table.phase, table.pending = "empty", None
        table.ended_at, table.expires_at = now, now + limits.result_seconds
    table.revision += 1
    return "accepted"


def _rejoinable(table: GameTable, member: GameMember, scope: GameScope, now: float) -> bool:
    """Whether a replacement controller may deliberately take its own membership back.

    A live lobby or round is recovered only inside the original reconnect grace. A
    finished table has no reconnect grace — its members are no longer tracked — so
    it is recoverable while its result is still displayed, letting a reconnect on
    the result screen rematch or leave.
    """
    if table.phase == "finished":
        return table.expires_at > now
    if table.phase not in {"playing_computer", "playing_human", "waiting"}:
        return False
    return member.controller == scope.controller or (
        member.offline_until is not None and member.offline_until > now
    )


def rejoin_table(
    state: WorldState, table: GameTable, scope: GameScope, now: float, limits: GameLimits
) -> GameOutcomeKind:
    """Require deliberate confirmation before a replacement controller inherits a membership.

    Args:
        state: Authority whose deadlines are re-evaluated after the rejoin.
        table: Table holding the account's membership.
        scope: Replacement account and controller generation.
        now: Redis Unix time of the commit.
        limits: Effective reconnect, turn and result deadlines.

    Returns:
        ``accepted``, ``not_participant`` without a seat, or ``unavailable`` once
        the reconnect grace (live table) or the result display (finished table)
        has ended.
    """
    member = next((member for member in table.members if member.account == scope.account), None)
    if member is None:
        return "not_participant"
    if not _rejoinable(table, member, scope, now):
        return "unavailable"
    member.controller, member.offline_until = scope.controller, None
    table.revision += 1
    prune_games(state, now, limits)
    return "accepted"


def rematch_table(
    table: GameTable,
    scope: GameScope,
    now: float,
    limits: GameLimits,
    prepared: OptionalGamePosition,
) -> GameOutcomeKind:
    """Require both human consents, or one explicit solo consent, and alternate the first color.

    Args:
        table: Finished table the consent addresses.
        scope: Consenting account and controller generation.
        now: Redis Unix time of the commit.
        limits: Effective round and turn deadlines.
        prepared: The computer's precomputed opening, required when the solo
            player's alternated color makes the computer move first.

    Returns:
        ``accepted`` once consent is recorded (or the fresh round started),
        ``not_participant`` without a seat, or ``unavailable`` when the table
        cannot rematch.
    """
    member = next((member for member in table.members if member.account == scope.account), None)
    if member is None:
        return "not_participant"
    if table.phase != "finished" or (not table.computer and len(table.members) != 2):
        return "unavailable"
    if table.computer:
        if member.number == 1 and prepared is None:
            return "unavailable"
        fresh_round(table, now, limits, computer=True, alternate=True)
        if prepared is not None:
            table.position = prepared
        return "accepted"
    if scope.account not in table.rematch:
        table.rematch.append(scope.account)
        table.revision += 1
    if len(table.rematch) == 2:
        fresh_round(table, now, limits, computer=False, alternate=True)
    return "accepted"
