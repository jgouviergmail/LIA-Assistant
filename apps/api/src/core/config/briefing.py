"""Today Briefing configuration module.

Per-widget content limits and scope windows for the Today briefing dashboard
(``domains/briefing``). Each is env-overridable so the briefing's richness can be
tuned in production without a code change (``BRIEFING_MAX_*``,
``BRIEFING_*_HOURS`` / ``BRIEFING_*_DAYS``).

Defaults are imported from ``src.core.constants`` (NOT from
``src.domains.briefing.constants``): importing the briefing domain here would
trigger its package ``__init__`` — which wires the router — and create a
config↔domain circular import.

Phase: evolution — Today Briefing tunability
Created: 2026-05-21
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    BRIEFING_AGENDA_LOOKAHEAD_HOURS_DEFAULT,
    BRIEFING_HEALTH_WINDOW_DAYS_DEFAULT,
    BRIEFING_MAX_AGENDA_ITEMS_DEFAULT,
    BRIEFING_MAX_BIRTHDAYS_HORIZON_DAYS_DEFAULT,
    BRIEFING_MAX_BIRTHDAYS_ITEMS_DEFAULT,
    BRIEFING_MAX_DOCUMENTS_ITEMS_DEFAULT,
    BRIEFING_MAX_MAILS_ITEMS_DEFAULT,
    BRIEFING_MAX_OPEN_LOOPS_ITEMS_DEFAULT,
    BRIEFING_MAX_REMINDERS_ITEMS_DEFAULT,
    BRIEFING_MAX_TASKS_ITEMS_DEFAULT,
    BRIEFING_TASKS_HORIZON_DAYS_DEFAULT,
    BRIEFING_WEATHER_DAILY_FORECAST_DAYS_DEFAULT,
)


class BriefingSettings(BaseSettings):
    """Env-overridable content limits for the Today briefing widgets."""

    briefing_max_agenda_items: int = Field(
        default=BRIEFING_MAX_AGENDA_ITEMS_DEFAULT,
        ge=1,
        le=50,
        description=(
            "Maximum calendar events shown on the agenda card, within the "
            "lookahead window. Default 10."
        ),
    )
    briefing_agenda_lookahead_hours: int = Field(
        default=BRIEFING_AGENDA_LOOKAHEAD_HOURS_DEFAULT,
        ge=1,
        le=168,
        description=(
            "Forward window (hours from now) scanned for agenda events. "
            "Default 24h (today + tomorrow morning). Up to 168h (7 days)."
        ),
    )
    briefing_max_mails_items: int = Field(
        default=BRIEFING_MAX_MAILS_ITEMS_DEFAULT,
        ge=1,
        le=50,
        description="Maximum emails shown on the mails card. Default 5.",
    )
    briefing_max_birthdays_items: int = Field(
        default=BRIEFING_MAX_BIRTHDAYS_ITEMS_DEFAULT,
        ge=1,
        le=50,
        description="Maximum upcoming birthdays shown on the birthdays card. Default 5.",
    )
    briefing_max_birthdays_horizon_days: int = Field(
        default=BRIEFING_MAX_BIRTHDAYS_HORIZON_DAYS_DEFAULT,
        ge=1,
        le=365,
        description="Forward window (days) for upcoming birthdays. Default 14.",
    )
    briefing_max_reminders_items: int = Field(
        default=BRIEFING_MAX_REMINDERS_ITEMS_DEFAULT,
        ge=1,
        le=50,
        description="Maximum pending reminders shown on the reminders card. Default 5.",
    )
    briefing_health_window_days: int = Field(
        default=BRIEFING_HEALTH_WINDOW_DAYS_DEFAULT,
        ge=1,
        le=90,
        description="Rolling window (days) for the health card per-kind averages. Default 14.",
    )
    briefing_weather_daily_forecast_days: int = Field(
        default=BRIEFING_WEATHER_DAILY_FORECAST_DAYS_DEFAULT,
        ge=1,
        le=5,
        description=(
            "Number of forecast days shown on the weather card. Default 5 "
            "(capped at 5 — the OpenWeatherMap free tier maximum)."
        ),
    )
    briefing_max_open_loops_items: int = Field(
        default=BRIEFING_MAX_OPEN_LOOPS_ITEMS_DEFAULT,
        ge=1,
        le=10,
        description="Max open loops surfaced on the For-you briefing card.",
    )
    briefing_max_tasks_items: int = Field(
        default=BRIEFING_MAX_TASKS_ITEMS_DEFAULT,
        ge=1,
        le=20,
        description="Max pending/overdue tasks on the tasks card.",
    )
    briefing_tasks_horizon_days: int = Field(
        default=BRIEFING_TASKS_HORIZON_DAYS_DEFAULT,
        ge=1,
        le=30,
        description="Tasks card look-ahead window (overdue + due within N days).",
    )
    briefing_max_documents_items: int = Field(
        default=BRIEFING_MAX_DOCUMENTS_ITEMS_DEFAULT,
        ge=1,
        le=20,
        description="Max recently-modified Drive files on the documents card.",
    )
