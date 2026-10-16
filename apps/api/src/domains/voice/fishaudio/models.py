"""The public Fish Audio voices the instance pinned (ADR-345 amendment 2026-10-14).

ONE list for every voice slot: a public voice an administrator pinned — after
attesting the right to use it — is offered to the chat's voice and to the
radio's alike. Pinning and unpinning are acts of the voice library, filed in the
admin audit log; the row only says which voice, who pinned it, and when.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel

#: Column comments, shared with the migration — the replay check compares them.
VOICE_ID_COMMENT = "The vendor's public model id (32 lowercase hexadecimal characters)."
PINNED_BY_COMMENT = "The administrator who pinned it; NULL once their account is gone."


class FishAudioPinnedVoice(BaseModel):
    """A public library voice the instance offers beside its own and the licensed ones.

    Attributes:
        voice_id: The vendor model id, once per instance.
        pinned_by: Who pinned it, while that account exists.
    """

    __tablename__ = "fishaudio_pinned_voices"

    voice_id: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, comment=VOICE_ID_COMMENT
    )
    pinned_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment=PINNED_BY_COMMENT,
    )


class FishAudioCatalogueRevision(BaseModel):
    """One durable instance revision fences choices against library deletion.

    The revision and pending deletion tokens survive cache loss. Only vendor
    voice ids and random operation tokens are kept; no credentials or samples.
    Writers take the instance catalogue lock before changing either.
    """

    __tablename__ = "fishaudio_catalogue_revisions"
    __table_args__ = (
        CheckConstraint(
            "id = '00000000-0000-0000-0000-000000000000'::uuid",
            name="ck_fishaudio_catalogue_singleton",
        ),
        CheckConstraint(
            "jsonb_typeof(pending_removals) = 'object'", name="ck_fishaudio_pending_removals_object"
        ),
    )

    generation: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    pending_removals: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


__all__ = [
    "PINNED_BY_COMMENT",
    "VOICE_ID_COMMENT",
    "FishAudioCatalogueRevision",
    "FishAudioPinnedVoice",
]
