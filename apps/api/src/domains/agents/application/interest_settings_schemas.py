"""Inherited source constraints and reviewed setting vocabulary close the native boundary."""

from enum import Enum

from pydantic import ConfigDict, GetJsonSchemaHandler, field_validator, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from src.domains.interests.preference_commands import INTEREST_SETTING_FIELDS
from src.domains.interests.schemas import InterestSettingsUpdate


class InterestSettingField(str, Enum):
    ENABLED = "interests_enabled"
    START_HOUR = "interests_notify_start_hour"
    END_HOUR = "interests_notify_end_hour"
    MIN_PER_DAY = "interests_notify_min_per_day"
    MAX_PER_DAY = "interests_notify_max_per_day"


class InterestSettingsPatch(InterestSettingsUpdate):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*")
    @classmethod
    def explicit_value(cls, value: object) -> object:
        if value is None:
            raise ValueError("A confirmed interest setting needs an explicit value")
        return value

    @model_validator(mode="after")
    def nonempty_change(self) -> InterestSettingsPatch:
        if not self.model_fields_set:
            raise ValueError("Name at least one interest setting")
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


if {field.value for field in InterestSettingField} != INTEREST_SETTING_FIELDS:
    raise AssertionError(
        "New interest settings require a reviewed native field and UI invalidation"
    )
