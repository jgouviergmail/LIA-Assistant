"""API shapes of a fired reminder's postponement (ADR-268 amendment 2026-11-16)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from src.domains.reminders.firing_service import FiringState, SnoozeResult
from src.domains.reminders.firings import FiringSurface, SnoozeChoice, SnoozeOutcome, StopOutcome


class ReminderFiringStateResponse(BaseModel):
    """What the chat bubble of a fired reminder offers."""

    id: UUID = Field(..., description="The occurrence that rang.")
    fired_at: datetime = Field(..., description="When it rang.")
    snoozable_until: datetime = Field(
        ..., description="Past this instant the occurrence can no longer be postponed."
    )
    snoozed_until: datetime | None = Field(
        None, description="Where a press already postponed it; null while none did."
    )
    stoppable: bool = Field(
        ..., description="Whether the reminder still has a future a press could stop."
    )
    short_minutes: int = Field(..., description="The short delay offered, in minutes.")
    long_minutes: int = Field(..., description="The long delay offered, in minutes.")

    @classmethod
    def of(cls, state: FiringState) -> ReminderFiringStateResponse:
        """The response for a state the service read."""
        return cls(
            id=state.firing_id,
            fired_at=state.fired_at,
            snoozable_until=state.snoozable_until,
            snoozed_until=state.snoozed_until,
            stoppable=state.stoppable,
            short_minutes=state.delays.short_minutes,
            long_minutes=state.delays.long_minutes,
        )


class ReminderSnoozeRequest(BaseModel):
    """A press on one of the « later »."""

    choice: SnoozeChoice = Field(..., description="Which « later »: short, long or morning.")
    surface: FiringSurface = Field(
        FiringSurface.CHAT, description="Where the press came from: chat or push."
    )

    @field_validator("surface")
    @classmethod
    def _not_a_channel(cls, value: FiringSurface, info: ValidationInfo) -> FiringSurface:
        """A Telegram press reaches the bot, never this route."""
        if value is FiringSurface.TELEGRAM:
            raise ValueError(f"{info.field_name} must be chat or push")
        return value


class ReminderSnoozeResponse(BaseModel):
    """What the press did."""

    outcome: SnoozeOutcome = Field(
        ..., description="snoozed, already_snoozed, expired or collides."
    )
    snoozed_until: datetime | None = Field(
        None, description="When the reminder comes back (snoozed or already_snoozed)."
    )
    next_occurrence_at: datetime | None = Field(
        None, description="The series' next occurrence a refused press met (collides)."
    )

    @classmethod
    def of(cls, result: SnoozeResult) -> ReminderSnoozeResponse:
        """The response for a verdict the service returned."""
        return cls(
            outcome=result.outcome,
            snoozed_until=result.snoozed_until,
            next_occurrence_at=result.next_occurrence_at,
        )


class ReminderStopResponse(BaseModel):
    """What a « stop this reminder » press did."""

    outcome: StopOutcome = Field(..., description="stopped or already_stopped.")
