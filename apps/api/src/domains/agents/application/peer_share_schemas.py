"""One explicit source-owned domain share; null means revocation, never omission."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from src.domains.peers.models import PeerShareDomain, PeerShareLevel
from src.domains.peers.schemas import ShareUpdate
from src.domains.peers.service import VALID_SHARE_LEVELS


class PeerShareInput(ShareUpdate):
    model_config = ConfigDict(frozen=True, extra="forbid")
    connection_id: UUID
    level: PeerShareLevel | None = Field(description="Explicit target level; null revokes sharing.")

    @model_validator(mode="after")
    def allowed_level(self) -> PeerShareInput:
        if self.level is not None and self.level.value not in VALID_SHARE_LEVELS[self.domain.value]:
            raise ValueError("Invalid source share level for domain")
        return self


class PeerShareSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: PeerShareInput
    peer_id: UUID
    display_name: str
    email_hint: str
    before_level: PeerShareLevel | None
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        level = self.request.level if after else self.before_level
        return {
            "connection_id": str(self.request.connection_id),
            "peer_id": str(self.peer_id),
            "display_name": self.display_name,
            "email_hint": self.email_hint,
            "domain": self.request.domain.value,
            "level": level.value if level else None,
        }


class PeerSharePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    peer_share: PeerShareSelection


class PeerShareField(StrEnum):
    SHARE = "peer_share"


if set(ShareUpdate.model_fields) != {"domain", "level"}:
    raise AssertionError("New source share options require reviewed native mapping")
if VALID_SHARE_LEVELS != {
    "calendar": frozenset({"availability", "details"}),
    "task": frozenset({"titles"}),
}:
    raise AssertionError("Changed source share matrix requires reviewed descriptions and consent")
if set(VALID_SHARE_LEVELS) != {domain.value for domain in PeerShareDomain} or set.union(
    *(set(levels) for levels in VALID_SHARE_LEVELS.values())
) != {level.value for level in PeerShareLevel}:
    raise AssertionError("New source share domains/levels require reviewed exact consent")
