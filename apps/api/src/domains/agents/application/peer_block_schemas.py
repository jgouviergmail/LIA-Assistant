"""Directional block consent pins visible identity and existing relationship consequences."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool

from src.domains.peers.models import PeerConnectionStatus
from src.domains.peers.schemas import BlockCreate, ShareItem


class PeerBlockInput(BlockCreate):
    model_config = ConfigDict(frozen=True, extra="forbid")
    blocked: StrictBool


class PeerBlockSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: PeerBlockInput
    display_name: str | None
    email_hint: str | None
    before_blocked: bool
    pair_status: PeerConnectionStatus | None
    my_shares: list[ShareItem] = Field(default_factory=list, max_length=2)
    their_shares: list[ShareItem] = Field(default_factory=list, max_length=2)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    share_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def severs_pair(self) -> bool:
        return self.request.blocked and self.pair_status in {
            PeerConnectionStatus.PENDING,
            PeerConnectionStatus.ACCEPTED,
        }

    @property
    def no_op(self) -> bool:
        return self.request.blocked == self.before_blocked and not self.severs_pair

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        status = (
            "removed"
            if after and self.severs_pair
            else self.pair_status.value if self.pair_status else None
        )
        return {
            "peer_id": str(self.request.peer_id),
            "display_name": self.display_name,
            "email_hint": self.email_hint,
            "blocked": self.request.blocked if after else self.before_blocked,
            "connection_status": status,
            "my_shares": (
                []
                if after and self.severs_pair
                else [item.model_dump(mode="json") for item in self.my_shares]
            ),
            "their_shares": (
                []
                if after and self.severs_pair
                else [item.model_dump(mode="json") for item in self.their_shares]
            ),
            "shared_work_release": (
                "source_attempted"
                if after
                and self.request.blocked
                and self.pair_status == PeerConnectionStatus.ACCEPTED
                else "not_started"
            ),
            "notifications": "none",
        }


class PeerBlockPatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    peer_block: PeerBlockSelection


class PeerBlockField(StrEnum):
    BLOCK = "peer_block"


if set(BlockCreate.model_fields) != {"peer_id"}:
    raise AssertionError("New source block controls require reviewed native mapping")
