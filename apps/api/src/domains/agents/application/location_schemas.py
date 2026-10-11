"""The model requests an address; the canonical command carries its resolved coordinates."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from src.domains.users.schemas import HomeLocationUpdate


class LocationField(str, Enum):
    HOME_LOCATION = "home_location"
    LAST_KNOWN_LOCATION = "last_known_location"


class LocationRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[LocationField] | None = Field(
        default=None, min_length=1, max_length=len(LocationField)
    )

    @model_validator(mode="after")
    def unique_fields(self) -> LocationRead:
        if self.fields is not None and len(self.fields) != len(set(self.fields)):
            raise ValueError("Location fields must be distinct")
        return self


class LocationChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["set", "clear"]
    address: Annotated[str | None, HomeLocationUpdate.model_fields["address"]] = None

    @model_validator(mode="after")
    def require_exact_request(self) -> LocationChangeRequest:
        if self.action == "set" and (self.address is None or not self.address.strip()):
            raise ValueError("Setting a home requires an address")
        if self.action == "clear" and "address" in self.model_fields_set:
            raise ValueError("Clearing home has no address input")
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
            "allOf": [
                {
                    "if": {"properties": {"action": {"const": "set"}}},
                    "then": {
                        "required": ["address"],
                        "properties": {"address": {"type": "string", "pattern": r"\S"}},
                    },
                    "else": {"not": {"required": ["address"]}},
                }
            ],
        }


class ResolvedHomeLocation(HomeLocationUpdate):
    model_config = ConfigDict(extra="forbid", strict=True)


class HomeLocationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    home_location: ResolvedHomeLocation | None
    last_known_location: Literal[None] = None

    @model_validator(mode="after")
    def enforce_cascade(self) -> HomeLocationPatch:
        if self.home_location is None and "last_known_location" not in self.model_fields_set:
            raise ValueError("Home deletion must declare the remembered-position cascade")
        if self.home_location is not None and "last_known_location" in self.model_fields_set:
            raise ValueError("Setting home does not change the remembered position")
        return self


def assert_location_schema_coverage() -> None:
    if set(HomeLocationUpdate.model_fields) != {"address", "lat", "lon", "place_id"}:
        raise ValueError("Review new home-location fields before offering the tool")
    if set(HomeLocationPatch.model_fields) != {field.value for field in LocationField}:
        raise ValueError("Location projections and commands require an explicit mapping")


assert_location_schema_coverage()
