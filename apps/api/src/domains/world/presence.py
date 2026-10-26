"""Coarse accepted-peer presence, separate from admission capacity and public positions."""

from typing import Literal

from src.core.constants import WORLD_PEER_AWAY_SECONDS, WORLD_PRESENCE_LEASE_SECONDS
from src.domains.world.collision import private_home
from src.domains.world.schemas import PresenceLease, WorldState

PeerPresenceStatus = Literal["online", "home", "away", "offline"]


def track_actor_presence(state: WorldState, account: str, controller: str, now: float) -> None:
    """Capture only the controlling actor's trusted activity and coarse home state."""
    actor = state.actors.get(account)
    if actor is None or actor.controller != controller:
        return
    previous = state.presences.get(account)
    expiry = now + WORLD_PRESENCE_LEASE_SECONDS
    if previous is not None and previous.controller == controller:
        expiry = previous.expires_at
    state.presences[account] = PresenceLease(
        controller=controller,
        binding=actor.binding,
        expires_at=expiry,
        activity_at=actor.activity_at,
        at_home=private_home(actor.position),
    )


def renew_presence(state: WorldState, account: str, controller: str, now: float) -> None:
    """Renew an actual socket command without pretending that a heartbeat is human activity."""
    lease = state.presences.get(account)
    if lease is not None and lease.controller == controller:
        lease.expires_at = now + WORLD_PRESENCE_LEASE_SECONDS


def drop_presence(state: WorldState, account: str, controller: str) -> None:
    """Withdraw this connection only; delayed teardown cannot erase its successor."""
    lease = state.presences.get(account)
    if lease is not None and lease.controller == controller:
        state.presences.pop(account)


def prune_presences(state: WorldState, now: float) -> None:
    """Preserve trusted last activity before idle eviction and forget expired connection leases."""
    for account, lease in tuple(state.presences.items()):
        if lease.expires_at <= now:
            state.presences.pop(account)
        else:
            track_actor_presence(state, account, lease.controller, now)


def peer_presence(state: WorldState, account: str, now: float) -> PeerPresenceStatus:
    """Return one coarse status; away takes precedence over the private-home marker."""
    lease = state.presences.get(account)
    if lease is None or lease.expires_at <= now:
        return "offline"
    if now - lease.activity_at >= WORLD_PEER_AWAY_SECONDS:
        return "away"
    return "home" if lease.at_home else "online"
