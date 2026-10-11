"""Explicit outcomes distinguish saved state from handoff and failure."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from src.core.application_interaction import PendingApplicationInteraction


class ApplicationPhase(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RESUMING = "resuming"
    COMMITTED = "committed"
    WAITING = "waiting"
    FAILED = "failed"
    CONFLICT = "conflict"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ApplicationExecutionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    success: bool
    phase: ApplicationPhase
    committed: bool = False
    no_op: bool = False
    values: dict[str, JsonValue] = Field(default_factory=dict)
    error_code: str | None = None
    interaction: PendingApplicationInteraction | None = None

    @model_validator(mode="after")
    def require_explicit_completion(self) -> ApplicationExecutionOutcome:
        if self.phase in {
            ApplicationPhase.PENDING,
            ApplicationPhase.CLAIMED,
            ApplicationPhase.RESUMING,
        }:
            raise ValueError("Pending and claimed commands are not execution results")
        if self.success != (self.phase == ApplicationPhase.COMMITTED and self.committed):
            raise ValueError("Only an explicitly committed result is completed success")
        if (self.phase == ApplicationPhase.WAITING) != (self.interaction is not None):
            raise ValueError("Only waiting outcomes carry a pending interaction")
        if self.phase == ApplicationPhase.WAITING and (self.error_code is not None or self.no_op):
            raise ValueError("A pending interaction is neither a refusal nor a completed no-op")
        if self.interaction is not None and self.interaction.kind == "secure" and self.committed:
            raise ValueError("A secure handoff cannot have performed its awaiting action")
        return self
