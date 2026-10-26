"""Validate byte limits and protocol before dispatch; no provider or database."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.world.transport import decode_command, origin_allowed

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "origin", [None, "null", "https://evil.invalid", "https://lia.invalid.evil.invalid"]
)
def test_socket_origins_are_exact_and_never_inferred(origin: str | None) -> None:
    assert not origin_allowed(origin, ["https://lia.invalid"])


def test_configured_origin_is_accepted_without_accepting_a_substring() -> None:
    assert origin_allowed("https://lia.invalid", ["https://lia.invalid"])


def test_frame_limit_counts_utf8_bytes_before_parsing() -> None:
    with pytest.raises(ValueError, match="frame_limit"):
        decode_command('"' + "界" * 1000 + '"', 2000)


@pytest.mark.parametrize(
    "text", ["null", "[]", '{"type":"tool"}', '{"type":"heartbeat","version":2}', '{"dx":NaN}']
)
def test_invalid_payload_cannot_reach_dispatch(text: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        decode_command(text, 8192)


def test_valid_move_round_trips_without_client_chosen_actor_fields() -> None:
    epoch = str(uuid4())
    value = decode_command(
        json.dumps({"type": "move", "version": 1, "epoch": epoch, "seq": 1, "dx": 0.5, "dy": -0.5}),
        8192,
    )
    assert value.type == "move" and value.epoch == epoch
