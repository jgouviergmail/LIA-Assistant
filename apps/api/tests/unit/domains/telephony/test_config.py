"""Unit tests for TelephonySettings defaults (P1.1)."""

import pytest

from src.core.config import settings


@pytest.mark.unit
def test_telephony_settings_defaults():
    """The telephony feature flag is off and knobs carry their documented defaults."""
    assert settings.telephony_enabled is False
    assert settings.telephony_ringing_timeout_seconds == 30
    assert settings.telephony_prefetch_window_days == 10
    assert settings.telephony_max_call_duration_seconds == 600
    assert settings.telephony_call_retention_days == 30
    assert settings.telephony_stale_call_timeout_minutes == 15
    assert settings.telephony_rate_limit_per_hour == 10
