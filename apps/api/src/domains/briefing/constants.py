"""Briefing domain constants — TTLs, item limits, cache prefix, error codes.

Single source of truth for every magic value used by the briefing service,
fetchers, and LLM helpers. Adjusting cache TTL or item limits is a one-line
edit here.
"""

from typing import Final, Literal

# =============================================================================
# Cache TTLs (seconds) — match the natural change rate of each source.
# =============================================================================

# Bumped to v2 when WeatherData.forecast_alert switched from str to a
# structured object — old cached payloads would otherwise raise a Pydantic
# ValidationError on read until their TTL elapses.
BRIEFING_CACHE_PREFIX = "briefing:v2"

SECTION_WEATHER_TTL_SECONDS = 3600  # 1 h — slow variations + free-tier API
SECTION_AGENDA_TTL_SECONDS = 600  # 10 min — occasional event edits
SECTION_MAILS_TTL_SECONDS = 300  # 5 min — important but Gmail-quota friendly
SECTION_BIRTHDAYS_TTL_SECONDS = 604800  # 7 days — quasi-static, full contacts scan is costly
SECTION_REMINDERS_TTL_SECONDS = 0  # Live (local DB, < 10 ms)
SECTION_HEALTH_TTL_SECONDS = 900  # 15 min — Shortcuts ingest cadence
SECTION_FOR_YOU_TTL_SECONDS = 300  # 5 min — open loops / automation runs move
SECTION_TASKS_TTL_SECONDS = 600  # 10 min — same natural change rate as agenda
SECTION_DOCUMENTS_TTL_SECONDS = 600  # 10 min — Drive activity cadence

# =============================================================================
# Per-widget content limits (agenda/mails/birthdays/reminders item caps, agenda
# lookahead, birthdays horizon, health window, weather forecast days) are
# env-overridable: their defaults live in src/core/constants.py
# (``BRIEFING_*_DEFAULT``) and are exposed via ``BriefingSettings``. Read them
# through ``settings.briefing_*`` — never inline constants here — so env
# overrides take effect. (They live in core, not this domain module, to avoid a
# config↔briefing-domain circular import.)
# =============================================================================

# Birthday lookup pagination.
#
# We bypass the global `api_max_items_per_request` security cap (max 50) to
# query the People API at its native limit of 1000 contacts per page. Without
# this bypass, scanning 1500 contacts would require 30+ paginated calls —
# unacceptable cold-cache latency for a briefing endpoint.
#
# Direct call uses `client._make_request("GET", "/people/me/connections", ...)`
# which skips `apply_max_items_limit`. Justified because:
#  - Source is the user's own contacts list (no privacy escalation)
#  - Cache TTL is 7 days (rebuilt on demand via force refresh)
#  - The per-card briefing TTL bounds the API call frequency anyway
# Birthday pagination constants moved to src/domains/connectors/birthdays.py (P7).

# Forecast 3-h slots fetched from OpenWeatherMap.
# 40 slots × 3 h = 120 h = 5 days (the free-tier maximum).
# Used both to detect short-term alerts AND to aggregate the 5-day forecast.
BRIEFING_WEATHER_FORECAST_CNT = 40

# =============================================================================
# Section names (Literal alignment for RefreshRequest schema).
# =============================================================================

SECTION_WEATHER = "weather"
SECTION_AGENDA = "agenda"
SECTION_MAILS = "mails"
SECTION_BIRTHDAYS = "birthdays"
SECTION_REMINDERS = "reminders"
SECTION_HEALTH = "health"
SECTION_FOR_YOU = "for_you"
SECTION_TASKS = "tasks"
SECTION_DOCUMENTS = "documents"

SECTION_NAMES: tuple[str, ...] = (
    SECTION_WEATHER,
    SECTION_AGENDA,
    SECTION_MAILS,
    SECTION_BIRTHDAYS,
    SECTION_REMINDERS,
    SECTION_HEALTH,
    SECTION_FOR_YOU,
    SECTION_TASKS,
    SECTION_DOCUMENTS,
)

# =============================================================================
# LLM prompt names (must match files in agents/prompts/v1/) and tracking labels.
# =============================================================================

BRIEFING_GREETING_PROMPT_NAME = "briefing_greeting_prompt"
BRIEFING_SYNTHESIS_PROMPT_NAME = "briefing_synthesis_prompt"

# Slot in LLM_TYPES_REGISTRY / LLM_DEFAULTS (see llm_config/constants.py).
# Annotated as Literal["briefing"] so callers like get_llm() (which expects
# the LLMType Literal) accept it without an explicit cast.
BRIEFING_LLM_TYPE: Final[Literal["briefing"]] = "briefing"

# Synthesis is generated only if at least N cards have actual data
# (avoids empty/forced LLM noise on a near-empty dashboard).
BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA = 2

# Token tracking labels (consumed by track_proactive_tokens for analytics dedup).
BRIEFING_TASK_TYPE = "briefing"
BRIEFING_GREETING_TARGET_PREFIX = "greeting"
BRIEFING_SYNTHESIS_TARGET_PREFIX = "synthesis"

# =============================================================================
# Error codes (stable identifiers — frontend uses these to pick localized CTAs).
# =============================================================================

ERROR_CODE_CONNECTOR_NOT_CONFIGURED = "connector_not_configured"
ERROR_CODE_CONNECTOR_OAUTH_EXPIRED = "connector_oauth_expired"
ERROR_CODE_CONNECTOR_NETWORK = "connector_network"
ERROR_CODE_CONNECTOR_RATE_LIMIT = "connector_rate_limit"
ERROR_CODE_INTERNAL = "internal"

# =============================================================================
# Time-of-day buckets (for prompt context — labels match the prompt placeholders).
# =============================================================================

TIME_OF_DAY_NIGHT = "night"
TIME_OF_DAY_MORNING = "morning"
TIME_OF_DAY_AFTERNOON = "afternoon"
TIME_OF_DAY_EVENING = "evening"
