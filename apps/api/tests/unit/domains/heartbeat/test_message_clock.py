"""The message prompt is written against the person's clock, not UTC.

Measured 2026-09-11 on docker dev: a real tick delivered « Il est 9h43 et il
brille toujours par son absence » at 11:43 Paris. The decision prompt had the
local time all along; the message prompt formatted ``datetime.now(tz=UTC)``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from src.domains.heartbeat.prompts import message_clock
from src.domains.heartbeat.schemas import HeartbeatContext

pytestmark = pytest.mark.unit


def test_the_local_instant_and_its_zone_are_used() -> None:
    context = HeartbeatContext()
    context.user_local_time = datetime(2026, 9, 11, 11, 43, tzinfo=ZoneInfo("Europe/Paris"))
    label, zone = message_clock(context)
    assert label == "11/09/2026 11:43"
    assert zone == "Europe/Paris"


def test_a_context_without_a_local_time_falls_back_to_utc_and_says_so() -> None:
    context = HeartbeatContext()
    label, zone = message_clock(context)
    assert zone is None
    assert label == datetime.now(tz=UTC).strftime("%d/%m/%Y %H:%M")


def test_a_naive_local_time_is_not_trusted() -> None:
    context = HeartbeatContext()
    context.user_local_time = datetime(2026, 9, 11, 11, 43)
    _label, zone = message_clock(context)
    assert zone is None
