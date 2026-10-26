"""Pose transitions run inside the same Redis CAS as movement and admission."""

import math

from src.domains.world.collision import POSE_SLOTS, fits, private_home
from src.domains.world.schemas import ActorState, WorldState

SLOTS = POSE_SLOTS


def stand(actor: ActorState) -> bool:
    """Leave a pose only when its authored approach position remains walkable."""
    if actor.pose is None:
        return True
    slot = SLOTS.get(actor.pose)
    if slot is None or not fits(**slot.approach):
        return False
    actor.position = slot.approach.copy()
    actor.pose = None
    actor.walking = False
    return True


def apply_pose(
    state: WorldState,
    account: str,
    controller: str,
    seq: int,
    slot_id: str | None,
    now: float,
) -> bool:
    """Fence a pose request by controller and sequence, then enforce reach and occupancy."""
    actor = state.actors.get(account)
    if (
        actor is None
        or actor.controller != controller
        or seq <= actor.seq
        or actor.expires_at <= now
    ):
        return False
    # Rejected requests are acknowledged too: a lost frame cannot later acquire a seat.
    actor.seq, actor.moved_at = seq, now
    actor.walking = False
    if slot_id is None:
        accepted = stand(actor)
        actor.pose_result = "accepted" if accepted else "invalid"
        return accepted
    slot = SLOTS.get(slot_id)
    if slot is None:
        actor.pose_result = "invalid"
        return False
    if actor.pose == slot_id:
        actor.pose_result = "accepted"
        return True
    if (
        actor.pose is not None
        or math.hypot(
            actor.position["x"] - slot.approach["x"],
            actor.position["y"] - slot.approach["y"],
        )
        > 0.6
    ):
        actor.pose_result = "out_of_reach"
        return False
    if _occupied(state, slot_id, now):
        actor.pose_result = "occupied"
        return False
    actor.pose, actor.position, actor.facing = (
        slot.id,
        slot.position.copy(),
        slot.facing,
    )
    actor.activity_at = now
    actor.pose_result = "accepted"
    return True


def _occupied(state: WorldState, slot_id: str, now: float) -> bool:
    """Check whether another live actor already occupies the requested authored pose slot."""
    if private_home(SLOTS[slot_id].position):
        return False
    return any(other.pose == slot_id and other.expires_at > now for other in state.actors.values())
