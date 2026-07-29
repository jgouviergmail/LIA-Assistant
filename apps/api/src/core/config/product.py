"""Product analytics configuration module (ADR-178).

Feature flag + tunables for the product outcomes pipeline: durable
``product_outcomes`` / ``product_events`` recording, the E2 behavioral
validation window, raw-row retention (signed-off decision #6: 180 days,
aggregates unlimited) and the hourly rollup cadence.

Defaults are imported from ``src.core.constants`` (never from the product
domain — importing a domain here would create a config↔domain cycle).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    PRODUCT_E2_VALIDATION_WINDOW_HOURS_DEFAULT,
    PRODUCT_OUTCOMES_RETENTION_DAYS_DEFAULT,
    PRODUCT_ROLLUP_INTERVAL_MINUTES_DEFAULT,
)


class ProductSettings(BaseSettings):
    """Env-overridable settings for product analytics (``PRODUCT_*``)."""

    product_analytics_enabled: bool = Field(
        default=False,
        description=(
            "Master switch for product outcome recording and the rollup job. "
            "Off by default: enabling is an explicit deployment decision "
            "(dashboard 26 renders n/a without it)."
        ),
    )
    product_outcomes_retention_days: int = Field(
        default=PRODUCT_OUTCOMES_RETENTION_DAYS_DEFAULT,
        ge=7,
        le=3650,
        description=(
            "Raw product_outcomes/product_events retention in days (decision "
            "#6: 180). Daily aggregates are kept forever. The purge runs in "
            "the hourly rollup job."
        ),
    )
    product_e2_validation_window_hours: int = Field(
        default=PRODUCT_E2_VALIDATION_WINDOW_HOURS_DEFAULT,
        ge=1,
        le=168,
        description=(
            "Behavioral validation window: an uncorrected, unreverted action "
            "outcome older than this is promoted to E2 (spec counting rule "
            "'at least 24 h without correction/reversion')."
        ),
    )
    product_rollup_interval_minutes: int = Field(
        default=PRODUCT_ROLLUP_INTERVAL_MINUTES_DEFAULT,
        ge=5,
        le=1440,
        description=(
            "Rollup job cadence (cost backfill, E2 upgrades, purge, gauge "
            "refresh). Must stay comfortably under the 2 h freshness SLA."
        ),
    )
