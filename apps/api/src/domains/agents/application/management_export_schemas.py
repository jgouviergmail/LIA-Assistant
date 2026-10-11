"""Only format is model-selected; source count, clock and comparison are sealed."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt


class ManagementExportRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    format: Literal["csv", "json"] = "csv"


class ManagementExportSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    format: Literal["csv", "json"]
    observed_at: AwareDatetime
    selected_count: StrictInt = Field(ge=0)
    selection_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)


class ManagementExportPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    management_export: ManagementExportSnapshot
