"""Account capacity, controller fencing, movement authority and wire privacy."""

import math
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.collision import POSE_SLOTS
from src.domains.world.schemas import MoveCommand, WorldState

pytestmark = pytest.mark.unit


def person(alias: str = "Visitor") -> Identity:
    return Identity(account_id=str(uuid4()), alias=alias, language="fr")


def test_arrivals_are_walkable_and_do_not_stack_characters_on_the_same_tile() -> None:
    from src.domains.world.collision import fits

    authority, state = Authority(Limits()), WorldState()
    for _ in range(5):
        identity = person()
        authority.join(state, identity, "control", 100)
    actors = list(state.actors.values())
    for index, actor in enumerate(actors):
        assert fits(actor.position["x"], actor.position["y"])
        for other in actors[index + 1 :]:
            assert (
                math.hypot(
                    actor.position["x"] - other.position["x"],
                    actor.position["y"] - other.position["y"],
                )
                >= 1.6
            )


def test_stopped_visitors_do_not_walk_forever_without_a_final_zero_frame() -> None:
    authority, state, identity = Authority(Limits()), WorldState(), person()
    authority.join(state, identity, "control", 100)
    authority.move(state, identity.account_id, "control", 1, 1, 0, 100.1)
    assert authority.project(state, identity.account_id, set(), 100.1).you.walking
    assert not authority.project(state, identity.account_id, set(), 100.5).you.walking


def test_capacity_is_per_account_and_fifo_waiters_never_receive_participants() -> None:
    authority, state = Authority(Limits(capacity=5)), WorldState()
    people = [person(str(n)) for n in range(7)]
    for identity in people:
        authority.join(state, identity, "controller", 100)
    assert len(state.actors) == 5
    assert len(state.queue) == 2
    waiting = authority.project(state, people[5].account_id, set(), 100)
    assert waiting.status == "waiting" and waiting.position == 1
    assert waiting.actors == []
    authority.leave(state, people[0].account_id, "controller")
    authority.join(state, people[6], "controller", 101)
    assert people[6].account_id not in state.actors
    authority.join(state, people[5], "controller", 101)
    assert people[5].account_id in state.actors


def test_duplicate_tab_does_not_take_control_and_stale_release_cannot_evict() -> None:
    authority, state, identity = Authority(Limits()), WorldState(), person()
    authority.join(state, identity, "first", 100)
    authority.join(state, identity, "second", 101)
    assert state.actors[identity.account_id].controller == "first"
    authority.takeover(state, identity.account_id, "second", 102)
    authority.leave(state, identity.account_id, "first")
    assert state.actors[identity.account_id].controller == "second"
    assert not authority.move(state, identity.account_id, "first", 1, 1, 0, 103)


def test_leases_expire_and_lost_offer_does_not_starve_the_next_waiter() -> None:
    authority = Authority(Limits(capacity=1, lease_seconds=5, offer_seconds=2))
    state, first, second, third = WorldState(), person(), person(), person()
    for identity, controller in [(first, "a"), (second, "b"), (third, "c")]:
        authority.join(state, identity, controller, 100)
    authority.prune(state, 106)
    assert state.queue[0].offered_until == 108
    authority.prune(state, 109)
    assert state.queue[0].account_id == third.account_id
    authority.join(state, third, "c", 109)
    assert third.account_id in state.actors


def test_public_projection_is_allowlisted_pairwise_and_excludes_private_homes() -> None:
    authority, state = Authority(Limits()), WorldState()
    owner, other, blocked = person("Owner"), person("Other"), person("Blocked")
    for identity in [owner, other, blocked]:
        authority.join(state, identity, identity.alias, 100)
    view = authority.project(state, owner.account_id, {blocked.account_id}, 100)
    assert [actor.alias for actor in view.actors] == ["Other"]
    wire = view.model_dump_json()
    for identity in [owner, other, blocked]:
        assert identity.account_id not in wire
    assert "controller" not in wire and "language" not in wire
    state.actors[other.account_id].position = POSE_SLOTS["home-bed:0"].approach.copy()
    assert [a.alias for a in authority.project(state, owner.account_id, set(), 100).actors] == [
        "Blocked"
    ]


def test_motion_is_time_bounded_idempotent_and_cannot_cross_solids() -> None:
    authority, state, identity = Authority(Limits()), WorldState(), person()
    authority.join(state, identity, "a", 100)
    actor = state.actors[identity.account_id]
    start = actor.position.copy()
    assert authority.move(state, identity.account_id, "a", 1, 1, 0, 100.1)
    assert actor.position["x"] - start["x"] <= 0.341
    assert not authority.move(state, identity.account_id, "a", 1, 1, 0, 101)
    assert authority.move(state, identity.account_id, "a", 2, 1, 0, 105)
    assert actor.position["x"] - start["x"] <= 0.681
    actor.position = {"x": 0.3, "y": 0.3}
    authority.move(state, identity.account_id, "a", 3, -1, -1, 105.1)
    assert actor.position["x"] >= 0.22 and actor.position["y"] >= 0.22


@pytest.mark.parametrize(
    "payload",
    [
        {"dx": float("nan"), "dy": 0},
        {"dx": 2, "dy": 0},
        {"dx": "1", "dy": 0},
        {"dx": 0, "dy": 0, "owner_id": "forged"},
    ],
)
def test_motion_rejects_nonfinite_coerced_and_extra_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MoveCommand.model_validate(
            {"type": "move", "version": 2, "seq": 1, "epoch": str(uuid4()), **payload}
        )


def test_equal_axis_motion_has_stable_facing_for_other_participants() -> None:
    authority, state, identity = Authority(Limits()), WorldState(), person()
    authority.join(state, identity, "control", 100)
    actor = state.actors[identity.account_id]
    actor.position = {"x": 30.3, "y": 32.9}
    for step in range(1, 4):
        assert authority.move(state, identity.account_id, "control", step, 1, -1, 100 + step / 10)
        assert actor.walking
        assert authority.project(state, identity.account_id, set(), 100 + step / 10).you.facing == 3


def test_running_is_explicit_normalized_and_bounded_by_the_server_clock() -> None:
    from src.domains.world.collision import WORLD

    travelled = []
    for running in (False, True):
        authority, state, identity = Authority(Limits()), WorldState(), person()
        authority.join(state, identity, "control", 100)
        start = dict(state.actors[identity.account_id].position)
        assert authority.move(
            state, identity.account_id, "control", 1, 0, 1, 100.9, running=running
        )
        end = state.actors[identity.account_id].position
        travelled.append(math.hypot(end["x"] - start["x"], end["y"] - start["y"]))
        assert travelled[-1] <= WORLD.movement.run * 0.1 + 1e-8
        assert not authority.move(state, identity.account_id, "foreign", 2, 1, 1, 101, running=True)
    assert travelled[1] / travelled[0] == pytest.approx(1.5)


@pytest.mark.parametrize("invalid", [1, "true", [], None])
def test_run_intent_is_a_strict_boolean(invalid: object) -> None:
    with pytest.raises(ValidationError):
        MoveCommand.model_validate(
            {
                "type": "move",
                "version": 2,
                "seq": 1,
                "dx": 0.0,
                "dy": 1.0,
                "running": invalid,
                "epoch": str(uuid4()),
            }
        )


def test_running_wire_intent_is_optional_and_accepted_when_explicit() -> None:
    wire = {"type": "move", "version": 2, "seq": 1, "dx": 0.0, "dy": 1.0, "epoch": str(uuid4())}
    assert not MoveCommand.model_validate(wire).running
    assert MoveCommand.model_validate({**wire, "running": True}).running
