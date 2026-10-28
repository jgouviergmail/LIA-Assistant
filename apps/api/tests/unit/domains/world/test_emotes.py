"""Finite gestures share controller/sequence authority without impersonating pose receipts."""

from uuid import uuid4

import pytest

from src.domains.world.authority import Authority, Identity, Limits
from src.domains.world.collision import POSE_SLOTS
from src.domains.world.emotes import apply_emote
from src.domains.world.poses import apply_pose
from src.domains.world.schemas import WorldState
from src.domains.world.socket_models import EmoteKind, EmoteReceipt

pytestmark = pytest.mark.unit


def joined() -> tuple[Authority, WorldState, str]:
    authority, state = Authority(Limits(capacity=10)), WorldState()
    account = str(uuid4())
    authority.join(state, Identity(account, "Visitor", "fr"), "controller", 100)
    return authority, state, account


def test_gesture_expiry_cooldown_and_duplicates_do_not_extend_the_same_animation() -> None:
    authority, state, account = joined()
    assert apply_emote(state, account, "controller", 1, "wave", 100)
    actor = state.actors[account]
    assert actor.emote is not None and actor.emote.serial == 1
    assert actor.emote.expires_at == 102
    assert not apply_emote(state, account, "controller", 1, "wave", 101)
    assert not apply_emote(state, account, "controller", 2, "laugh", 101)
    assert actor.receipts[-1].result == "rate_limited"
    assert actor.emote.expires_at == 102
    assert authority.public_actor(actor, 102).emote is None
    assert apply_emote(state, account, "controller", 3, "thanks", 102)
    assert actor.emote.serial == 2


@pytest.mark.parametrize("kind", ["wave", "thanks", "applause", "laugh", "question", "celebrate"])
def test_every_authored_gesture_uses_the_same_finite_authority(kind: EmoteKind) -> None:
    _, state, account = joined()
    assert apply_emote(state, account, "controller", 1, kind, 100)
    actor = state.actors[account]
    assert actor.emote is not None and actor.emote.emote == kind
    actor.emote_serial = 2**31 - 1
    assert not apply_emote(state, account, "controller", 2, kind, 102)
    assert actor.receipts[-1].result == "unavailable"


def test_takeover_fences_commands_and_receipts_without_bypassing_social_cooldown() -> None:
    authority, state, account = joined()
    assert apply_emote(state, account, "controller", 1, "wave", 100)
    authority.takeover(state, account, "successor", 100.5)
    actor = state.actors[account]
    assert actor.receipts == []
    assert not apply_emote(state, account, "controller", 2, "laugh", 101)
    assert not apply_emote(state, account, "successor", 1, "laugh", 101)
    assert apply_emote(state, account, "successor", 2, "laugh", 102)
    assert actor.emote is not None and actor.emote.serial == 2


def test_hidden_home_expired_and_absent_senders_cannot_publish() -> None:
    authority, state, account = joined()
    actor = state.actors[account]
    assert not apply_emote(state, "absent", "controller", 1, "wave", 100)
    authority.heartbeat(state, account, "controller", 100, visible=False, active=False)
    assert not apply_emote(state, account, "controller", 1, "wave", 100)
    authority.heartbeat(state, account, "controller", 100, visible=True, active=False)
    actor.position = {"x": 60.0, "y": 70.0}
    from src.domains.world.collision import private_home

    assert private_home(actor.position)
    assert not apply_emote(state, account, "controller", 2, "wave", 101)
    actor.expires_at = 101
    assert not apply_emote(state, account, "controller", 3, "wave", 102)
    assert actor.emote is None


def test_seated_gesture_preserves_contact_and_receipt_survives_later_movement() -> None:
    authority, state, account = joined()
    actor = state.actors[account]
    slot = next(iter(POSE_SLOTS.values()))
    actor.position = slot.approach.copy()
    assert apply_pose(state, account, "controller", 1, slot.id, 100)
    assert apply_emote(state, account, "controller", 2, "applause", 100)
    assert actor.pose == slot.id and actor.position == slot.position
    assert [(r.seq, r.kind, r.result) for r in actor.receipts] == [
        (1, "pose", "accepted"),
        (2, "emote", "accepted"),
    ]
    assert authority.move(state, account, "controller", 3, 1, 0, 100.1)
    view = authority.project(state, account, set(), 100.1, "controller")
    assert view.receipts[0].kind == "pose" and view.receipts[0].seq == 1
    assert view.server_time == 100.1
    assert "receipts" not in authority.public_actor(actor, 100.1).model_dump()
    assert authority.project(state, account, set(), 100.1, "stale-tab").receipts == []
    for seq in range(4, 40):
        apply_emote(state, account, "controller", seq, "wave", 100.1)
    assert len(actor.receipts) == 16


def test_projection_filters_blocked_and_hidden_gestures_and_bounds_wire_size() -> None:
    authority, state, account = joined()
    for index in range(9):
        peer = str(uuid4())
        authority.join(state, Identity(peer, "Person" * 4, "fr"), str(index), 100)
        apply_emote(state, peer, str(index), 1, "celebrate", 100)
    for seq in range(1, 18):
        apply_emote(state, account, "controller", seq, "wave", 100)
    full = authority.project(state, account, set(), 100, "controller")
    assert len(full.actors) == 9 and len(full.receipts) == 16
    assert len(full.model_dump_json().encode()) < 16384
    blocked = next(key for key in state.actors if key != account)
    view = authority.project(state, account, {blocked}, 100, "controller")
    assert len(view.actors) == 8
    assert len(view.model_dump_json().encode()) < 16384
    own = state.actors[account]
    authority.heartbeat(state, account, "controller", 100.1, visible=False, active=False)
    assert authority.public_actor(own, 100.1).emote is None


def test_a_refusal_is_predicted_and_settled_without_publishing_anything() -> None:
    from src.domains.world.emotes import emote_refusal, refuse_emote

    authority, state, account = joined()
    actor = state.actors[account]
    # A publishable gesture is neither predicted nor settled as a refusal.
    assert emote_refusal(state, account, "controller", 1, 100) is None
    assert not refuse_emote(state, account, "controller", 1, 100)
    assert actor.seq == 0 and actor.receipts == []
    assert apply_emote(state, account, "controller", 1, "wave", 100)
    # Inside the cooldown: predicted, then settled under its own sequence.
    assert emote_refusal(state, account, "controller", 2, 101) == "rate_limited"
    assert refuse_emote(state, account, "controller", 2, 101)
    assert actor.seq == 2 and actor.receipts[-1] == EmoteReceipt(seq=2, result="rate_limited")
    assert actor.emote is not None and actor.emote.serial == 1 and actor.emote.emote == "wave"
    # A stale sequence or controller is inert: nothing to predict, nothing recorded.
    assert emote_refusal(state, account, "controller", 2, 101) is None
    assert not refuse_emote(state, account, "stale-tab", 3, 101)
    assert actor.seq == 2
    # Visibility takes precedence over the cooldown, exactly as in apply_emote.
    authority.heartbeat(state, account, "controller", 101, visible=False, active=False)
    assert emote_refusal(state, account, "controller", 3, 101) == "unavailable"
    assert refuse_emote(state, account, "controller", 3, 101)
    assert actor.receipts[-1] == EmoteReceipt(seq=3, result="unavailable")
