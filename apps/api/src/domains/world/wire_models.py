"""Strict shared world DTO primitives; no scene, identity or persistence imports."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PoseResult = Literal["accepted", "occupied", "out_of_reach", "invalid"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


def require_integer_version(value: object) -> object:
    """Keep schema generations exact: bool, float and text are never version integers."""
    if type(value) is not int:
        raise ValueError("integer_version_required")
    return value


class VersionedModel(StrictModel):
    version: Literal[1] = Field(
        default=1, description="Explicit supported wire or preference schema version."
    )

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        """Reject booleans and coerced noninteger protocol versions before model validation."""
        return require_integer_version(value)


def explicit_consent(value: object) -> object:
    """Reject every value except literal True at the public consent boundary."""
    if value is not True:
        raise ValueError("explicit_consent_required")
    return value
