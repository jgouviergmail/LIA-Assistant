"""Share a generated image with a connection (ADR-316).

A relayed MESSAGE goes through the sender's assistant: a draft the person
confirms, then a delivery sweep and a wording in the recipient's voice. An
IMAGE is shared by an explicit click on the image itself — the click is the
confirmation — and arrives as it is: a COPY in the recipient's gallery, filed
like an image they generated when it arrived (its own lifetime, the attachment
TTL), and a bubble in their chat that shows it, the sender's optional comment
quoted literally underneath (``shared/markdown_literal``: a third party's words
never become links, images or markup in someone else's chat).

Two phases, never one transaction across a network call (ADR-304):

1. :func:`share_image` checks, copies and records, then COMMITS: the
   connection is accepted and no block separates the pair, the image is the
   sender's own live generated image, the daily quotas hold (counted on the
   share ledger, serialised per sender by a transaction-scoped advisory lock so
   two shares racing for the last slot cannot both land), the file is copied
   under the recipient's folder and the gallery row and the ledger row are
   written together. A failed write withdraws the copy.
2. :func:`deliver_shared_image` shows it in the recipient's chat (archive,
   live event, push) on a session of its own, best-effort: the image is
   already in their gallery whatever happens there.

No model is called, so nothing is spent; the comment is kept nowhere but in
the recipient's chat.
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NoReturn

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import PEERS_IMAGE_SHARE_COMMENT_MAX_CHARS
from src.core.exceptions import (
    raise_invalid_input,
    raise_not_found_or_unauthorized,
    raise_rate_limit_exceeded,
)
from src.core.i18n_proactive import ProactiveMessages
from src.domains.attachments.models import (
    Attachment,
    AttachmentContentType,
    AttachmentOrigin,
    AttachmentStatus,
)
from src.domains.attachments.repository import AttachmentRepository
from src.domains.attachments.urls import attachment_url
from src.domains.image_generation.image_store import (
    GENERATED_IMAGES_METADATA_KEY,
    PendingImage,
    to_wire_metadata,
)
from src.domains.peers.constants import (
    PEER_IMAGE_TASK_TYPE,
    PEER_META_SENDER_ID,
    PEER_META_SENDER_NAME,
    PEER_UNKNOWN_DISPLAY_NAME,
)
from src.domains.peers.models import PeerConnectionStatus, PeerImageShare
from src.domains.peers.repository import PeersRepository, utc_day_bounds
from src.domains.shared.markdown_literal import literal_quote
from src.domains.users.models import User
from src.infrastructure.observability.metrics_registry import peers_image_shares_total

logger = structlog.get_logger(__name__)

#: Stable codes the web app translates (the ``peers_*`` contract).
NOT_SHAREABLE_CODE = "peers_image_not_shareable"
COMMENT_TOO_LONG_CODE = "peers_image_comment_too_long"
QUOTA_REACHED_CODE = "peers_image_quota_reached"
_NOT_CONNECTED_CODE = "peers_not_connected"


@dataclass(frozen=True)
class SharedImage:
    """A committed share: what the recipient's chat needs to show it.

    Attributes:
        share_id: The ledger row.
        sender_id: Who shared it.
        sender_display_name: Their name, as the recipient reads it.
        recipient_id: Who received the copy.
        recipient_display_name: Their name, for the sender's confirmation.
        attachment_id: The recipient's copy.
        url: Where the copy is served.
        title: What the image is called (its prompt).
        expires_at: When the copy's lifetime ends.
        comment: The sender's words, stripped; None when there were none.
    """

    share_id: uuid.UUID
    sender_id: uuid.UUID
    sender_display_name: str
    recipient_id: uuid.UUID
    recipient_display_name: str
    attachment_id: uuid.UUID
    url: str
    title: str
    expires_at: datetime
    comment: str | None


def _count(outcome: str) -> None:
    # Best-effort: a metric never decides a share.
    with suppress(Exception):
        peers_image_shares_total.labels(outcome=outcome).inc()


def _refuse(outcome: str, code: str) -> NoReturn:
    _count(outcome)
    raise_invalid_input(code)


def _clean_comment(comment: str | None) -> str | None:
    """The comment as the recipient will read it; blank means none.

    The request schema already bounds it; this is the same bound for any other
    caller, and a validation refusal rather than a share outcome.
    """
    stripped = (comment or "").strip()
    if len(stripped) > PEERS_IMAGE_SHARE_COMMENT_MAX_CHARS:
        raise_invalid_input(COMMENT_TOO_LONG_CODE)
    return stripped or None


async def _recipient_of(
    db: AsyncSession, repo: PeersRepository, sender_id: uuid.UUID, connection_id: uuid.UUID
) -> User:
    """The other side of an accepted, unblocked connection of the sender's."""
    connection = await repo.get_by_id(connection_id)
    if connection is None or sender_id not in (connection.user_a_id, connection.user_b_id):
        _count("not_connected")
        raise_not_found_or_unauthorized("peer", connection_id)
    if connection.status != PeerConnectionStatus.ACCEPTED.value:
        _refuse("not_connected", _NOT_CONNECTED_CODE)
    recipient_id = (
        connection.user_b_id if connection.user_a_id == sender_id else connection.user_a_id
    )
    recipient = await db.get(User, recipient_id)
    # A block either way, or an account that is gone, answers like no
    # connection at all: the sender learns nothing about the other side.
    if (
        recipient is None
        or not recipient.is_active
        or await repo.has_block_between(sender_id, recipient_id)
    ):
        _refuse("not_connected", _NOT_CONNECTED_CODE)
    return recipient


def _source_file(attachment: Attachment) -> Path:
    return Path(settings.attachments_storage_path) / attachment.file_path


async def _shareable_source(
    db: AsyncSession, sender_id: uuid.UUID, attachment_id: uuid.UUID, now: datetime
) -> Attachment:
    """The sender's own, live, generated image — or one refusal for every other case.

    Someone else's image, an upload, an expired one or one whose file is gone
    all answer the same code: the sender learns nothing about ids that are not
    theirs.
    """
    source = await AttachmentRepository(db).get_by_id(attachment_id)
    if (
        source is None
        or source.user_id != sender_id
        or source.origin != AttachmentOrigin.GENERATED_IMAGE.value
        or source.status != AttachmentStatus.READY
        or source.expires_at <= now
        or not await asyncio.to_thread(_source_file(source).is_file)
    ):
        _refuse("not_shareable", NOT_SHAREABLE_CODE)
    assert source is not None  # narrowed by the refusal above (NoReturn)
    return source


async def _hold_the_quota(
    db: AsyncSession, sender_id: uuid.UUID, recipient_id: uuid.UUID, now: datetime
) -> None:
    """Serialise this sender's shares, then refuse past either daily cap.

    The advisory lock is transaction-scoped: it is released by the commit that
    writes the share, so the next share counts it.
    """
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"peer_image_share:{sender_id}"},
    )
    start, end = utc_day_bounds(now)
    today = (
        PeerImageShare.sender_id == sender_id,
        PeerImageShare.created_at >= start,
        PeerImageShare.created_at < end,
    )
    total = await db.scalar(select(func.count(PeerImageShare.id)).where(*today))
    to_pair = await db.scalar(
        select(func.count(PeerImageShare.id)).where(
            *today, PeerImageShare.recipient_id == recipient_id
        )
    )
    caps = (
        (int(total or 0), settings.peers_image_share_max_per_day),
        (int(to_pair or 0), settings.peers_image_share_max_per_day_per_pair),
    )
    for used, cap in caps:
        if used >= cap:
            _count("quota")
            retry_after = max(1, int((end - now).total_seconds()))
            raise_rate_limit_exceeded(
                limit=cap,
                window_seconds=int(timedelta(days=1).total_seconds()),
                retry_after=retry_after,
                detail=QUOTA_REACHED_CODE,
                headers={"Retry-After": str(retry_after)},
            )


def _copy_file(source: Path, target: Path) -> None:
    """Disk work, off the event loop: the copy under the recipient's folder."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


async def _record(
    db: AsyncSession,
    *,
    source: Attachment,
    stored_filename: str,
    relative_path: str,
    sender_name: str,
    recipient_id: uuid.UUID,
    sender_id: uuid.UUID,
    connection_id: uuid.UUID,
    now: datetime,
) -> tuple[Attachment, PeerImageShare]:
    """The recipient's gallery row and the ledger row, in the caller's transaction."""
    copy = await AttachmentRepository(db).create(
        {
            "user_id": recipient_id,
            "original_filename": f"shared_{stored_filename}",
            "stored_filename": stored_filename,
            "mime_type": source.mime_type,
            "file_size": source.file_size,
            "file_path": relative_path,
            "content_type": AttachmentContentType.IMAGE,
            # Filed like an image they generated when it arrived (owner
            # request): the same gallery, a lifetime of its own.
            "origin": AttachmentOrigin.GENERATED_IMAGE.value,
            "title": source.title,
            "shared_by_name": sender_name,
            "status": AttachmentStatus.READY,
            "expires_at": now + timedelta(hours=settings.attachments_ttl_hours),
        }
    )
    share = PeerImageShare(
        connection_id=connection_id,
        sender_id=sender_id,
        recipient_id=recipient_id,
        attachment_id=copy.id,
    )
    db.add(share)
    await db.flush()
    return copy, share


async def share_image(
    db: AsyncSession,
    *,
    sender_id: uuid.UUID,
    connection_id: uuid.UUID,
    attachment_id: uuid.UUID,
    comment: str | None,
) -> SharedImage:
    """Copy one of the sender's generated images into a connection's gallery.

    Args:
        db: The request session — committed here.
        sender_id: Who shares.
        connection_id: The accepted connection it travels on.
        attachment_id: The sender's generated image.
        comment: Optional words for the recipient, quoted literally in their chat.

    Returns:
        The committed share, with what the recipient's chat needs.

    Raises:
        BaseAPIException: 404 for a connection the sender is not part of; 400
            ``peers_not_connected`` (not accepted, blocked, account gone),
            ``peers_image_not_shareable`` or ``peers_image_comment_too_long``;
            429 ``peers_image_quota_reached`` with ``Retry-After``.
    """
    now = datetime.now(UTC)
    words = _clean_comment(comment)
    repo = PeersRepository(db)
    recipient = await _recipient_of(db, repo, sender_id, connection_id)
    source = await _shareable_source(db, sender_id, attachment_id, now)
    sender = await db.get(User, sender_id)
    sender_name = (sender.full_name if sender else None) or PEER_UNKNOWN_DISPLAY_NAME
    await _hold_the_quota(db, sender_id, recipient.id, now)

    stored_filename = f"{uuid.uuid4()}{Path(source.stored_filename).suffix}"
    relative_path = f"{recipient.id}/{stored_filename}"
    target = Path(settings.attachments_storage_path) / relative_path
    try:
        await asyncio.to_thread(_copy_file, _source_file(source), target)
        copy, share = await _record(
            db,
            source=source,
            stored_filename=stored_filename,
            relative_path=relative_path,
            sender_name=sender_name,
            recipient_id=recipient.id,
            sender_id=sender_id,
            connection_id=connection_id,
            now=now,
        )
        await db.commit()
    except Exception as exc:
        # A copy nobody's row points at would outlive every sweep: withdraw it.
        await db.rollback()
        await asyncio.to_thread(target.unlink, True)
        _count("failed")
        logger.warning(
            "peer_image_share_failed",
            sender_id=str(sender_id),
            connection_id=str(connection_id),
            error_type=type(exc).__name__,
        )
        raise

    _count("shared")
    logger.info(
        "peer_image_shared",
        share_id=str(share.id),
        sender_id=str(sender_id),
        recipient_id=str(recipient.id),
        has_comment=words is not None,
    )
    return SharedImage(
        share_id=share.id,
        sender_id=sender_id,
        sender_display_name=sender_name,
        recipient_id=recipient.id,
        recipient_display_name=recipient.full_name or PEER_UNKNOWN_DISPLAY_NAME,
        attachment_id=copy.id,
        url=attachment_url(copy.id),
        title=copy.title or "",
        expires_at=copy.expires_at,
        comment=words,
    )


def shared_image_body(shared: SharedImage, language: str) -> str:
    """What the recipient's chat says above the image.

    Args:
        shared: The committed share.
        language: The recipient's language.

    Returns:
        The localized line, then the sender's comment as a literal quote.
    """
    line = ProactiveMessages.peer_image_shared_body(shared.sender_display_name, language)
    if shared.comment is None:
        return line
    return f"{line}\n\n{literal_quote(shared.comment)}"


async def deliver_shared_image(shared: SharedImage) -> bool:
    """Show a shared image in the recipient's chat — best-effort, never raises.

    The same card as an image LIA generated for them (one wire shape,
    ``to_wire_metadata``), on a proactive bubble the chat tints as a peer's,
    with the reply and block actions of a relayed message.

    Args:
        shared: The committed share.

    Returns:
        Whether any road (archive, live event, push) delivered it.
    """
    from src.infrastructure.database import get_db_context
    from src.infrastructure.proactive.notification import NotificationDispatcher

    card = PendingImage(
        url=shared.url, alt_text=shared.title, expires_at=shared.expires_at.isoformat()
    )
    try:
        async with get_db_context() as db:
            recipient = await db.get(User, shared.recipient_id)
            if recipient is None:
                return False
            result = await NotificationDispatcher().dispatch(
                user=recipient,
                content=shared_image_body(shared, recipient.language),
                task_type=PEER_IMAGE_TASK_TYPE,
                target_id=str(shared.share_id),
                metadata={
                    PEER_META_SENDER_ID: str(shared.sender_id),
                    PEER_META_SENDER_NAME: shared.sender_display_name,
                    GENERATED_IMAGES_METADATA_KEY: to_wire_metadata([card]),
                },
                db=db,
                title=ProactiveMessages.notification_title(
                    PEER_IMAGE_TASK_TYPE, recipient.language
                ),
            )
    except Exception as exc:  # noqa: BLE001 — the image is in their gallery already
        logger.warning(
            "peer_image_delivery_failed",
            share_id=str(shared.share_id),
            error_type=type(exc).__name__,
        )
        return False
    return result.success


__all__ = [
    "COMMENT_TOO_LONG_CODE",
    "NOT_SHAREABLE_CODE",
    "QUOTA_REACHED_CODE",
    "SharedImage",
    "deliver_shared_image",
    "share_image",
    "shared_image_body",
]
