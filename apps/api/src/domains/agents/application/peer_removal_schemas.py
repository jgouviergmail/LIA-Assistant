"""An exact accepted pair and both share directions define approved severance."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.peers.schemas import ShareItem


class PeerRemovalInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    connection_id: UUID


class PeerRemovalSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: PeerRemovalInput
    peer_id: UUID
    display_name: str
    email_hint: str
    my_shares: list[ShareItem] = Field(max_length=2)
    their_shares: list[ShareItem] = Field(max_length=2)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "connection_id": str(self.request.connection_id),
            "peer_id": str(self.peer_id),
            "display_name": self.display_name,
            "email_hint": self.email_hint,
            "status": "removed" if after else "accepted",
            "my_shares": (
                [] if after else [share.model_dump(mode="json") for share in self.my_shares]
            ),
            "their_shares": (
                [] if after else [share.model_dump(mode="json") for share in self.their_shares]
            ),
            "shared_work_release": "source_attempted" if after else "not_started",
        }


class PeerRemovalPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    peer_removal: PeerRemovalSelection


class PeerRemovalField(StrEnum):
    REMOVAL = "peer_removal"
