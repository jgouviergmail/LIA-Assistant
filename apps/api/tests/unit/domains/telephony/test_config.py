"""Unit tests for TelephonySettings defaults (P1.1)."""

import pytest

from src.core.config import settings


@pytest.mark.unit
def test_telephony_settings_defaults():
    """The telephony feature flag is off and knobs carry their documented defaults."""
    assert settings.telephony_enabled is False
    assert settings.telephony_ringing_timeout_seconds == 30
    assert settings.telephony_prefetch_window_days == 10
    assert settings.telephony_call_retention_days == 30
    assert settings.telephony_stale_call_timeout_minutes == 15
    assert settings.telephony_rate_limit_per_hour == 10


@pytest.mark.unit
def test_no_setting_pins_the_voice_agent_llm() -> None:
    """The model behind the voice agent is configured on the ElevenLabs portal,
    for the agent (owner decision 2026-09-16, after a portal-chosen model and a
    pinned one collided on every sync). No setting may reintroduce a pin."""
    names = set(type(settings).model_fields)
    assert not {n for n in names if n.startswith("telephony_agent_") and "llm" in n}
    assert "telephony_agent_reasoning_effort" not in names


@pytest.mark.unit
def test_no_setting_administers_what_the_portal_owns() -> None:
    """The language, the voice, the audio format and the duration caps are
    administered on the ElevenLabs portal — changing them there needs no
    restart (owner decision 2026-09-16). No setting may bring them back."""
    names = set(type(settings).model_fields)
    for gone in (
        "telephony_agent_tts_model_id",
        "telephony_agent_voice_id",
        "telephony_agent_audio_format",
        "telephony_max_call_duration_seconds",
        "telephony_self_call_max_duration_seconds",
        "telephony_verification_call_max_duration_seconds",
    ):
        assert gone not in names, gone
