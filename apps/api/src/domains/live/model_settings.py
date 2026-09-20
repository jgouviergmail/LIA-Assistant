"""What the person set for ONE model of a live connector, and how the metadata holds it.

Every model of a provider keeps its own voice, thinking level and two
durations (owner decision 2026-09-19): the silence after which the session
closes and the longest session before the extension dialog — both
``0`` for « unlimited », because a provider may bill the whole session
(per second, waiting included) or only the interactions, and the person
alone knows the model's billing. The choices are stored on the connector's
JSONB as ``{"model": current, "models": {name: {...}}}``; a connector written
by the first two waves holds ``voice`` / ``thinking_level`` at the top level
and is READ as one model's settings (never migrated in place — a NEW dict is
written on the next save, the JSONB rule). A stored value nobody can read
falls back to the instance default, never to a 500 on the settings page.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.core.config import settings
from src.core.constants import (
    LIVE_DURATION_UNLIMITED,
    LIVE_IDLE_TIMEOUT_SECONDS_MAX,
    LIVE_IDLE_TIMEOUT_SECONDS_MIN,
    LIVE_SESSION_BUDGET_EUR_MAX,
    LIVE_SESSION_MAX_MINUTES_MAX,
    LIVE_SESSION_MAX_MINUTES_MIN,
)


def _within_or_unlimited(value: int, low: int, high: int, name: str) -> int:
    if value == LIVE_DURATION_UNLIMITED or low <= value <= high:
        return value
    raise ValueError(
        f"{name} must be {LIVE_DURATION_UNLIMITED} (unlimited) or between {low} and {high}"
    )


class LiveModelSettings(BaseModel):
    """One model's choices: its voice, its thinking level, its two durations."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    voice: str = Field(
        ..., min_length=1, max_length=64, description="A name of the provider's published list."
    )
    thinking_level: str | None = Field(
        None, max_length=16, description="A level of the model's ADR-245 ladder, or none."
    )
    idle_timeout_seconds: int = Field(
        ...,
        description=(
            "Silence (nobody speaks, no delegation, no processing) after which the client "
            f"ends the session; {LIVE_DURATION_UNLIMITED} = never."
        ),
    )
    session_max_minutes: int = Field(
        ...,
        description=(
            "Longest session before the extension is offered; "
            f"{LIVE_DURATION_UNLIMITED} = unlimited (the cap rolls on without asking)."
        ),
    )

    @field_validator("idle_timeout_seconds")
    @classmethod
    def _idle_bounds(cls, value: int) -> int:
        return _within_or_unlimited(
            value,
            LIVE_IDLE_TIMEOUT_SECONDS_MIN,
            LIVE_IDLE_TIMEOUT_SECONDS_MAX,
            "idle_timeout_seconds",
        )

    @field_validator("session_max_minutes")
    @classmethod
    def _max_bounds(cls, value: int) -> int:
        return _within_or_unlimited(
            value, LIVE_SESSION_MAX_MINUTES_MIN, LIVE_SESSION_MAX_MINUTES_MAX, "session_max_minutes"
        )


def default_durations() -> dict[str, int]:
    """The instance defaults a model without stored durations runs under."""
    return {
        "idle_timeout_seconds": settings.live_idle_timeout_seconds,
        "session_max_minutes": settings.live_session_max_minutes,
    }


def read_model_settings(raw: object) -> LiveModelSettings | None:
    """One model's settings as the metadata holds them, field by field, or None without a voice.

    A duration nobody can read (absent, a string, out of bounds) is the
    instance default; an unreadable thinking level is none.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("voice"), str) or not raw["voice"]:
        return None
    kept: dict[str, Any] = {"voice": raw["voice"], **default_durations()}
    for name in ("thinking_level", "idle_timeout_seconds", "session_max_minutes"):
        candidate = raw.get(name)
        if candidate is None:
            continue
        try:
            LiveModelSettings.model_validate({**kept, name: candidate})
        except ValidationError:
            continue
        kept[name] = candidate
    return LiveModelSettings.model_validate(kept)


def read_models(metadata: dict[str, Any] | None) -> dict[str, LiveModelSettings]:
    """Every model the connector remembers, the legacy top-level shape included."""
    metadata = metadata or {}
    models: dict[str, LiveModelSettings] = {}
    stored = metadata.get("models")
    if isinstance(stored, dict):
        for name, raw in stored.items():
            parsed = read_model_settings(raw)
            if isinstance(name, str) and name and parsed is not None:
                models[name] = parsed
    # The first two waves wrote the current model's voice and level at the top level.
    current = metadata.get("model")
    if isinstance(current, str) and current and current not in models:
        legacy = read_model_settings(
            {"voice": metadata.get("voice"), "thinking_level": metadata.get("thinking_level")}
        )
        if legacy is not None:
            models[current] = legacy
    return models


def write_models(
    metadata: dict[str, Any] | None, model: str, chosen: LiveModelSettings
) -> dict[str, Any]:
    """A NEW metadata dict with ``model`` current and its settings remembered (the JSONB rule).

    The legacy top-level keys are dropped: one shape, read tolerantly, written once.
    """
    models = {name: value.model_dump() for name, value in read_models(metadata).items()}
    models[model] = chosen.model_dump()
    kept = {
        k: v
        for k, v in (metadata or {}).items()
        if k not in {"voice", "thinking_level", "models", "model"}
    }
    return {**kept, "model": model, "models": models}


#: The connector-level spend ceiling's key in the metadata (ADR-300 wave 3).
BUDGET_KEY = "session_budget_eur"


def read_session_budget(metadata: dict[str, Any] | None) -> float | None:
    """The connector's per-session spend ceiling, or None (absent, unreadable, off the bound)."""
    raw = (metadata or {}).get(BUDGET_KEY)
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    value = float(raw)
    return value if 0 < value <= LIVE_SESSION_BUDGET_EUR_MAX else None


def write_session_budget(metadata: dict[str, Any], budget: float | None) -> dict[str, Any]:
    """A NEW metadata dict carrying the ceiling, or none of it (the JSONB rule)."""
    kept = {k: v for k, v in metadata.items() if k != BUDGET_KEY}
    return kept if budget is None else {**kept, BUDGET_KEY: budget}


__all__ = [
    "BUDGET_KEY",
    "LiveModelSettings",
    "default_durations",
    "read_model_settings",
    "read_models",
    "read_session_budget",
    "write_models",
    "write_session_budget",
]
