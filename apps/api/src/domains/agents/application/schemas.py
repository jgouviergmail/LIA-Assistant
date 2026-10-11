"""Bounded application contracts; sensitive columns are never inferred from User."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    JsonValue,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from src.domains.agents.application.preference_fields import (
    PREFERENCE_FIELDS,
    PREFERENCE_READ_ONLY_FIELDS,
    PreferenceField,
    assert_preference_field_coverage,
)
from src.domains.agents.application.schema_projection import (
    NON_NULL_PREFERENCE_FIELDS,
    patch_property_schema,
)
from src.domains.users.schemas import UserUpdate


class PreferencePatch(UserUpdate):
    """Keep the UI schema's validators while closing its extra-field boundary."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def normalize_displayed_choice(cls, value: object, info: ValidationInfo) -> object:
        from src.domains.agents.application.setting_choices import (
            normalize_setting_value,
        )

        return normalize_setting_value(info.field_name or "", value)

    @model_validator(mode="after")
    def require_a_change(self) -> PreferencePatch:
        if not self.model_fields_set:
            raise ValueError("A preference patch must name at least one field")
        if self.model_fields_set & PREFERENCE_READ_ONLY_FIELDS:
            raise ValueError("Profile identity is read-only on this application surface")
        if any(
            getattr(self, name) is None
            for name in self.model_fields_set & NON_NULL_PREFERENCE_FIELDS
        ):
            raise ValueError("A non-null preference requires an explicit value or default")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(
            super().__get_pydantic_json_schema__(core_schema, handler)
        )
        return {
            **schema,
            "minProperties": 1,
            "properties": {
                name: patch_property_schema(name, value)
                for name, value in schema.get("properties", {}).items()
                if name not in PREFERENCE_READ_ONLY_FIELDS
            },
        }


class PreferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[PreferenceField] | None = Field(
        default=None,
        min_length=1,
        max_length=len(PREFERENCE_FIELDS),
        description="Distinct preference fields to read; omit for all",
    )

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, fields: list[PreferenceField] | None) -> list[PreferenceField] | None:
        if fields is not None and (
            len(fields) != len(set(fields)) or not set(fields) <= set(PREFERENCE_FIELDS)
        ):
            raise ValueError("Select distinct, declared preference fields")
        return fields


class PreferenceChangeRequest(BaseModel):
    """Resolve a relative UI step to an absolute patch before confirmation."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["set", "increase_font", "decrease_font"]
    patch: PreferencePatch | None = None

    @model_validator(mode="after")
    def validate_mode(self) -> PreferenceChangeRequest:
        if (self.mode == "set") != (self.patch is not None):
            raise ValueError("Set requires a patch; font steps must not carry one")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(
            super().__get_pydantic_json_schema__(core_schema, handler)
        )
        patch = next(
            item for item in schema["properties"]["patch"]["anyOf"] if item.get("type") != "null"
        )
        return {
            **schema,
            "allOf": [
                {
                    "if": {
                        "properties": {"mode": {"const": "set"}},
                        "required": ["mode"],
                    },
                    "then": {"required": ["patch"], "properties": {"patch": patch}},
                    "else": {"properties": {"patch": {"type": "null"}}},
                }
            ],
        }


class ApplicationProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["account", "device", "administration"] = "account"
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    values: dict[str, JsonValue]


assert_preference_field_coverage(set(UserUpdate.model_fields))
