"""Source psyche fields require strict sparse values and deliberate confirmation/sync coverage."""

from enum import StrEnum

from pydantic import ConfigDict, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from src.domains.psyche.preference_commands import PSYCHE_SETTING_FIELDS
from src.domains.psyche.schemas import PsycheSettingsUpdate


class PsycheSettingField(StrEnum):
    ENABLED = "psyche_enabled"
    DISPLAY_AVATAR = "psyche_display_avatar"
    SENSITIVITY = "psyche_sensitivity"
    STABILITY = "psyche_stability"


class PsycheSettingsPatch(PsycheSettingsUpdate):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

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


if {field.value for field in PsycheSettingField} != PSYCHE_SETTING_FIELDS:
    raise AssertionError(
        "New psyche preferences require reviewed confirmation fields and UI invalidation"
    )
