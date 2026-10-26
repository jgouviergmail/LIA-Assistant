"""Only live, fenced World connections may expose coarse presence to accepted peers."""

from uuid import uuid4

import pytest

from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.collision import WORLD
from src.domains.world.presence import (
    drop_presence,
    peer_presence,
    renew_presence,
    track_actor_presence,
)
from src.domains.world.schemas import WorldState

pytestmark = pytest.mark.unit


def joined() -> tuple[Authority, WorldState, str]:
    authority, state = Authority(Limits(lease_seconds=90)), WorldState()
    account = str(uuid4())
    authority.join(state, Identity(account, "Peer", "fr", "cookie-digest"), "current", 100)
    return authority, state, account


def test_only_actual_world_admission_creates_online_presence() -> None:
    _, state, account = joined()
    assert peer_presence(state, account, 100) == "online"
    assert peer_presence(state, str(uuid4()), 100) == "offline"
    track_actor_presence(state, "forged", "current", 100)
    assert "forged" not in state.presences


def test_home_status_reveals_only_a_coarse_state_and_returns_online_on_exit() -> None:
    _, state, account = joined()
    actor = state.actors[account]
    outside = actor.position.copy()
    home = next(zone for zone in WORLD.zones if zone.id == "home")
    actor.position = {"x": home.x + 1, "y": home.y + 1}
    track_actor_presence(state, account, "current", 101)
    assert peer_presence(state, account, 101) == "home"
    assert "position" not in state.presences[account].model_dump()
    actor.position = outside
    track_actor_presence(state, account, "current", 102)
    assert peer_presence(state, account, 102) == "online"


def test_idle_connection_keeps_away_presence_while_releasing_its_capacity() -> None:
    authority, state, account = joined()
    for now in range(110, 710, 10):
        authority.heartbeat(state, account, "current", now, visible=True, active=False)
        renew_presence(state, account, "current", now)
    assert peer_presence(state, account, 699) == "online"
    authority.prune(state, 700)
    assert account not in state.actors
    assert peer_presence(state, account, 700) == "away"
    renew_presence(state, account, "current", 710)
    assert peer_presence(state, account, 710) == "away"
    assert peer_presence(state, account, 801) == "offline"


def test_disconnect_and_old_controller_cannot_affect_the_successor() -> None:
    authority, state, account = joined()
    authority.takeover(state, account, "successor", 101)
    drop_presence(state, account, "current")
    renew_presence(state, account, "current", 1000)
    assert peer_presence(state, account, 102) == "online"
    assert peer_presence(state, account, 193) == "offline"
    drop_presence(state, account, "successor")
    assert account not in state.presences
    assert account in state.actors  # Transport loss retains the bounded actor reconnect grace.


def test_leave_and_serialization_preserve_privacy_and_other_accounts() -> None:
    authority, state, account = joined()
    second = str(uuid4())
    authority.join(state, Identity(second, "Other", "en"), "other", 101)
    restored = WorldState.model_validate_json(state.model_dump_json())
    authority.leave(restored, account, "current")
    assert peer_presence(restored, account, 102) == "offline"
    assert peer_presence(restored, second, 102) == "online"
    view = authority.project(restored, second, set(), 102, "other").model_dump()
    assert "presences" not in view
    assert account not in str(view)


def test_disconnected_actor_grace_never_recreates_live_presence_on_prune() -> None:
    authority, state, account = joined()
    drop_presence(state, account, "current")
    authority.prune(state, 101)
    assert account in state.actors
    assert peer_presence(state, account, 101) == "offline"


def test_away_overrides_home_and_old_snapshots_have_no_inferred_presence() -> None:
    _, state, account = joined()
    state.presences[account].at_home = True
    state.presences[account].expires_at = 800
    assert peer_presence(state, account, 700) == "away"
    old_snapshot = state.model_dump(exclude={"presences"})
    restored = WorldState.model_validate(old_snapshot)
    assert restored.presences == {}
    assert peer_presence(restored, account, 101) == "offline"


def test_transport_resume_does_not_invent_new_human_activity() -> None:
    authority, state, account = joined()
    assert authority.resume(
        state, Identity(account, "Peer", "fr", "cookie-digest"), "current", "resumed", 110
    )
    assert state.actors[account].activity_at == 100
    assert state.presences[account].activity_at == 100
    assert state.presences[account].controller == "resumed"


def test_missing_heartbeats_expire_presence_independently_of_actor_capacity() -> None:
    authority, state, account = joined()
    state.actors[account].expires_at = 1000
    authority.prune(state, 190)
    assert account in state.actors
    assert account not in state.presences
    assert peer_presence(state, account, 190) == "offline"
