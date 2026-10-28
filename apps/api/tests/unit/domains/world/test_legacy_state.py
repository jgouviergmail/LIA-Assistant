"""Older active scene documents retain their original field shape during erasure."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.domains.world.legacy_state import decode_legacy_state, encode_legacy_state
from src.domains.world.store import MAX_STATE_BYTES, WorldUnavailable

pytestmark = pytest.mark.unit
FIXTURE = Path(__file__).parents[3] / "fixtures" / "world" / "authority-v1.json"


def test_old_scene_round_trip_preserves_every_original_field() -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    assert json.loads(encode_legacy_state(decode_legacy_state(raw))) == json.loads(raw)


def test_selective_erasure_never_injects_new_actor_defaults_into_an_older_reader() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    owner, peer = tuple(raw["actors"])
    for actor in raw["actors"].values():
        actor.pop("appearance")
        actor.pop("appearance_revision")
        actor.pop("pose_result")
    state = decode_legacy_state(json.dumps(raw))
    state.actors.pop(owner)
    state.presences.pop(owner)
    state.queue = [waiter for waiter in state.queue if waiter.account_id != owner]
    encoded = json.loads(encode_legacy_state(state))
    assert encoded["version"] == 1 and encoded["epoch"] == raw["epoch"]
    assert encoded["actors"] == {peer: raw["actors"][peer]}
    assert encoded["presences"] == {peer: raw["presences"][peer]}
    assert encoded["queue"] == raw["queue"]
    assert "emote" not in encoded["actors"][peer]
    assert "receipts" not in encoded["actors"][peer]


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_legacy_generation_is_not_a_compatibility_backdoor(version: object) -> None:
    with pytest.raises(ValidationError):
        decode_legacy_state(json.dumps({"version": version}))


def test_legacy_decoder_counts_utf8_bytes_before_parsing() -> None:
    with pytest.raises(WorldUnavailable, match="world_state_limit"):
        decode_legacy_state("雪" * 50_000)


def test_oversized_text_is_refused_without_allocating_an_encoded_copy() -> None:
    class Oversized(str):
        def encode(self, *_args: object, **_kwargs: object) -> bytes:
            raise AssertionError("oversized text must be rejected before UTF-8 allocation")

    with pytest.raises(WorldUnavailable, match="world_state_limit"):
        decode_legacy_state(Oversized("x" * (MAX_STATE_BYTES + 1)))
