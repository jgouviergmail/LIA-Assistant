"""The model chooses a verdict and an identity; source comparison facts stay sealed."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.agents.application.interest_update_schemas import InterestEditSnapshot
from src.domains.interests.management_schemas import InterestConfiguration
from src.domains.interests.schemas import InterestFeedbackKind


class InterestFeedbackSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    interest_id: UUID | None = None
    notification_id: UUID | None = None
    feedback: InterestFeedbackKind

    @model_validator(mode="after")
    def exactly_one_identity(self) -> Self:
        if (self.interest_id is None) == (self.notification_id is None):
            raise ValueError("Select one interest or one delivered notification")
        return self


class InterestFeedbackNotification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    interest_id: UUID
    created_at: datetime
    user_feedback: InterestFeedbackKind | None
    feedback_at: datetime | None
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class InterestFeedbackValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected: InterestEditSnapshot
    configuration: InterestConfiguration
    feedback: InterestFeedbackKind
    notification: InterestFeedbackNotification | None
    card_scope: Literal["all_interest_cards", "one_notification"]


class InterestFeedbackPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    interest_feedback: InterestFeedbackValues
