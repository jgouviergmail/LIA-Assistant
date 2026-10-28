"""Pure game deadlines and loss-of-presence handling; no per-match timer or worker."""

import math

from src.core.constants import WORLD_ARCADE_CABINET_REACH
from src.domains.world.game_catalogue import CABINETS
from src.domains.world.game_context import GameLimits
from src.domains.world.game_models import CabinetId, OptionalPlayer
from src.domains.world.game_state import GameEndReason, GameMember, GameTable
from src.domains.world.schemas import ActorState, WorldState


def at_cabinet(actor: ActorState, cabinet: CabinetId) -> bool:
    """Use the authored ground approach, never a client camera or predicted position.

    Args:
        actor: The authoritative actor.
        cabinet: Authored cabinet whose front approach counts.

    Returns:
        Whether the standing actor is within the cabinet's reach.
    """
    point = CABINETS[cabinet].approach
    return (
        actor.pose is None
        and math.hypot(actor.position["x"] - point["x"], actor.position["y"] - point["y"])
        <= WORLD_ARCADE_CABINET_REACH
    )


def near_cabinet(actor: ActorState, table: GameTable) -> bool:
    """Resolve a table's immutable authored interaction approach.

    Args:
        actor: The authoritative actor.
        table: Table whose cabinet approach counts.

    Returns:
        Whether the standing actor is within the table's cabinet reach.
    """
    return at_cabinet(actor, table.cabinet)


def finish_game(
    table: GameTable,
    reason: GameEndReason,
    now: float,
    limits: GameLimits,
    winner: OptionalPlayer = None,
) -> None:
    """Keep one bounded terminal result; unavailable and abandoned never invent a winner.

    Args:
        table: Table finished in place.
        reason: Server-derived terminal cause.
        now: Redis Unix time of the commit.
        limits: Effective result display deadline.
        winner: Rule or resignation winner; None for every other cause.
    """
    table.phase, table.reason, table.winner = "finished", reason, winner
    table.ended_at, table.expires_at = now, now + limits.result_seconds
    table.pending, table.paused_at, table.remaining_turn = None, None, None
    table.rematch = []


def _connected(state: WorldState, member: GameMember, now: float) -> bool:
    """Require both the current World controller and its visible, live connection lease."""
    actor, presence = state.actors.get(member.account), state.presences.get(member.account)
    return (
        actor is not None
        and actor.visible
        and actor.expires_at > now
        and actor.controller == member.controller
        and presence is not None
        and presence.controller == member.controller
        and presence.expires_at > now
    )


def _pending_expired(state: WorldState, table: GameTable, now: float) -> bool:
    """A hidden, departed or replaced requester cannot be accepted later."""
    pending = table.pending
    if pending is None:
        return False
    actor = state.actors.get(pending.account)
    return (
        pending.expires_at <= now
        or actor is None
        or actor.controller != pending.controller
        or actor.expires_at <= now
        or not actor.visible
        or not near_cabinet(actor, table)
    )


def _pause_or_resume(state: WorldState, table: GameTable, now: float, limits: GameLimits) -> bool:
    """Anchor grace and remaining turn time once; ordinary ticks cannot extend either."""
    changed, offline = False, False
    for member in table.members:
        if _connected(state, member, now):
            if member.offline_until is not None:
                member.offline_until, changed = None, True
            continue
        offline = True
        if member.offline_until is None:
            member.offline_until, changed = now + limits.reconnect_seconds, True
        if member.offline_until <= now:
            table.members = [other for other in table.members if other is not member]
            finish_game(table, "unavailable", now, limits)
            return True
    if offline and table.paused_at is None:
        table.paused_at, table.remaining_turn = now, max(0.0, table.turn_until - now)
        return True
    if not offline and table.paused_at is not None:
        table.turn_until = now + (table.remaining_turn or 0)
        table.paused_at, table.remaining_turn = None, None
        return True
    return changed


def _prune_round(state: WorldState, table: GameTable, now: float, limits: GameLimits) -> bool:
    """Expire admissions, maximum round life and turns before considering reconnection."""
    missing = _missing_members(state, table, now)
    if missing:
        table.members = [member for member in table.members if member not in missing]
        finish_game(table, "unavailable", now, limits)
        return True
    if now >= table.expires_at or (table.paused_at is None and now >= table.turn_until):
        finish_game(table, "abandoned", now, limits)
        return True
    departed = next(
        (
            member
            for member in table.members
            if not near_cabinet(state.actors[member.account], table)
        ),
        None,
    )
    if departed is not None:
        table.members = [member for member in table.members if member is not departed]
        finish_game(table, "resigned", now, limits, 3 - departed.number)
        return True
    return _pause_or_resume(state, table, now, limits)


def _missing_members(state: WorldState, table: GameTable, now: float) -> list[GameMember]:
    """Separate native admission expiry from the shorter reconnect overlay."""
    return [
        member
        for member in table.members
        if member.account not in state.actors
        or state.actors[member.account].expires_at <= now
        or state.actors[member.account].public_id != member.public_id
    ]


def _waiting_invalid(state: WorldState, table: GameTable, now: float) -> bool:
    """A departed or remote host cannot keep an empty lobby reserved."""
    if not table.members or _missing_members(state, table, now):
        return True
    return not near_cabinet(state.actors[table.members[0].account], table)


def prune_games(state: WorldState, now: float, limits: GameLimits) -> bool:
    """Return whether bounded authoritative game state changed, so callers can persist actual ticks.

    Args:
        state: Authority whose tables are pruned in place.
        now: Redis Unix time of the evaluation.
        limits: Effective lobby, request, reconnect, turn, round and result deadlines.

    Returns:
        Whether any table expired, ended, paused, resumed or lost a request.
    """
    changed = False
    for cabinet, table in tuple(state.games.items()):
        if table.phase in {"empty", "finished", "waiting"} and table.expires_at <= now:
            del state.games[cabinet]
            changed = True
            continue
        local = False
        if _pending_expired(state, table, now):
            table.pending, local = None, True
        if table.phase == "waiting":
            if _waiting_invalid(state, table, now):
                del state.games[cabinet]
                changed = True
                continue
            local = _pause_or_resume(state, table, now, limits) or local
        elif table.phase in {"playing_computer", "playing_human"}:
            local = _prune_round(state, table, now, limits) or local
        if local:
            table.revision += 1
            changed = True
    return changed
