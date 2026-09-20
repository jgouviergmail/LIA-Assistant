"""Per-model settings of a live connector: bounds, the unlimited value, the legacy shape, a NEW dict."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.constants import (
    LIVE_DURATION_UNLIMITED,
    LIVE_IDLE_TIMEOUT_SECONDS_MAX,
    LIVE_IDLE_TIMEOUT_SECONDS_MIN,
    LIVE_SESSION_MAX_MINUTES_MAX,
)
from src.domains.live.model_settings import (
    LiveModelSettings,
    read_model_settings,
    read_models,
    write_models,
)

pytestmark = pytest.mark.unit


def _settings(**overrides: object) -> LiveModelSettings:
    base: dict[str, object] = {
        "voice": "Kore",
        "thinking_level": None,
        "idle_timeout_seconds": 60,
        "session_max_minutes": 10,
    }
    base.update(overrides)
    return LiveModelSettings.model_validate(base)


def test_zero_means_unlimited_and_the_bounds_are_the_instance_settings_own() -> None:
    # The per-model bound and the instance setting's bound are ONE constant
    # (ADR-184): a value the settings page accepts is a value the instance honours.
    assert _settings(idle_timeout_seconds=LIVE_DURATION_UNLIMITED).idle_timeout_seconds == 0
    assert _settings(session_max_minutes=LIVE_DURATION_UNLIMITED).session_max_minutes == 0
    assert (
        _settings(idle_timeout_seconds=LIVE_IDLE_TIMEOUT_SECONDS_MAX).idle_timeout_seconds == 3600
    )
    assert _settings(session_max_minutes=LIVE_SESSION_MAX_MINUTES_MAX).session_max_minutes == 240
    for bad in (LIVE_IDLE_TIMEOUT_SECONDS_MIN - 1, LIVE_IDLE_TIMEOUT_SECONDS_MAX + 1, -1):
        with pytest.raises(ValidationError):
            _settings(idle_timeout_seconds=bad)
    for bad in (-5, LIVE_SESSION_MAX_MINUTES_MAX + 1):
        with pytest.raises(ValidationError):
            _settings(session_max_minutes=bad)
    assert LIVE_IDLE_TIMEOUT_SECONDS_MIN == 5


def test_reading_a_model_falls_back_field_by_field_to_the_instance_defaults() -> None:
    parsed = read_model_settings(
        {"voice": "Kore", "idle_timeout_seconds": "soon", "session_max_minutes": 9999}
    )
    assert parsed is not None
    assert parsed.idle_timeout_seconds == settings.live_idle_timeout_seconds
    assert parsed.session_max_minutes == settings.live_session_max_minutes
    assert parsed.thinking_level is None
    assert read_model_settings({"voice": ""}) is None
    assert read_model_settings("garbage") is None
    kept = read_model_settings(
        {"voice": "Puck", "thinking_level": "high", "idle_timeout_seconds": 0}
    )
    assert kept is not None and kept.idle_timeout_seconds == 0 and kept.thinking_level == "high"


def test_the_legacy_top_level_shape_reads_as_the_current_models_settings() -> None:
    # Wave 1-2 metadata: {model, voice, thinking_level, functionally_verified}.
    models = read_models(
        {
            "model": "gemini-3.8-live",
            "voice": "Kore",
            "thinking_level": None,
            "functionally_verified": True,
        }
    )
    assert set(models) == {"gemini-3.8-live"}
    assert models["gemini-3.8-live"].voice == "Kore"
    assert models["gemini-3.8-live"].idle_timeout_seconds == settings.live_idle_timeout_seconds
    assert read_models(None) == {}
    assert read_models({"model": "m"}) == {}  # no voice: nothing to remember


def test_writing_remembers_every_model_and_drops_the_legacy_keys_in_a_new_dict() -> None:
    before = {
        "model": "gemini-3.8-live",
        "voice": "Kore",
        "thinking_level": None,
        "functionally_verified": True,
    }
    after = write_models(
        before,
        "gemini-3.8-live-extended-thinking",
        _settings(voice="Puck", thinking_level="high", idle_timeout_seconds=0),
    )
    assert after is not before and before == {
        "model": "gemini-3.8-live",
        "voice": "Kore",
        "thinking_level": None,
        "functionally_verified": True,
    }
    assert after["model"] == "gemini-3.8-live-extended-thinking"
    assert after["functionally_verified"] is True
    assert "voice" not in after and "thinking_level" not in after
    # The previous model's voice survives the switch: that is the persistence asked for.
    assert after["models"]["gemini-3.8-live"]["voice"] == "Kore"
    assert after["models"]["gemini-3.8-live-extended-thinking"] == {
        "voice": "Puck",
        "thinking_level": "high",
        "idle_timeout_seconds": 0,
        "session_max_minutes": 10,
    }
    # Switching back reads the remembered voice, not the first of the list.
    assert read_models(after)["gemini-3.8-live"].voice == "Kore"
