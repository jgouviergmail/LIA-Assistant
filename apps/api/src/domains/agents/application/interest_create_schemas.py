"""Manual creation inherits source limits; stable identity is minted outside the model."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from src.domains.interests.models import InterestCategory
from src.domains.interests.schemas import InterestCreate


class InterestCreateConfiguration(InterestCreate):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @field_validator("category", mode="before")
    @classmethod
    def source_category(cls, value: object) -> InterestCategory:
        if isinstance(value, InterestCategory):
            return value
        if isinstance(value, str):
            return InterestCategory(value)
        raise ValueError("Select a declared interest category")


class InterestCreationValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: UUID
    configuration: InterestCreateConfiguration


class InterestCreatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    interest_to_create: InterestCreationValues
