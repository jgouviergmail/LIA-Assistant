"""Send a generated file or an answer by e-mail (ADR-321).

A person sends, from the chat or the gallery, an image, a document or a
capture LIA generated — or an answer, as the very ``.md`` file « Download »
writes — with a subject and, if they want, a few words. Three decisions taken
elsewhere are followed here, not re-decided:

- **The click is the confirmation** (ADR-316's precedent): the dialog's send
  button is the person's explicit act, so no draft is built and no model is
  called — nothing is written in their place, the body is their words or
  nothing.
- **The road**: the connected mailbox, to any recipient; without one, LIA's
  relay to the account's own address, and only when that address is VERIFIED
  (ADR-314's rule — an account opened with someone else's address must not turn
  the relay into a relay aimed at them). A broken mailbox is said, and the
  relay serves meanwhile.
- **No transaction across a network call** (ADR-304): :func:`prepare_share`
  reads and checks, the caller commits, then :func:`deliver_share` reads the
  file from disk and sends — the mailbox through ``open_active_client``, which
  holds no session of its caller's.

Each road publishes the largest file it carries, DERIVED from what its provider
documents (``OUTGOING_FILE_MAX_BYTES``, ``max_file_bytes``): a file past it is
refused before anything leaves, with the ceiling in the refusal.
"""

from __future__ import annotations

import asyncio
import smtplib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    EMAIL_SHARE_MAX_RECIPIENTS,
    EMAIL_SHARE_MESSAGE_MAX_CHARS,
    EMAIL_SHARE_RECIPIENT_QUERY_MIN_CHARS,
    EMAIL_SHARE_RECIPIENT_SUGGESTIONS_MAX,
    EMAIL_SHARE_SUBJECT_MAX_CHARS,
)
from src.core.exceptions import AuthenticationError, ConnectorAPIError
from src.domains.attachments.models import Attachment, AttachmentStatus
from src.domains.attachments.origin import GENERATED_ORIGINS
from src.domains.connectors.active_client import ClientUnavailable, open_active_client
from src.domains.connectors.clients.base_apple_client import AppleAuthenticationError
from src.domains.connectors.clients.protocols import OutgoingCeiling
from src.domains.connectors.clients.registry import ClientRegistry
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.provider_resolver import (
    find_error_connector_type,
    resolve_active_connector,
)
from src.domains.connectors.session_scope import DetachedConnectorService
from src.domains.email_share import errors
from src.domains.email_share.schemas import (
    EmailShareOptions,
    EmailShareRequest,
    EmailShareResult,
    SharedMarkdown,
    ShareRouteKind,
)
from src.domains.shared.action_sink import EMAIL_SHARE_CAPABILITY, recorded_action
from src.domains.users.models import User
from src.infrastructure.email.email_service import get_email_service
from src.infrastructure.email.outgoing import OutgoingAttachment, max_file_bytes, plain_text_bodies

logger = structlog.get_logger(__name__)

_EMAIL_CATEGORY: Final = "email"
_GENERATED_VALUES: Final = sorted(origin.value for origin in GENERATED_ORIGINS)
_MARKDOWN_TYPE: Final = "text/markdown"


@dataclass(frozen=True, slots=True)
class ShareRoute:
    """The road a send takes, and what it carries.

    Attributes:
        kind: ``mailbox``, ``relay`` or ``unavailable``.
        connector_type: The connected mailbox, on the mailbox road.
        own_address: The one recipient of the relay road.
        needs_reconnect: A mailbox is connected but broken.
        max_file_bytes: The largest file the road carries.
    """

    kind: Literal["mailbox", "relay", "unavailable"]
    connector_type: ConnectorType | None = None
    own_address: str | None = None
    needs_reconnect: bool = False
    max_file_bytes: int | None = None

    @classmethod
    def mailbox(cls, connector_type: ConnectorType, *, max_file_bytes: int | None) -> ShareRoute:
        """The connected mailbox, to any recipient."""
        return cls("mailbox", connector_type=connector_type, max_file_bytes=max_file_bytes)

    @classmethod
    def relay(
        cls, own_address: str, *, max_file_bytes: int, needs_reconnect: bool = False
    ) -> ShareRoute:
        """LIA's relay, to the account's own verified address alone."""
        return cls(
            "relay",
            own_address=own_address,
            needs_reconnect=needs_reconnect,
            max_file_bytes=max_file_bytes,
        )

    @classmethod
    def unavailable(cls, *, needs_reconnect: bool = False) -> ShareRoute:
        """No mailbox, and no verified address to relay to."""
        return cls("unavailable", needs_reconnect=needs_reconnect)

    @property
    def label(self) -> str:
        """How the metric names the road."""
        return "none" if self.kind == "unavailable" else self.kind


@dataclass(frozen=True, slots=True)
class StoredFile:
    """One of the person's generated files, read from disk only when sent."""

    path: Path
    filename: str
    mime_type: str
    size: int

    async def read(self) -> OutgoingAttachment:
        """The file's bytes, off the event loop.

        Raises:
            FileNotFoundError: The cleanup removed it since it was checked.
        """
        data = await asyncio.to_thread(self.path.read_bytes)
        return OutgoingAttachment(self.filename, self.mime_type, data)


@dataclass(frozen=True, slots=True)
class InlineFile:
    """A file the request itself carries: an answer as Markdown."""

    attachment: OutgoingAttachment

    @property
    def size(self) -> int:
        """The file's size in bytes."""
        return len(self.attachment.data)

    async def read(self) -> OutgoingAttachment:
        """The file, as it came."""
        return self.attachment


@dataclass(frozen=True, slots=True)
class PreparedShare:
    """A send that passed every check, ready to leave."""

    route: ShareRoute
    recipients: list[str]
    subject: str
    message: str | None
    source: StoredFile | InlineFile


async def resolve_route(user: User) -> ShareRoute:
    """Which road a send takes for this account, right now.

    Reads the connectors on a short session of its own (Redis-cached), never on
    the caller's.

    Args:
        user: The account.

    Returns:
        The road, with the largest file it carries.
    """
    async with DetachedConnectorService().unit_of_work() as connectors:
        active = await resolve_active_connector(user.id, _EMAIL_CATEGORY, connectors)
        broken = (
            None
            if active is not None
            else await find_error_connector_type(user.id, _EMAIL_CATEGORY, connectors)
        )
    if active is not None:
        client_class = ClientRegistry.get_client_class(active)
        ceiling = (
            client_class.OUTGOING_FILE_MAX_BYTES
            if isinstance(client_class, OutgoingCeiling)
            else None
        )
        return ShareRoute.mailbox(active, max_file_bytes=ceiling)
    if user.is_verified and user.email:
        return ShareRoute.relay(
            user.email,
            max_file_bytes=max_file_bytes(settings.email_share_relay_max_message_bytes),
            needs_reconnect=broken is not None,
        )
    return ShareRoute.unavailable(needs_reconnect=broken is not None)


def options_for(route: ShareRoute, *, contacts_connected: bool) -> EmailShareOptions:
    """What the dialog may offer on this road — every bound it will meet.

    Args:
        route: The account's road.
        contacts_connected: A contacts connector is active. Suggestions are
            offered only where recipients are free: the relay's one recipient
            is locked, so nothing would be typed.

    Returns:
        The published options.
    """
    return EmailShareOptions(
        route=route.kind,
        own_address=route.own_address,
        mailbox_needs_reconnect=route.needs_reconnect,
        max_file_bytes=route.max_file_bytes,
        max_recipients=EMAIL_SHARE_MAX_RECIPIENTS,
        subject_max_chars=EMAIL_SHARE_SUBJECT_MAX_CHARS,
        message_max_chars=EMAIL_SHARE_MESSAGE_MAX_CHARS,
        recipient_suggestions=route.kind == "mailbox" and contacts_connected,
        recipient_query_min_chars=EMAIL_SHARE_RECIPIENT_QUERY_MIN_CHARS,
        recipient_suggestions_max=EMAIL_SHARE_RECIPIENT_SUGGESTIONS_MAX,
    )


def _recipients(route: ShareRoute, requested: list[str]) -> list[str]:
    """Whom this road may reach, each once (compared without case)."""
    unique: dict[str, str] = {}
    for address in requested:
        unique.setdefault(address.casefold(), address)
    if route.kind == "relay" and route.own_address is not None:
        own = route.own_address.casefold()
        if any(key != own for key in unique):
            errors.refuse(errors.RECIPIENTS_LOCKED, route=route.label)
        return [route.own_address]
    if not unique:
        errors.refuse(errors.NO_RECIPIENT, route=route.label)
    return list(unique.values())


async def _source(
    db: AsyncSession, user_id: uuid.UUID, request: EmailShareRequest, route: ShareRoute
) -> StoredFile | InlineFile:
    """What is sent: the answer as its `.md` file, or a live generated file."""
    attachment = request.attachment
    if isinstance(attachment, SharedMarkdown):
        return InlineFile(
            OutgoingAttachment(
                filename=f"{attachment.filename}.md",
                mime_type=_MARKDOWN_TYPE,
                data=attachment.text.encode("utf-8"),
                charset="utf-8",
            )
        )
    # The person's own generated file (never an upload), not past its deadline:
    # the card of an expired file offers nothing, and the cleanup is about to
    # take it. A kept file has no deadline.
    row = (
        await db.execute(
            select(
                Attachment.file_path,
                Attachment.original_filename,
                Attachment.mime_type,
                Attachment.file_size,
            ).where(
                Attachment.id == attachment.attachment_id,
                Attachment.user_id == user_id,
                Attachment.origin.in_(_GENERATED_VALUES),
                Attachment.status != AttachmentStatus.EXPIRED,
                or_(Attachment.expires_at.is_(None), Attachment.expires_at > datetime.now(UTC)),
            )
        )
    ).first()
    if row is None:
        errors.refuse(errors.FILE_GONE, route=route.label)
    return StoredFile(
        path=Path(settings.attachments_storage_path) / row.file_path,
        filename=row.original_filename,
        mime_type=row.mime_type,
        size=int(row.file_size),
    )


async def prepare_share(
    db: AsyncSession, user: User, request: EmailShareRequest, route: ShareRoute
) -> PreparedShare:
    """Check a send against its road before anything leaves.

    Args:
        db: The request session (read only; the caller commits before sending).
        user: The account.
        request: What the dialog asked for.
        route: The account's road (:func:`resolve_route`).

    Returns:
        The send, ready for :func:`deliver_share`.

    Raises:
        BaseAPIException: A coded refusal (no road, recipients, file, size).
    """
    if route.kind == "unavailable":
        errors.refuse(errors.UNAVAILABLE, route=route.label)
    recipients = _recipients(route, list(request.recipients))
    source = await _source(db, user.id, request, route)
    if route.max_file_bytes is not None and source.size > route.max_file_bytes:
        errors.refuse(errors.TOO_LARGE, route=route.label, max_bytes=route.max_file_bytes)
    return PreparedShare(
        route=route,
        recipients=recipients,
        subject=request.subject,
        message=request.message,
        source=source,
    )


async def _send_from_mailbox(
    user_id: uuid.UUID, prepared: PreparedShare, attachment: OutgoingAttachment
) -> None:
    """Send through the connected mailbox; every failure becomes what it is."""
    async with open_active_client(_EMAIL_CATEGORY, user_id) as opened:
        if isinstance(opened, ClientUnavailable):
            errors.refuse(errors.UNAVAILABLE, route="mailbox")
        provider = opened.connector_type.value
        try:
            await opened.client.send_email(
                to=", ".join(prepared.recipients),
                subject=prepared.subject,
                body=prepared.message or "",
                attachments=[attachment],
            )
        except AuthenticationError, AppleAuthenticationError:
            errors.refuse(errors.RECONNECT, route="mailbox")
        except (ConnectorAPIError, smtplib.SMTPException) as exc:
            logger.warning(
                "email_share_mailbox_refused",
                connector_type=provider,
                error_type=type(exc).__name__,
                status_code=exc.status_code if isinstance(exc, ConnectorAPIError) else None,
            )
            errors.refuse(errors.REFUSED, route="mailbox")
        except Exception as exc:  # noqa: BLE001 — anything else: the mailbox was not reached
            logger.warning(
                "email_share_mailbox_failed",
                connector_type=provider,
                error_type=type(exc).__name__,
            )
            errors.refuse(errors.FAILED, route="mailbox")


async def _send_from_relay(prepared: PreparedShare, attachment: OutgoingAttachment) -> None:
    """Send through LIA's relay, to the account's own verified address."""
    html_body, text_body = plain_text_bodies(prepared.message or "")
    sent = await get_email_service().send_email(
        prepared.recipients[0],
        prepared.subject,
        html_body,
        text_body,
        attachments=[attachment],
    )
    if not sent:
        errors.refuse(errors.FAILED, route="relay")


async def deliver_share(user_id: uuid.UUID, prepared: PreparedShare) -> EmailShareResult:
    """Send a prepared share — no database session is held by this function.

    Args:
        user_id: The account.
        prepared: What :func:`prepare_share` returned (and the caller committed).

    Returns:
        Where it left from, and to how many addresses.

    Raises:
        BaseAPIException: A coded refusal (file gone meanwhile, the road failed).
    """
    route = prepared.route
    if route.kind == "unavailable":
        errors.refuse(errors.UNAVAILABLE, route=route.label)
    kind: ShareRouteKind = "mailbox" if route.kind == "mailbox" else "relay"
    try:
        attachment = await prepared.source.read()
    except FileNotFoundError:
        errors.refuse(errors.FILE_GONE, route=kind)
    # The person's act, in the action register (ADR-263): claimed before the
    # message leaves, settled from what the provider answered. How many it was
    # written to is a fact; the addresses and the words are the person's.
    async with recorded_action(
        user_id=user_id,
        capability=EMAIL_SHARE_CAPABILITY,
        arguments={"count": str(len(prepared.recipients))},
    ) as act:
        if kind == "mailbox":
            await _send_from_mailbox(user_id, prepared, attachment)
        else:
            await _send_from_relay(prepared, attachment)
        act.succeeded = True
    errors.count(kind, "sent")
    # Facts only: the addresses, the subject and the words are the person's.
    logger.info(
        "email_share_sent",
        user_id=str(user_id),
        route=kind,
        recipients=len(prepared.recipients),
        size=len(attachment.data),
        source="answer" if isinstance(prepared.source, InlineFile) else "file",
    )
    return EmailShareResult(route=kind, recipients=len(prepared.recipients))
