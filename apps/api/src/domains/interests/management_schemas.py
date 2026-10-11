"""Existing source facts have read semantics; validators apply to the proposed delta."""

from pydantic import BaseModel, ConfigDict, field_validator

from src.domains.interests.models import InterestCategory
from src.domains.interests.schemas import InterestUpdate


class InterestConfiguration(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    topic: str
    category: InterestCategory
    positive_signals: int
    negative_signals: int

    @field_validator("category", mode="before")
    @classmethod
    def category_value(cls, value: object) -> InterestCategory:
        if isinstance(value, InterestCategory):
            return value
        if isinstance(value, str):
            return InterestCategory(value)
        raise ValueError("Select a source interest category")


if set(InterestConfiguration.model_fields) != set(InterestUpdate.model_fields):
    raise AssertionError("New source interest edit fields require a reviewed fact mapping")
