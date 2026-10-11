"""Sparse source editing and its server-owned semantic comparison facts."""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    JsonValue,
    StringConstraints,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from src.domains.journals.removal_snapshot import JournalRemovalSnapshot
from src.domains.journals.schemas import JournalEntryUpdate


class JournalUpdateChanges(JournalEntryUpdate):
    model_config = ConfigDict(frozen=True, extra="forbid")
    search_hints: (
        list[Annotated[str, StringConstraints(min_length=1, max_length=100, strict=True)]] | None
    ) = Field(default=None, max_length=5)

    @model_validator(mode="after")
    def require_change(self) -> JournalUpdateChanges:
        if not self.model_fields_set or any(
            getattr(self, name) is None for name in self.model_fields_set
        ):
            raise ValueError("Choose explicit non-null journal changes; use [] to clear hints")
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


class JournalUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    entry_id: UUID
    changes: JournalUpdateChanges


class JournalUpdateValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected: JournalRemovalSnapshot
    changes: JournalUpdateChanges
    projected: dict[str, JsonValue]
    invalidates_portrait: bool


class JournalUpdatePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    journal_configuration: JournalUpdateValues


class JournalUpdateField(StrEnum):
    ENTRY = "journal_entry"


if set(JournalEntryUpdate.model_fields) != {
    "title",
    "content",
    "mood",
    "search_hints",
    "confidence",
    "level",
}:
    raise AssertionError(
        "New journal edit fields require source transition and exact approval coverage"
    )
