"""Effective Live configuration shared by UI and native settings readers."""

from src.core.config import settings
from src.core.constants import (
    LIVE_DELEGATION_TOOL_NAME,
    LIVE_DURATION_UNLIMITED,
    LIVE_IDLE_TIMEOUT_SECONDS_MAX,
    LIVE_IDLE_TIMEOUT_SECONDS_MIN,
    LIVE_SESSION_BUDGET_EUR_MAX,
    LIVE_SESSION_MAX_MINUTES_MAX,
    LIVE_SESSION_MAX_MINUTES_MIN,
    LIVE_TURN_TEXT_MAX_CHARS,
)
from src.domains.live.direct_mandate import browser_lines
from src.domains.live.mandate import bridge_lines, tone_lines
from src.domains.live.schemas import LiveConfigResponse, LiveDurationBounds


def effective_live_configuration() -> LiveConfigResponse:
    return LiveConfigResponse(
        session_max_minutes=settings.live_session_max_minutes,
        session_max_bounds=LiveDurationBounds(
            min=LIVE_SESSION_MAX_MINUTES_MIN, max=LIVE_SESSION_MAX_MINUTES_MAX
        ),
        idle_timeout_bounds=LiveDurationBounds(
            min=LIVE_IDLE_TIMEOUT_SECONDS_MIN, max=LIVE_IDLE_TIMEOUT_SECONDS_MAX
        ),
        session_budget_eur_max=LIVE_SESSION_BUDGET_EUR_MAX,
        unlimited_value=LIVE_DURATION_UNLIMITED,
        extension_minutes=settings.live_extension_minutes,
        extension_prompt_seconds=settings.live_extension_prompt_seconds,
        connect_window_seconds=settings.live_connect_window_seconds,
        idle_timeout_seconds=settings.live_idle_timeout_seconds,
        hidden_grace_seconds=settings.live_hidden_grace_seconds,
        standby_max_seconds=settings.live_standby_max_seconds,
        delegation_timeout_seconds=settings.live_delegation_timeout_seconds,
        delegation_result_max_tokens=settings.live_delegation_result_max_tokens,
        delegation_tool_name=LIVE_DELEGATION_TOOL_NAME,
        turn_text_max_chars=LIVE_TURN_TEXT_MAX_CHARS,
        delegation_lines=bridge_lines(),
        direct_lines=browser_lines(),
        tone_lines=tone_lines(),
    )
