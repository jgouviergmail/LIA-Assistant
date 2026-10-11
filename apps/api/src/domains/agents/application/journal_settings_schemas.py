"""Native settings inherit source bounds; new settings require reviewed effect coverage."""

from enum import StrEnum

from pydantic import ConfigDict, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from src.domains.journals.preference_commands import JOURNAL_SETTING_FIELDS
from src.domains.journals.schemas import JournalSettingsUpdate


class JournalSettingField(StrEnum):
    ENABLED = "journals_enabled"
    CONSOLIDATION = "journal_consolidation_enabled"
    HISTORY = "journal_consolidation_with_history"
    TOTAL_CHARS = "journal_max_total_chars"
    CONTEXT_CHARS = "journal_context_max_chars"
    ENTRY_CHARS = "journal_max_entry_chars"
    CONTEXT_RESULTS = "journal_context_max_results"


class JournalSettingsPatch(JournalSettingsUpdate):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    @model_validator(mode="after")
    def require_explicit_values(self) -> JournalSettingsPatch:
        if not self.model_fields_set or any(
            getattr(self, name) is None for name in self.model_fields_set
        ):
            raise ValueError("Name at least one journal preference with a non-null value")
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


if {field.value for field in JournalSettingField} != JOURNAL_SETTING_FIELDS:
    raise AssertionError(
        "New journal preferences require reviewed confirmation, source effects and invalidation"
    )
