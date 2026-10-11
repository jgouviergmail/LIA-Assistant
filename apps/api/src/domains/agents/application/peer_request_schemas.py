"""Public invitation fields remain separate from private source-state proofs."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.core.constants import PEERS_CONTEXT_MESSAGE_MAX_CHARS
from src.domains.peers.models import PeerConnectionStatus
from src.domains.peers.schemas import ConnectionRequestCreate


class PeerRequestInput(ConnectionRequestCreate):
    model_config = ConfigDict(frozen=True, extra="forbid")
    context_message: str | None = Field(
        default=None, max_length=PEERS_CONTEXT_MESSAGE_MAX_CHARS, strict=True
    )


class PeerRequestField(StrEnum):
    REQUEST = "peer_request"


class PeerRequestSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: PeerRequestInput
    display_name: str
    email_hint: str
    before_status: str
    after_status: str
    no_op: bool
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "peer_id": str(self.request.peer_id),
            "display_name": self.display_name,
            "email_hint": self.email_hint,
            "status": self.after_status if after else self.before_status,
            "no_op": self.no_op,
            "note": (
                self.request.context_message
                if after
                and not self.no_op
                and self.after_status == PeerConnectionStatus.PENDING.value
                else None
            ),
        }


class PeerRequestPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    peer_request: PeerRequestSelection


if set(ConnectionRequestCreate.model_fields) != {"peer_id", "context_message"}:
    raise AssertionError("New invitation options require reviewed exact confirmation")
if set(PeerConnectionStatus) != {
    PeerConnectionStatus.PENDING,
    PeerConnectionStatus.ACCEPTED,
    PeerConnectionStatus.DECLINED,
    PeerConnectionStatus.REMOVED,
}:
    raise AssertionError("New source pair states require reviewed invitation effects")
