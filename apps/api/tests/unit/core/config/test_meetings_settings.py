"""Bounds of the meetings settings (ADR-258): the durability contract is refused
at load time, never discovered at 3 a.m.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config.meetings import MeetingsSettings
from src.core.constants import (
    MEETINGS_MAX_DURATION_MINUTES_CEILING,
    STT_BYTES_PER_SECOND_AT_16KHZ_INT16,
)

pytestmark = pytest.mark.unit


def test_defaults_load_and_respect_their_own_invariants() -> None:
    settings = MeetingsSettings(_env_file=None)
    assert settings.meetings_enabled is True
    assert (
        settings.meetings_job_heartbeat_interval_seconds < settings.meetings_job_lease_ttl_seconds
    )
    assert settings.meetings_segment_max_seconds >= settings.meetings_segment_seconds
    assert settings.meetings_max_duration_minutes <= MEETINGS_MAX_DURATION_MINUTES_CEILING


def test_heartbeat_must_stay_under_the_lease() -> None:
    with pytest.raises(ValidationError, match="heartbeat_interval_seconds must be <"):
        MeetingsSettings(
            _env_file=None,
            meetings_job_lease_ttl_seconds=120,
            meetings_job_heartbeat_interval_seconds=120,
        )


def test_a_segment_cannot_be_shorter_than_the_cadence() -> None:
    with pytest.raises(ValidationError, match="segment_max_seconds must be >="):
        MeetingsSettings(
            _env_file=None, meetings_segment_seconds=60, meetings_segment_max_seconds=30
        )


def test_the_duration_ceiling_is_a_provider_fact_not_a_preference() -> None:
    with pytest.raises(ValidationError):
        MeetingsSettings(
            _env_file=None,
            meetings_max_duration_minutes=MEETINGS_MAX_DURATION_MINUTES_CEILING + 1,
        )


def test_segment_byte_cap_is_derived_from_the_densest_format() -> None:
    settings = MeetingsSettings(_env_file=None, meetings_segment_max_seconds=60)
    assert settings.meetings_segment_max_bytes == int(
        STT_BYTES_PER_SECOND_AT_16KHZ_INT16 * 60 * 1.05
    )
