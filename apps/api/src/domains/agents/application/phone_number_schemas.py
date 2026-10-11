"""An explicit declaration can change a number, never its proof of ownership."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, GetJsonSchemaHandler, StrictStr, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from src.domains.telephony.phone_numbers import to_e164
from src.domains.telephony.schemas import TelephonyIdentityNumberRequest
from src.infrastructure.phone_number_preferences import PhoneNumberSnapshot, PhoneNumberValues


class PhoneNumberField(str, Enum):
    NUMBER = "phone_number"


class PhoneNumberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["set", "clear"]
    phone_number: Annotated[
        StrictStr | None, TelephonyIdentityNumberRequest.model_fields["phone_number"]
    ] = None

    @model_validator(mode="after")
    def require_exact_request(self) -> PhoneNumberRequest:
        if self.action == "clear":
            if "phone_number" in self.model_fields_set:
                raise ValueError("Clearing a number has no number input")
            return self
        if self.phone_number is None or to_e164(self.phone_number) is None:
            raise ValueError("Declare a number accepted by the phone settings")
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
                        "required": ["phone_number"],
                        "properties": {"phone_number": {"type": "string"}},
                    },
                    "else": {"not": {"required": ["phone_number"]}},
                }
            ],
        }


class PhoneNumberCommandValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected: PhoneNumberSnapshot
    number: StrictStr | None = Field(pattern=r"^\+[1-9][0-9]{6,14}$")

    def public_values(self) -> PhoneNumberValues:
        if self.number == self.expected.values.phone_number:
            # An unreadable stored record cleared to None still becomes unset.
            if self.expected.values.number_status != "unreadable":
                return self.expected.values
        return PhoneNumberValues(
            phone_number=self.number,
            number_status="available" if self.number else "unset",
            verified=False,
            verified_at=None,
        )


class PhoneNumberPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    phone_number: PhoneNumberCommandValues


def assert_phone_number_schema_coverage() -> None:
    if set(TelephonyIdentityNumberRequest.model_fields) != {"phone_number"}:
        raise ValueError("Review new number settings before offering the tool")


assert_phone_number_schema_coverage()
