"""Explicit paid generation request, with server-owned source comparison."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class PsycheSummaryField(StrEnum):
    SUMMARY = "psyche_summary"


class PsycheSummaryRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: Literal["current_account"]


class PsycheSummaryScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    state_present: bool
    settings: dict[str, JsonValue]
    language: str

    def public_scope(self) -> dict[str, JsonValue]:
        return {
            "scope": "current_account",
            "state_present": self.state_present,
            "settings": self.settings,
            "language": self.language,
        }


class PsycheSummaryPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    psyche_summary: PsycheSummaryScope
