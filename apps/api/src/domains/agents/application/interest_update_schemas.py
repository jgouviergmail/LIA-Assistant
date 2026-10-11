"""Source sparse constraints; comparison facts are assembled outside model authority."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, GetJsonSchemaHandler, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from src.domains.agents.application.interest_create_schemas import InterestCreateConfiguration
from src.domains.interests.management_schemas import InterestConfiguration
from src.domains.interests.models import InterestCategory, InterestStatus
from src.domains.interests.schemas import InterestUpdate


class InterestUpdateChanges(InterestUpdate):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def refuse_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Omit an unchanged interest field instead of null")
        return value

    @field_validator("category", mode="before")
    @classmethod
    def category_value(cls, value: object) -> InterestCategory:
        return InterestCreateConfiguration.source_category(value)

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Choose at least one interest field")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(
            super().__get_pydantic_json_schema__(core_schema, handler)
        )
        properties: dict[str, JsonSchemaValue] = {}
        for name, value in schema.get("properties", {}).items():
            prop = dict(value)
            alternatives = [item for item in prop.pop("anyOf", []) if item.get("type") != "null"]
            if len(alternatives) == 1:
                prop.update(alternatives[0])
            prop.pop("default", None)
            properties[name] = prop
        return {**schema, "minProperties": 1, "properties": properties}


class InterestUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    interest_id: UUID
    changes: InterestUpdateChanges


class InterestEditSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    status: InterestStatus
    subject: str | None


class InterestUpdateValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected: InterestEditSnapshot
    configuration: InterestConfiguration
    changes: InterestUpdateChanges


class InterestUpdatePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    interest_configuration: InterestUpdateValues
