"""Typed ownership and results of attachment filesystem effects."""

from dataclasses import dataclass
from uuid import UUID

from src.domains.attachments.models import AttachmentOrigin


@dataclass(frozen=True, slots=True)
class UploadMetadata:
    """Validated presentation metadata, never a caller-selected filesystem path."""

    filename: str
    mime_type: str
    content_type: str
    suffix: str
    origin: AttachmentOrigin = AttachmentOrigin.UPLOAD
    title: str | None = None
    conversation_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class FileWriteResult:
    """What a joined disk operation actually produced, before publication."""

    file_size: int
    extracted_text: str | None = None


@dataclass(frozen=True, slots=True)
class FileWriteTicket:
    """The committed authority and exact path of a single uploader."""

    attachment_id: UUID
    owner_id: UUID
    worker_id: UUID
    owner_token: UUID
    file_path: str


@dataclass(frozen=True, slots=True)
class FileRemovalClaim:
    """A fenced, retryable unlink of an immutable path whose writers have stopped."""

    attachment_id: UUID
    owner_id: UUID
    worker_id: UUID
    owner_token: UUID
    fence: int
    file_path: str
    reason: str
    check_identity: bool = False
    expected_digest: str | None = None
