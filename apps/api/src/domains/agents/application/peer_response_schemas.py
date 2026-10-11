"""Only a selected incoming connection and strict accept/refuse choice are public inputs."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool

from src.domains.peers.schemas import ConnectionRespond, ConnectionView


class PeerResponseInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    connection_id: UUID
    accept: StrictBool


class PeerResponseSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: PeerResponseInput
    card: ConnectionView
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "connection_id": str(self.card.id),
            "peer_id": str(self.card.peer_id),
            "display_name": self.card.peer_display_name,
            "email_hint": self.card.peer_email_hint,
            "note": self.card.context_message,
            "status": ("accepted" if self.request.accept else "declined") if after else "pending",
        }


class PeerResponsePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    peer_response: PeerResponseSelection


class PeerResponseField(StrEnum):
    RESPONSE = "peer_response"


if set(ConnectionRespond.model_fields) != {"accept"}:
    raise AssertionError("New source response options require reviewed exact approval")
