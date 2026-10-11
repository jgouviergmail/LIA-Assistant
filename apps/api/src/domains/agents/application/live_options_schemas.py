"""Explicit bounded Live choice listing; discovery is separate from saved settings."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator


class LiveOptionsRead(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "if": {"properties": {"section": {"const": "voices"}}, "required": ["section"]},
            "then": {
                "required": ["provider"],
                "properties": {"provider": {"type": "string", "minLength": 1}},
            },
            "allOf": [
                {
                    "if": {"required": ["cursor"], "properties": {"cursor": {"type": "string"}}},
                    "then": {"properties": {"offset": {"const": 0}}},
                }
            ],
        },
    )
    section: Literal["models", "voices"]
    provider: StrictStr | None = Field(default=None, min_length=1, max_length=32)
    offset: StrictInt = Field(default=0, ge=0, le=10000)
    limit: StrictInt = Field(default=25, ge=1, le=50)
    cursor: StrictStr | None = Field(default=None, pattern=r"^[0-9a-f]{64}:[1-9][0-9]{0,4}$")

    @model_validator(mode="after")
    def require_voice_provider(self) -> LiveOptionsRead:
        if self.section == "voices" and self.provider is None:
            raise ValueError("Choose an owned Live provider before listing voices")
        if self.cursor is not None and self.offset:
            raise ValueError("Use a cursor or an initial offset, never both")
        return self
