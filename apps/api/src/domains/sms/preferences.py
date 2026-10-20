"""Separate archive ingestion, assistant consent and immediate-push policy."""

from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError


class SmsPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ingestion_enabled: StrictBool = True
    assistant_enabled: StrictBool = False
    push_enabled: StrictBool = True

    @classmethod
    def from_stored(cls, value: object) -> SmsPreferences:
        if value is None:
            return cls()
        try:
            return cls.model_validate(value)
        except ValidationError:
            return cls(ingestion_enabled=False, assistant_enabled=False, push_enabled=False)
