"""Two independent source consents are sparse, strict and never nullable writes."""

from enum import StrEnum
from typing import Self

from pydantic import ConfigDict, GetJsonSchemaHandler, StrictBool, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from src.domains.peers.schemas import DiscoveryStateResponse, DiscoveryStateUpdate

PEER_PREFERENCE_COLUMNS = {
    "discovery_enabled": "discovery_enabled",
    "email_visible": "peer_email_visible",
}


class PeerPreferencePatch(DiscoveryStateUpdate):
    model_config = ConfigDict(frozen=True, extra="forbid")
    discovery_enabled: StrictBool | None = None
    email_visible: StrictBool | None = None

    @model_validator(mode="after")
    def explicit_nonnullable_fields(self) -> Self:
        if not self.model_fields_set or any(
            getattr(self, name) is None for name in self.model_fields_set
        ):
            raise ValueError("Consent changes require explicit non-null boolean fields")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(
            super().__get_pydantic_json_schema__(core_schema, handler)
        )
        # Both reviewed source fields are booleans; omission preserves, null never writes.
        properties = {
            name: {"type": "boolean", "title": value.get("title", name)}
            for name, value in schema["properties"].items()
        }
        return {**schema, "minProperties": 1, "properties": properties}


class PeerPreferenceField(StrEnum):
    DISCOVERY = "discovery_enabled"
    ADDRESS = "email_visible"


if set(DiscoveryStateUpdate.model_fields) != set(PEER_PREFERENCE_COLUMNS) or set(
    DiscoveryStateResponse.model_fields
) != set(PEER_PREFERENCE_COLUMNS):
    raise AssertionError(
        "New source peer consents require reviewed tool inputs, previews and column mapping"
    )
