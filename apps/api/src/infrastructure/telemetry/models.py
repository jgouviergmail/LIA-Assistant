"""Typed results for telemetry reads (Prometheus, Loki, Alertmanager).

Doctrine: telemetry reading never raises on a caller's path. Every client
returns one of these models with ``status="unavailable"`` (and an ``error``
string) when the source is disabled, unreachable, failing or protected by an
open circuit breaker. Callers branch on ``status`` — never on exceptions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TelemetryStatus = Literal["ok", "unavailable"]


class PromSample(BaseModel):
    """One sample of a Prometheus instant-query vector result."""

    model_config = ConfigDict(frozen=True)

    metric: dict[str, str] = Field(description="Label set of the sample.")
    value: float = Field(description="Sample value.")
    ts: datetime = Field(description="Sample timestamp (aware UTC).")


class PromResult(BaseModel):
    """Result of a Prometheus instant query."""

    status: TelemetryStatus = Field(description="'ok' or 'unavailable' (source never raises).")
    samples: list[PromSample] = Field(default_factory=list, description="Vector samples.")
    error: str | None = Field(default=None, description="Failure reason when unavailable.")


class LokiLine(BaseModel):
    """One log line returned by a bounded LogQL range query."""

    model_config = ConfigDict(frozen=True)

    ts: datetime = Field(description="Log timestamp (aware UTC).")
    container: str = Field(default="", description="Container name from the stream labels.")
    level: str = Field(default="", description="Log level label of the stream.")
    payload: dict[str, object] | None = Field(
        default=None,
        description="Parsed structlog JSON payload, or None for non-JSON lines.",
    )
    raw: str = Field(description="The raw line as stored by Loki.")


class LokiResult(BaseModel):
    """Result of a bounded LogQL range query."""

    status: TelemetryStatus = Field(description="'ok' or 'unavailable' (source never raises).")
    lines: list[LokiLine] = Field(default_factory=list, description="Matched log lines.")
    error: str | None = Field(default=None, description="Failure reason when unavailable.")


class ActiveAlert(BaseModel):
    """One currently-firing alert as reported by Alertmanager."""

    model_config = ConfigDict(frozen=True)

    fingerprint: str = Field(description="Alertmanager's stable alert fingerprint.")
    name: str = Field(description="alertname label.")
    severity: str = Field(default="", description="severity label (may be absent).")
    component: str = Field(default="", description="component label (may be absent).")
    starts_at: str = Field(default="", description="RFC3339 start time as reported.")
    summary: str = Field(default="", description="summary annotation (may be absent).")
    description: str = Field(default="", description="description annotation (may be absent).")
    runbook: str = Field(default="", description="runbook annotation (may be absent).")


class AlertsResult(BaseModel):
    """Result of an Alertmanager active-alerts listing."""

    status: TelemetryStatus = Field(description="'ok' or 'unavailable' (source never raises).")
    alerts: list[ActiveAlert] = Field(default_factory=list, description="Firing alerts.")
    error: str | None = Field(default=None, description="Failure reason when unavailable.")
