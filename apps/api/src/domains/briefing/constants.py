"""Briefing domain constants — TTLs, item limits, cache prefix, error codes.

Single source of truth for every magic value used by the briefing service,
fetchers, and LLM helpers. Adjusting cache TTL or item limits is a one-line
edit here.
"""

from typing import Final, Literal

# =============================================================================
# Cache TTLs (seconds) — match the natural change rate of each source.
# =============================================================================

BRIEFING_CACHE_PREFIX = "briefing"

SECTION_WEATHER_TTL_SECONDS = 3600  # 1 h — slow variations + free-tier API
SECTION_AGENDA_TTL_SECONDS = 600  # 10 min — occasional event edits
SECTION_MAILS_TTL_SECONDS = 300  # 5 min — important but Gmail-quota friendly
SECTION_BIRTHDAYS_TTL_SECONDS = 604800  # 7 days — quasi-static, full contacts scan is costly
SECTION_REMINDERS_TTL_SECONDS = 0  # Live (local DB, < 10 ms)
SECTION_HEALTH_TTL_SECONDS = 900  # 15 min — Shortcuts ingest cadence

# Health metrics rolling window for the dashboard card (per-kind daily average).
BRIEFING_HEALTH_WINDOW_DAYS = 14

# =============================================================================
# Item limits per section (UI-facing budgets — keep cards scannable).
# =============================================================================

BRIEFING_MAX_AGENDA_ITEMS = 3
BRIEFING_MAX_MAILS_ITEMS = 5
BRIEFING_MAX_BIRTHDAYS_ITEMS = 5
BRIEFING_MAX_BIRTHDAYS_HORIZON_DAYS = 14
BRIEFING_MAX_REMINDERS_ITEMS = 5

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
BRIEFING_BIRTHDAY_PAGE_SIZE = 1000  # People API native max
BRIEFING_BIRTHDAY_PAGINATION_MAX_PAGES = 5  # 5 × 1000 = 5000 contacts (more than any address book)

# Calendar fetch window (hours forward from now) — covers today + tomorrow morning.
BRIEFING_AGENDA_LOOKAHEAD_HOURS = 24

# Forecast 3-h slots fetched from OpenWeatherMap.
# 40 slots × 3 h = 120 h = 5 days (the free-tier maximum).
# Used both to detect short-term alerts AND to aggregate the 5-day forecast.
BRIEFING_WEATHER_FORECAST_CNT = 40

# Daily forecast horizon shown on the weather card (rolling next N days).
BRIEFING_WEATHER_DAILY_FORECAST_DAYS = 5

# =============================================================================
# Section names (Literal alignment for RefreshRequest schema).
# =============================================================================

SECTION_WEATHER = "weather"
SECTION_AGENDA = "agenda"
SECTION_MAILS = "mails"
SECTION_BIRTHDAYS = "birthdays"
SECTION_REMINDERS = "reminders"
SECTION_HEALTH = "health"

SECTION_NAMES: tuple[str, ...] = (
    SECTION_WEATHER,
    SECTION_AGENDA,
    SECTION_MAILS,
    SECTION_BIRTHDAYS,
    SECTION_REMINDERS,
    SECTION_HEALTH,
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
