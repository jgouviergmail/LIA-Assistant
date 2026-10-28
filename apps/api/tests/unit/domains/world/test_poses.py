"""Authored seating, privacy, fencing and safe exits under the shared authority."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.collision import fits, private_home
from src.domains.world.poses import SLOTS, apply_pose
from src.domains.world.schemas import COMMAND_ADAPTER, WorldState

pytestmark = pytest.mark.unit


def setup():
    authority, state = Authority(Limits()), WorldState()
    for name in ("a", "b"):
        authority.join(state, Identity(name, name, "fr"), name, 100)
    slot = next(s for s in SLOTS.values() if s.kind == "sit" and not private_home(s.position))
    for actor in state.actors.values():
        actor.position = slot.approach.copy()
    return authority, state, slot


def test_one_shared_slot_has_one_owner_and_standing_releases_it():
    _, state, slot = setup()
    assert apply_pose(state, "a", "a", 1, slot.id, 101)
    assert not apply_pose(state, "b", "b", 1, slot.id, 101)
    assert state.actors["b"].pose_result == "occupied"
    assert state.actors["b"].seq == 1
    assert state.actors["a"].position == slot.position
    assert apply_pose(state, "a", "a", 2, None, 102)
    assert fits(**state.actors["a"].position)
    assert state.actors["a"].position == slot.approach
    assert apply_pose(state, "b", "b", 2, slot.id, 102)


def test_private_furniture_is_per_owner_and_never_projects_to_peers():
    authority, state, _ = setup()
    slot = next(s for s in SLOTS.values() if s.kind == "lie" and private_home(s.position))
    for account in state.actors:
        state.actors[account].position = slot.approach.copy()
        assert apply_pose(state, account, account, 1, slot.id, 101)
    assert authority.project(state, "a", set(), 101).actors == []
    wire = authority.project(state, "a", set(), 101).model_dump_json()
    assert '"pose"' in wire and '"controller"' not in wire


@pytest.mark.parametrize("slot_id", ["workout-1:0", "workout-2:0"])
def test_shared_workout_pose_is_exclusive_public_and_releases_safely(slot_id: str):
    authority, state, _ = setup()
    slot = SLOTS[slot_id]
    assert slot.kind == "lie" and not private_home(slot.position)
    for actor in state.actors.values():
        actor.position = slot.approach.copy()
    assert apply_pose(state, "a", "a", 1, slot_id, 101)
    assert not apply_pose(state, "b", "b", 1, slot_id, 101)
    assert state.actors["b"].pose_result == "occupied"
    public = authority.project(state, "b", set(), 101).actors
    assert len(public) == 1 and public[0].pose == slot_id
    state = WorldState.model_validate_json(state.model_dump_json())
    assert apply_pose(state, "a", "a", 2, None, 102)
    assert fits(**state.actors["a"].position)
    assert apply_pose(state, "b", "b", 2, slot_id, 102)


def test_pose_fences_replay_controller_distance_invalid_slot_and_expiry():
    _, state, slot = setup()
    assert not apply_pose(state, "a", "stale", 1, slot.id, 101)
    assert state.actors["a"].seq == 0
    assert not apply_pose(state, "a", "a", 1, "invented", 101)
    assert state.actors["a"].pose_result == "invalid"
    assert not apply_pose(state, "a", "a", 1, slot.id, 101)
    state.actors["a"].position = {"x": 34.5, "y": 30.5}
    assert not apply_pose(state, "a", "a", 2, slot.id, 102)
    assert state.actors["a"].pose_result == "out_of_reach"
    state.actors["a"].expires_at = 103
    assert not apply_pose(state, "a", "a", 3, slot.id, 104)


def test_pose_survives_serialization_and_resume_but_lease_releases_occupancy():
    authority, state, slot = setup()
    assert apply_pose(state, "a", "a", 1, slot.id, 101)
    state = WorldState.model_validate_json(state.model_dump_json())
    assert authority.resume(state, Identity("a", "a", "fr"), "a", "new", 102)
    assert state.actors["a"].pose == slot.id
    assert not apply_pose(state, "a", "a", 2, None, 103)
    state.actors["a"].expires_at = 103
    authority.prune(state, 104)
    assert apply_pose(state, "b", "b", 1, slot.id, 104)


def test_movement_stands_at_authored_exit_before_moving_and_never_walks_through_furniture():
    authority, state, slot = setup()
    assert apply_pose(state, "a", "a", 1, slot.id, 101)
    assert authority.move(state, "a", "a", 2, 1, 0, 101.1)
    assert state.actors["a"].pose is None
    assert fits(**state.actors["a"].position)
    assert abs(state.actors["a"].position["x"] - slot.approach["x"]) <= 0.341


def test_every_authored_slot_has_a_finite_walkable_exit_in_its_privacy_scope():
    assert len(SLOTS) > 10
    for slot in SLOTS.values():
        assert fits(**slot.approach), slot.id
        assert private_home(slot.approach) == private_home(slot.position), slot.id


@pytest.mark.parametrize(
    "extra", [{"position": {"x": 0, "y": 0}}, {"slot": "x" * 97}, {"seq": True}]
)
def test_pose_wire_refuses_client_position_coercion_and_unbounded_identifiers(extra):
    with pytest.raises(ValidationError):
        COMMAND_ADAPTER.validate_python(
            {"type": "pose", "version": 2, "epoch": str(uuid4()), "seq": 1, "slot": None, **extra}
        )
