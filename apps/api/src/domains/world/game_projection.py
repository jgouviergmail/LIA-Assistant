"""No spectators: only the controlling, consenting, eligible unblocked participants receive boards."""

from src.domains.world.game_catalogue import CABINETS
from src.domains.world.game_models import GameMove
from src.domains.world.game_rules import legal_moves
from src.domains.world.game_state import GameMember, GameTable
from src.domains.world.game_views import (
    CabinetView,
    GamePlayerView,
    GameRequestView,
    GameView,
    GameWaitingView,
)
from src.domains.world.policy import WorldPolicy
from src.domains.world.schemas import WorldState


def _visible(table: GameTable, policy: WorldPolicy) -> bool:
    """A revoked/blocked member hides the complete participant projection immediately."""
    return all(
        member.account in policy.eligible and member.account not in policy.blocked
        for member in table.members
    )


def _pending(
    state: WorldState, table: GameTable, account: str, policy: WorldPolicy
) -> GameRequestView | None:
    """A join requester has no board access and is shown by public alias only to the host."""
    pending = table.pending
    if not table.members or table.members[0].account != account or pending is None:
        return None
    actor = state.actors.get(pending.account)
    if actor is None or pending.account not in policy.eligible or pending.account in policy.blocked:
        return None
    return GameRequestView(id=actor.public_id, alias=actor.alias, expires_at=pending.expires_at)


def _legal_moves(table: GameTable, member: GameMember, controller: str) -> list[GameMove]:
    """Expose legal controls only to the actual current player on a connected active round."""
    active = (
        table.phase in {"playing_computer", "playing_human"}
        and table.paused_at is None
        and member.controller == controller
        and table.position.turn == member.number
    )
    return list(legal_moves(table.position)) if active else []


def _game(
    state: WorldState, table: GameTable, account: str, controller: str, policy: WorldPolicy
) -> GameView | None:
    """No board escapes on a missing admission or stale/blocked identity."""
    member = next((member for member in table.members if member.account == account), None)
    if (
        member is None
        or not _visible(table, policy)
        or any(other.account not in state.actors for other in table.members)
    ):
        return None
    needs_rejoin = member.controller != controller
    deadlines = [other.offline_until for other in table.members if other.offline_until is not None]
    return GameView(
        cabinet=table.cabinet,
        round_id=table.round_id,
        revision=table.revision,
        phase=table.phase,
        computer=table.computer,
        position=table.position,
        players=[
            GamePlayerView(
                id=other.public_id, alias=state.actors[other.account].alias, number=other.number
            )
            for other in table.members
        ],
        your_number=member.number,
        needs_rejoin=needs_rejoin,
        paused=table.paused_at is not None,
        turn_until=table.turn_until,
        expires_at=table.expires_at,
        reconnect_until=min(deadlines) if deadlines else None,
        pending=_pending(state, table, account, policy),
        legal_moves=_legal_moves(table, member, controller),
        reason=table.reason,
        winner=table.winner,
        rematch_ready=[other.number for other in table.members if other.account in table.rematch],
    )


def _waiting(table: GameTable, account: str, controller: str) -> GameWaitingView | None:
    """Only the requesting controller may withdraw its outstanding request."""
    pending = table.pending
    if pending is None or pending.account != account or pending.controller != controller:
        return None
    return GameWaitingView(
        cabinet=table.cabinet,
        round_id=table.round_id,
        revision=table.revision,
        expires_at=pending.expires_at,
    )


def _cabinet(table: GameTable, policy: WorldPolicy) -> CabinetView:
    """Coarse availability; only a joinable cabinet carries the round fence a join needs.

    A table holding someone blocked by, blocking or ineligible to the viewer reads
    exactly like any other full table — no distinct state and no round fence — so
    the hint cannot disclose a block or a revocation.
    """
    joinable = (
        _visible(table, policy)
        and table.phase in {"waiting", "playing_computer"}
        and table.pending is None
    )
    if not joinable:
        return CabinetView(cabinet=table.cabinet, availability="full")
    return CabinetView(
        cabinet=table.cabinet,
        availability="joinable",
        round_id=table.round_id,
        revision=table.revision,
    )


def project_games(
    state: WorldState, account: str, controller: str, policy: WorldPolicy, now: float
) -> tuple[list[CabinetView], GameView | None, GameWaitingView | None]:
    """Project only bounded coarse hints plus at most one own game or outstanding join request.

    Args:
        state: Authority read for this snapshot.
        account: Viewing account.
        controller: Viewing controller generation.
        policy: The viewer's fresh eligibility and block policy.
        now: Redis Unix time of the snapshot.

    Returns:
        Every cabinet's coarse hint, the viewer's own visible game, and the
        viewer's outstanding join request — nothing for a non-controlling,
        hidden or expired viewer.
    """
    actor = state.actors.get(account)
    if (
        actor is None
        or actor.controller != controller
        or not actor.visible
        or actor.expires_at <= now
    ):
        return [], None, None
    cabinets: list[CabinetView] = []
    own, waiting = None, None
    for cabinet in CABINETS:
        table = state.games.get(cabinet)
        if table is None or table.phase == "empty":
            cabinets.append(CabinetView(cabinet=cabinet, availability="empty"))
            continue
        cabinets.append(_cabinet(table, policy))
        if not _visible(table, policy):
            continue
        own = _game(state, table, account, controller, policy) or own
        waiting = _waiting(table, account, controller) or waiting
    return cabinets, own, waiting
