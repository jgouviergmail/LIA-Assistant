"""Read-only origin of a recipient-owned capability, independent of source lifetime."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

CapabilityOriginKind = Literal["skill", "mcp", "plugin"]


class CapabilityOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sender_display_name: str | None
    shared_at: AwareDatetime
    transfer_id: UUID
