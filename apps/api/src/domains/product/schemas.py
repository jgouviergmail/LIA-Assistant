"""Request schemas for the product telemetry ingestion endpoint (Phase 4).

Everything is enum-bounded by construction — no free text ever reaches the
database or a Prometheus label. Three item kinds share one polymorphic shape:
funnel events (DB rows), search telemetry and Web Vitals (Prometheus only).
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.domains.product.constants import (
    CLIENT_EVENT_TYPES,
    SEARCH_OUTCOMES,
    SEARCH_SURFACES,
    WEB_VITAL_RATIO_METRICS,
    WEB_VITAL_SECONDS_METRICS,
)

MAX_EVENTS_PER_BATCH = 20


class ClientEventItem(BaseModel):
    """One telemetry item — exactly one of the three bounded kinds.

    Attributes:
        kind: Item discriminator (funnel event, search, web vital).
        event_type: Bounded ``CLIENT_EVENT_TYPES`` value (kind=event).
        surface: Bounded search surface (kind=search).
        outcome: Bounded search outcome (kind=search).
        metric: Bounded Web Vital name (kind=vital).
        value: Web Vital measurement (kind=vital) — seconds for LCP,
            unitless for CLS; capped to reject garbage.
    """

    kind: Literal["event", "search", "vital"] = Field(
        description="Item discriminator: funnel event, search telemetry or Web Vital."
    )
    event_type: str | None = Field(
        default=None, description="Bounded client event type (kind=event)."
    )
    surface: str | None = Field(default=None, description="Bounded search surface (kind=search).")
    outcome: str | None = Field(default=None, description="Bounded search outcome (kind=search).")
    metric: str | None = Field(default=None, description="Bounded Web Vital metric (kind=vital).")
    value: float | None = Field(
        default=None,
        ge=0,
        le=120,
        description="Web Vital value (kind=vital) — seconds (LCP) or ratio (CLS).",
    )

    @field_validator("event_type")
    @classmethod
    def _bounded_event_type(cls, v: str | None) -> str | None:
        if v is not None and v not in {e.value for e in CLIENT_EVENT_TYPES}:
            raise ValueError(f"unknown event_type '{v}'")
        return v

    @field_validator("surface")
    @classmethod
    def _bounded_surface(cls, v: str | None) -> str | None:
        if v is not None and v not in SEARCH_SURFACES:
            raise ValueError(f"unknown surface '{v}'")
        return v

    @field_validator("outcome")
    @classmethod
    def _bounded_outcome(cls, v: str | None) -> str | None:
        if v is not None and v not in SEARCH_OUTCOMES:
            raise ValueError(f"unknown outcome '{v}'")
        return v

    @field_validator("metric")
    @classmethod
    def _bounded_metric(cls, v: str | None) -> str | None:
        if v is not None and v not in (WEB_VITAL_SECONDS_METRICS | WEB_VITAL_RATIO_METRICS):
            raise ValueError(f"unknown metric '{v}'")
        return v


class ClientEventBatch(BaseModel):
    """Batch envelope for the ingestion endpoint.

    Attributes:
        events: Bounded telemetry items (at most ``MAX_EVENTS_PER_BATCH``).
    """

    events: list[ClientEventItem] = Field(
        min_length=1,
        max_length=MAX_EVENTS_PER_BATCH,
        description="Telemetry items — enum-bounded, never free text.",
    )


class ClientEventAck(BaseModel):
    """Ingestion acknowledgement.

    Attributes:
        accepted: Number of items accepted.
        dropped: Number of items dropped (unauthorized kind for anonymous
            callers, or incomplete items) — dropping is silent by design,
            telemetry must never surface errors to the UX.
    """

    accepted: int = Field(description="Items accepted.")
    dropped: int = Field(description="Items silently dropped.")
