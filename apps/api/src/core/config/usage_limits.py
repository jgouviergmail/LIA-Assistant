"""
Usage limits configuration module.

Contains settings for the per-user usage limits feature:
- Feature toggle (usage_limits_enabled)
- Default limits applied at user creation (tokens, messages, cost)
- Cache TTL for Redis-based limit checks

Phase: evolution — Per-User Usage Limits
Created: 2026-03-21
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    DEFAULT_COST_LIMIT_ABSOLUTE_EUR,
    DEFAULT_COST_LIMIT_PER_CYCLE_EUR,
    DEFAULT_MESSAGE_LIMIT_ABSOLUTE,
    DEFAULT_MESSAGE_LIMIT_PER_CYCLE,
    DEFAULT_TOKEN_LIMIT_ABSOLUTE,
    DEFAULT_TOKEN_LIMIT_PER_CYCLE,
    USAGE_LIMIT_CACHE_TTL_SECONDS_DEFAULT,
    USAGE_LIMITS_ENABLED_DEFAULT,
)


def _empty_str_to_none(v: Any) -> Any:
    """Convert empty strings to None for optional numeric env vars.

    Environment variables with empty values (VAR=) are read as "" by pydantic-settings.
    Since these fields accept int | None or float | None, we convert "" to None
    so Pydantic doesn't fail parsing an empty string as a number.

    Args:
        v: Raw value from environment.

    Returns:
        None if empty string, otherwise original value.
    """
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


# Type aliases with BeforeValidator for empty-string-to-None conversion
OptionalInt = Annotated[int | None, BeforeValidator(_empty_str_to_none)]
OptionalFloat = Annotated[float | None, BeforeValidator(_empty_str_to_none)]


class UsageLimitsSettings(BaseSettings):
    """Settings for the per-user usage limits feature."""

    # ========================================================================
    # Feature Toggle
    # ========================================================================

    usage_limits_enabled: bool = Field(
        default=USAGE_LIMITS_ENABLED_DEFAULT,
        description=(
            "Global feature flag for usage limits enforcement. "
            "When false, no usage limit checks are performed and the router is not registered."
        ),
    )

    # ========================================================================
    # Default Limits (applied at user creation)
    # ========================================================================

    default_token_limit_per_cycle: OptionalInt = Field(
        default=DEFAULT_TOKEN_LIMIT_PER_CYCLE,
        description=(
            "Default token limit (prompt + completion combined) per billing cycle "
            "for new users. None = unlimited."
        ),
    )

    default_message_limit_per_cycle: OptionalInt = Field(
        default=DEFAULT_MESSAGE_LIMIT_PER_CYCLE,
        description=(
            "Default user message limit per billing cycle for new users. None = unlimited."
        ),
    )

    default_cost_limit_per_cycle_eur: OptionalFloat = Field(
        default=DEFAULT_COST_LIMIT_PER_CYCLE_EUR,
        description=("Default cost limit (EUR) per billing cycle for new users. None = unlimited."),
    )

    default_token_limit_absolute: OptionalInt = Field(
        default=DEFAULT_TOKEN_LIMIT_ABSOLUTE,
        description=("Default absolute (lifetime) token limit for new users. None = unlimited."),
    )

    default_message_limit_absolute: OptionalInt = Field(
        default=DEFAULT_MESSAGE_LIMIT_ABSOLUTE,
        description=("Default absolute (lifetime) message limit for new users. None = unlimited."),
    )

    default_cost_limit_absolute_eur: OptionalFloat = Field(
        default=DEFAULT_COST_LIMIT_ABSOLUTE_EUR,
        description=(
            "Default absolute (lifetime) cost limit (EUR) for new users. None = unlimited."
        ),
    )

    # ========================================================================
    # Cache Configuration
    # ========================================================================

    usage_limit_cache_ttl_seconds: int = Field(
        default=USAGE_LIMIT_CACHE_TTL_SECONDS_DEFAULT,
        ge=5,
        le=300,
        description=(
            "Redis cache TTL (seconds) for usage limit check results. "
            "Lower values = more accurate enforcement, higher values = less DB load."
        ),
    )
