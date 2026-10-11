"""One owned entry selector grants no source/account override."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JournalProvenanceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    entry_id: UUID
