"""A bounded, non-secret interaction receipt; completion stays a separate fact."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError, field_validator


class PendingApplicationInteraction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    interaction_id: UUID
    kind: Literal["secure", "device"]
    expires_at: AwareDatetime

    @field_validator("expires_at", mode="before")
    @classmethod
    def require_explicit_timestamp(cls, value: object) -> object:
        if not isinstance(value, datetime | str):
            raise ValueError("An interaction deadline must be an explicit aware timestamp")
        return value


def _result_field(result: object, name: str) -> object:
    if isinstance(result, dict):
        return result.get(name)
    try:
        return getattr(result, name, None)
    except Exception:
        # An observer cannot break a returned operation through a faulty property.
        return None


def pending_interaction_of(result: object) -> PendingApplicationInteraction | None:
    """Recognize only explicit incomplete results with a reviewed finite receipt.

    Deadlines may be past: the durable command reader determines current expiry,
    while the notarized effect remains the immutable fact that a handoff was requested.
    """
    if (
        _result_field(result, "success") is not False
        or _result_field(result, "phase") != "waiting"
        or type(_result_field(result, "committed")) is not bool
        or _result_field(result, "error_code") is not None
        or _result_field(result, "no_op") not in (None, False)
    ):
        return None
    try:
        interaction = PendingApplicationInteraction.model_validate(
            _result_field(result, "interaction")
        )
    except ValidationError:
        return None
    if interaction.kind == "secure" and _result_field(result, "committed") is True:
        return None
    return interaction
