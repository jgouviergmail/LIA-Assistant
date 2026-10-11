"""Allowlisted, short-lived browser observations; never authentication facts."""

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

RecordingPhase = Literal[
    "idle", "starting", "recording", "offline", "stopping", "processing", "interrupted", "error"
]


class RecordingDeviceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    actor_id: UUID
    observed_at: AwareDatetime
    supported: bool
    phase: RecordingPhase
    meeting_id: UUID | None

    @model_validator(mode="after")
    def coherent(self) -> RecordingDeviceSnapshot:
        if (
            self.phase in {"recording", "offline", "stopping", "processing", "interrupted"}
            and self.meeting_id is None
        ):
            raise ValueError("An active recording requires its original meeting identifier")
        if self.phase in {"idle", "starting"} and self.meeting_id is not None:
            raise ValueError("An idle recorder cannot carry another meeting")
        return self

    def fresh_for(self, actor_id: UUID, *, now: datetime) -> bool:
        age = now - self.observed_at
        return self.actor_id == actor_id and timedelta(seconds=-5) <= age <= timedelta(seconds=30)
