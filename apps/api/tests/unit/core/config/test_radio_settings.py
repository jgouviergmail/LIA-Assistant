"""Bounds of the radio settings (ADR-324): a contradiction is refused at load time."""

from __future__ import annotations

from typing import Any, get_args

import pytest
from pydantic import ValidationError

from src.core.config.radio import RadioSettings
from src.domains.radio.setup import VerificationMode

pytestmark = pytest.mark.unit


def test_defaults_load_and_respect_their_own_invariants() -> None:
    settings = RadioSettings(_env_file=None)
    assert settings.radio_timer_minutes <= settings.radio_timer_max_minutes
    assert settings.radio_analysis_min_points <= settings.radio_analysis_max_points
    assert settings.radio_newsroom_pass_timeout_seconds < settings.radio_newsroom_interval_seconds
    assert settings.radio_record_ttl_seconds > settings.radio_pause_timeout_seconds


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"radio_timer_minutes": 90, "radio_timer_max_minutes": 60}, "RADIO_TIMER_MINUTES"),
        (
            {"radio_analysis_min_points": 6, "radio_analysis_max_points": 4},
            "RADIO_ANALYSIS_MIN_POINTS",
        ),
        (
            {"radio_newsroom_interval_seconds": 300, "radio_newsroom_pass_timeout_seconds": 300},
            "pass must end",
        ),
        (
            {"radio_pause_timeout_seconds": 1800, "radio_record_ttl_seconds": 1800},
            "outlive its pause",
        ),
    ],
)
def test_a_contradiction_is_refused_at_load_time(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        RadioSettings(_env_file=None, **overrides)


def test_the_default_verification_speaks_the_domains_own_vocabulary() -> None:
    """``core`` cannot import the domain's enum: the two lists are pinned equal here."""
    declared = get_args(RadioSettings.model_fields["radio_verification_default"].annotation)
    assert set(declared) == {mode.value for mode in VerificationMode}
