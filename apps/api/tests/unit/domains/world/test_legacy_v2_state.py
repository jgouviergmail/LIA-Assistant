"""Persistence v2 is frozen before games; erasure must never inject game fields into it."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.domains.world.legacy_state import decode_legacy_state_v2, encode_legacy_state
from src.domains.world.store import WorldStore

pytestmark = pytest.mark.unit
FIXTURE = Path(__file__).parents[3] / "fixtures" / "world" / "authority-v2.json"


def test_legacy_socket_roundtrips_without_games_and_refuses_current_admission() -> None:
    raw = FIXTURE.read_text(encoding="utf-8")
    state = decode_legacy_state_v2(raw)
    assert json.loads(encode_legacy_state(state)) == json.loads(raw)
    with pytest.raises(ValidationError):
        WorldStore.decode(raw)
    owner, peer = tuple(state.actors)
    state.actors.pop(owner)
    after = json.loads(encode_legacy_state(state))
    assert after["version"] == 2
    assert "games" not in after and set(after["actors"]) == {peer}
    assert after["actors"][peer] == json.loads(raw)["actors"][peer]
