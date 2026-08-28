"""Pydantic schemas of the diagnostics domain (webhook payload + admin DTOs)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.diagnostics.checks import unit_for


class WebhookAlert(BaseModel):
    """One alert entry of an Alertmanager webhook payload (v4)."""

    model_config = ConfigDict(extra="ignore")

    status: str = Field(description="'firing' or 'resolved'.")
    labels: dict[str, str] = Field(default_factory=dict, description="Alert labels.")
    annotations: dict[str, str] = Field(default_factory=dict, description="Alert annotations.")
    fingerprint: str = Field(default="", description="Alertmanager's stable fingerprint.")


class AlertmanagerWebhookPayload(BaseModel):
    """Alertmanager webhook body (version 4)."""

    model_config = ConfigDict(extra="ignore")

    version: str = Field(default="4", description="Webhook payload version.")
    status: str = Field(description="Group status: 'firing' or 'resolved'.")
    alerts: list[WebhookAlert] = Field(description="Individual alerts of the group.")


class WebhookOutcome(BaseModel):
    """What the webhook did with the payload (exact counts)."""

    opened: int = Field(description="Incidents newly opened by this delivery.")
    resolved: int = Field(description="Incidents resolved by this delivery.")


class CheckResultOut(BaseModel):
    """One check result as stored in a snapshot."""

    model_config = ConfigDict(extra="ignore")

    check_id: str = Field(description="Check identifier.")
    status: str = Field(description="ok/degraded/critical/unknown.")
    value: float | None = Field(default=None, description="Exact measured value.")
    unit: str = Field(
        default="",
        description=(
            "Unit of `value`, resolved from the check registry. Published so the "
            "client never infers it from the identifier (ADR-184)."
        ),
    )
    detail: str = Field(default="", description="Failure reason or context.")
    alertname: str | None = Field(default=None, description="Mirrored alertname, if any.")

    @model_validator(mode="after")
    def _resolve_unit_from_the_registry(self) -> CheckResultOut:
        """Fill the unit from the registry, including for rows stored without it."""
        if not self.unit:
            self.unit = unit_for(self.check_id)
        return self


class SnapshotOut(BaseModel):
    """One health snapshot."""

    model_config = ConfigDict(from_attributes=True)

    taken_at: datetime = Field(description="When the self-check ran (UTC).")
    overall: str = Field(description="Snapshot verdict.")
    results: list[CheckResultOut] = Field(description="Per-check results.")


class IncidentSummaryOut(BaseModel):
    """Incident list row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Incident id.")
    correlation_key: str = Field(description="Deduplication identity.")
    source: str = Field(description="'alert' or 'self_check'.")
    severity: str = Field(description="'critical' or 'warning'.")
    status: str = Field(description="'open' or 'resolved'.")
    title: str = Field(description="Human title.")
    opened_at: datetime = Field(description="First observation (UTC).")
    last_seen_at: datetime = Field(description="Most recent observation (UTC).")
    resolved_at: datetime | None = Field(default=None, description="Resolution time, if any.")
    has_diagnosis: bool = Field(default=False, description="Whether a diagnosis is stored.")


class IncidentDetailOut(IncidentSummaryOut):
    """Incident detail with evidence, diagnosis and action audit."""

    evidence: dict[str, object] = Field(default_factory=dict, description="Evidence pack.")
    diagnosis: dict[str, object] | None = Field(default=None, description="Stored diagnosis.")
    action_log: list[dict[str, object]] = Field(
        default_factory=list, description="Append-only action audit."
    )


class IncidentListOut(BaseModel):
    """Paged incident listing with an EXACT total."""

    items: list[IncidentSummaryOut] = Field(description="Page rows.")
    total: int = Field(description="Exact COUNT(*) over the filtered set.")
    page: int = Field(description="1-based page number.")
    page_size: int = Field(description="Rows per page.")
