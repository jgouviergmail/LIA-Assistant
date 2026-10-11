"""The public source level cannot accept another owner, a digest or invented effects."""

from enum import StrEnum
from typing import get_args

from pydantic import BaseModel, ConfigDict

from src.domains.psyche.reset_snapshot import PsycheResetSnapshot
from src.domains.psyche.schemas import PsycheResetRequest


class PsycheResetIntent(PsycheResetRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PsycheResetValues(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: PsycheResetIntent
    expected: PsycheResetSnapshot


class PsycheResetPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    psyche_reset: PsycheResetValues


class PsycheResetField(StrEnum):
    RESET = "psyche_reset"


if set(PsycheResetRequest.model_fields) != {"level"} or set(
    get_args(PsycheResetRequest.model_fields["level"].annotation)
) != {"soft", "full", "purge"}:
    raise AssertionError(
        "New psyche reset fields or levels require reviewed effects and source transitions"
    )
