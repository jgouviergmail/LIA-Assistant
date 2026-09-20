"""Live settings (ADR-299): the deployment ceiling and every bound the client is told."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.config.live import LiveSettings
from src.core.constants import (
    LIVE_DELEGATION_RESULT_MAX_TOKENS_DEFAULT,
    LIVE_EXTENSION_MINUTES_DEFAULT,
    LIVE_EXTENSION_PROMPT_SECONDS_DEFAULT,
    LIVE_IDLE_TIMEOUT_SECONDS_DEFAULT,
    LIVE_SESSION_MAX_MINUTES_DEFAULT,
)

pytestmark = pytest.mark.unit


def test_live_is_off_by_default() -> None:
    assert settings.live_enabled is False


def test_bounds_read_their_constants() -> None:
    assert settings.live_session_max_minutes == LIVE_SESSION_MAX_MINUTES_DEFAULT
    assert settings.live_delegation_result_max_tokens == LIVE_DELEGATION_RESULT_MAX_TOKENS_DEFAULT
    assert settings.live_extension_minutes == LIVE_EXTENSION_MINUTES_DEFAULT
    assert settings.live_extension_prompt_seconds == LIVE_EXTENSION_PROMPT_SECONDS_DEFAULT


def test_the_owner_arbitrated_a_ten_minute_cap_and_a_minute_of_silence() -> None:
    # 2026-09-19: a provider that bills the session's duration (GPT-Live)
    # tolls while nobody speaks; the DEFAULT cap is short and explicitly
    # extended, the default silence a minute — each model of a connector
    # keeps its own, 0 meaning unlimited (the person knows the billing).
    assert LIVE_SESSION_MAX_MINUTES_DEFAULT == 10
    assert LIVE_IDLE_TIMEOUT_SECONDS_DEFAULT == 60
    assert LIVE_EXTENSION_MINUTES_DEFAULT == 10


def test_the_extension_prompt_must_fall_inside_the_cap() -> None:
    # A prompt at or beyond the cap would ask the question after the session
    # ended: refused at boot, like the sibling settings validators.
    with pytest.raises(ValidationError):
        LiveSettings(live_session_max_minutes=1, live_extension_prompt_seconds=60)
    assert LiveSettings(live_session_max_minutes=2, live_extension_prompt_seconds=60)
