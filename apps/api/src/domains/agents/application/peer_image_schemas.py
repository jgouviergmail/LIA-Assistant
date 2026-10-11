"""Exact generated-image and recipient approval; storage paths remain private."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.peers.schemas import ImageShareCreate


class PeerImageInput(ImageShareCreate):
    model_config = ConfigDict(frozen=True, extra="forbid")
    connection_id: UUID


class PeerImageSelection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request: PeerImageInput
    peer_id: UUID
    display_name: str
    email_hint: str
    title: str | None
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "connection_id": str(self.request.connection_id),
            "peer_id": str(self.peer_id),
            "display_name": self.display_name,
            "email_hint": self.email_hint,
            "attachment_id": str(self.request.attachment_id),
            "title": self.title,
            "comment": self.request.comment,
            "copy_to_recipient_gallery": after,
            "notification": "attempt_after_save" if after else "not_started",
        }


class PeerImagePatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    peer_image: PeerImageSelection


class PeerImageField(StrEnum):
    IMAGE = "peer_image"
