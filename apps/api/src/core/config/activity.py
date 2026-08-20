"""Activity timeline configuration module (Lot 1-A1).

Feature flag + window/caps for the read-only "what LIA did for you"
timeline (``domains/activity``). Defaults are imported from
``src.core.constants`` (NOT from the activity domain — importing the
domain here would wire its router and create a config↔domain circular
import, same doctrine as ``briefing.py``).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    ACTIVITY_TIMELINE_PAGE_SIZE_DEFAULT,
    ACTIVITY_TIMELINE_SOURCE_CAP_DEFAULT,
    ACTIVITY_TIMELINE_WINDOW_DAYS_DEFAULT,
)


class ActivitySettings(BaseSettings):
    """Env-overridable settings for the proactive activity timeline."""

    activity_timeline_enabled: bool = Field(
        default=True,
        description=(
            "Master switch of the activity timeline (router inclusion). "
            "Pure read feature: no scheduler, no LLM, no new table."
        ),
    )
    activity_timeline_window_days: int = Field(
        default=ACTIVITY_TIMELINE_WINDOW_DAYS_DEFAULT,
        ge=1,
        le=365,
        description="Look-back window (days) of the timeline aggregation.",
    )
    activity_timeline_source_cap: int = Field(
        default=ACTIVITY_TIMELINE_SOURCE_CAP_DEFAULT,
        ge=10,
        le=1000,
        description=(
            "Maximum rows fetched per source within the window. Exact totals "
            "come from COUNT(*); the cap only bounds the payload and is "
            "surfaced as an explicit truncated flag (ADR-185)."
        ),
    )
    activity_timeline_page_size: int = Field(
        default=ACTIVITY_TIMELINE_PAGE_SIZE_DEFAULT,
        ge=5,
        le=100,
        description="Default page size of the timeline API.",
    )
