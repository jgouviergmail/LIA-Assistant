"""An explicit phone consent delta cannot verify a number or place a call."""

from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    field_validator,
    model_validator,
)

from src.domains.shared.phone_domains import PHONE_DOMAINS, unknown_phone_domains
from src.infrastructure.phone_identity import NativePhoneCallMode
from src.infrastructure.phone_preferences import PhonePreferenceSnapshot


class PhonePreferenceField(str, Enum):
    PREFERENCES = "phone_preferences"


class PhonePreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rich_context_enabled: StrictBool | None = None
    disabled_domains: list[StrictStr] | None = Field(
        default=None,
        max_length=len(PHONE_DOMAINS),
        json_schema_extra={"items": {"type": "string", "enum": list(PHONE_DOMAINS)}},
    )
    call_mode: NativePhoneCallMode | None = None

    @field_validator("rich_context_enabled", "disabled_domains", "call_mode", mode="before")
    @classmethod
    def refuse_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Phone settings cannot be null")
        return value

    @field_validator("disabled_domains")
    @classmethod
    def canonical_domains(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and unknown_phone_domains(value):
            raise ValueError("Choose available phone domains")
        return sorted(set(value)) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> PhonePreferenceRequest:
        if not self.model_fields_set:
            raise ValueError("Choose at least one phone setting")
        return self


class PhonePreferencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    phone_preferences: PhonePreferenceSnapshot
