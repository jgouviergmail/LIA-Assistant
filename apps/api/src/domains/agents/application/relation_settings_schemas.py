"""Source relation options retain source bounds and require explicit sparse approval."""

from enum import StrEnum
from typing import Self

from pydantic import ConfigDict, Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from src.core.constants import (
    RELATION_OVERVIEW_MAX_ITEMS_CEILING,
    RELATION_OVERVIEW_MAX_ITEMS_DEFAULT,
)
from src.domains.relations.overview_scope import (
    OverviewDirection,
    OverviewRole,
    OverviewSection,
    RelationOverviewScope,
)
from src.domains.relations.preference_commands import RelationPreferencePatch
from src.domains.relations.schemas import RelationSettingsUpdate


class RelationSettingField(StrEnum):
    DEBRIEF = "relation_debrief_enabled"
    SCOPE = "relation_overview_scope"


class ReviewedRelationScope(RelationOverviewScope):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sections: list[OverviewSection] = Field(
        default_factory=lambda: list(OverviewSection), max_length=len(OverviewSection)
    )
    directions: list[OverviewDirection] = Field(
        default_factory=lambda: list(OverviewDirection), max_length=len(OverviewDirection)
    )
    roles: list[OverviewRole] = Field(
        default_factory=lambda: list(OverviewRole), max_length=len(OverviewRole)
    )
    # Enum wire strings are accepted; boolean item limits are never coerced to one.
    max_items: int = Field(
        default=RELATION_OVERVIEW_MAX_ITEMS_DEFAULT,
        ge=1,
        le=RELATION_OVERVIEW_MAX_ITEMS_CEILING,
        strict=True,
    )

    @model_validator(mode="after")
    def bounded_unique_options(self) -> Self:
        for selected, ceiling in (
            (self.sections, len(OverviewSection)),
            (self.directions, len(OverviewDirection)),
            (self.roles, len(OverviewRole)),
        ):
            if len(selected) > ceiling or len(set(selected)) != len(selected):
                raise ValueError("Select each source relation option at most once")
        return self


class RelationSettingsPatch(RelationPreferencePatch):
    relation_overview_scope: ReviewedRelationScope | None = None

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


if set(RelationSettingsPatch.model_fields) != {
    field.value for field in RelationSettingField
} or set(RelationSettingsUpdate.model_fields) != {"debrief_enabled"}:
    raise AssertionError(
        "New relation preferences require reviewed source mapping, approval and UI sync"
    )

if set(RelationOverviewScope.model_fields) != {"sections", "directions", "roles", "max_items"}:
    raise AssertionError(
        "New overview scope controls require reviewed bounds and confirmation copy"
    )
