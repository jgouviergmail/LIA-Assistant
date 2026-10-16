"""How an Apple (IMAP/SMTP) message is composed — for a send and a draft alike (ADR-344).

iCloud has no draft API: a draft is a message APPENDed to the drafts folder,
and sending it is SMTP. So the message a draft holds must be the message the
send would have built, and one composition serves both. What a reply or a
forward SAYS is decided once for every hand-built composition
(``email_compose``); this module builds the MIME message.

Every recipient header is written by ``encode_recipients``: assigned raw, a
display name outside ASCII made the email package encode the WHOLE header,
addresses included — the reader saw a name and no address. A draft keeps its
``Bcc`` header (the person must see whom it will blind-copy); the send takes it
off the message and into the envelope (``mailbox_drafts.prepare_for_smtp``).
"""

from __future__ import annotations

from collections.abc import Sequence
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import Any

from src.domains.connectors.clients.email_compose import (
    forward_subject,
    forwarded_body,
    quoted_reply,
    reply_recipients,
    reply_subject,
)
from src.infrastructure.email.outgoing import OutgoingAttachment, attachment_part
from src.infrastructure.email.recipients import encode_recipients

__all__ = ["forward_message", "new_message", "reply_message"]


def _headed(
    *, sender: str, to: str, subject: str, cc: str | None = None, bcc: str | None = None
) -> MIMEMultipart:
    """An empty message with its headers: a draft is dated and identified like a send."""
    message = MIMEMultipart()
    message["From"] = sender
    if to:
        message["To"] = encode_recipients(to)
    message["Subject"] = subject
    if cc:
        message["Cc"] = encode_recipients(cc)
    if bcc:
        message["Bcc"] = encode_recipients(bcc)
    message["Date"] = formatdate(usegmt=True)
    # The sender's own domain: the default asks the host its name, a DNS wait
    # that also names the container.
    message["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or None)
    return message


def _text(body: str, *, is_html: bool) -> MIMEText:
    return MIMEText(body, "html" if is_html else "plain", "utf-8")


def new_message(
    *,
    sender: str,
    to: str,
    subject: str,
    body: str,
    cc: str | None = None,
    bcc: str | None = None,
    is_html: bool = False,
    attachments: Sequence[OutgoingAttachment] = (),
) -> MIMEMultipart:
    """A new message; an empty ``to`` leaves the recipient for later (a draft).

    Raises:
        ValueError: A recipient that cannot be read.
    """
    message = _headed(sender=sender, to=to, subject=subject, cc=cc, bcc=bcc)
    message.attach(_text(body, is_html=is_html))
    for attachment in attachments:
        message.attach(attachment_part(attachment))
    return message


def reply_message(
    original: dict[str, Any],
    body: str,
    *,
    sender: str,
    reply_all: bool = False,
    is_html: bool = False,
    override_to: str | None = None,
) -> MIMEMultipart:
    """The reply to a normalised message, threaded on its ``Message-ID``.

    Args:
        original: The message in the ``EmailMessage`` vocabulary.
        body: The reply's own words.
        sender: The mailbox's address (never answered, never copied).
        reply_all: Answer every recipient of the original.
        is_html: Whether ``body`` is HTML (an HTML reply quotes nothing).
        override_to: A recipient chosen instead of the answered ones.

    Raises:
        ValueError: A recipient that cannot be read.
    """
    original_from = str(original.get("from") or "")
    to, cc = reply_recipients(
        original_from,
        str(original.get("to") or ""),
        str(original.get("cc") or ""),
        own_address=sender,
        reply_all=reply_all,
        override_to=override_to,
        reply_to=str(original.get("reply_to") or ""),
    )
    message = _headed(
        sender=sender,
        to=to,
        subject=reply_subject(str(original.get("subject") or "")),
        cc=cc or None,
    )
    rfc_message_id = original.get("rfc_message_id")
    if rfc_message_id:
        message["In-Reply-To"] = rfc_message_id
        message["References"] = rfc_message_id
    full_body = quoted_reply(
        body,
        str(original.get("body") or ""),
        date=str(original.get("date") or ""),
        sender=original_from,
        is_html=is_html,
    )
    message.attach(_text(full_body, is_html=is_html))
    return message


def forward_message(
    original: dict[str, Any],
    files: Sequence[OutgoingAttachment],
    *,
    sender: str,
    to: str,
    body: str | None = None,
    cc: str | None = None,
    is_html: bool = False,
) -> MIMEMultipart:
    """The forward of a normalised message, its files carried along.

    Raises:
        ValueError: A recipient that cannot be read.
    """
    original_subject = str(original.get("subject") or "")
    message = _headed(sender=sender, to=to, subject=forward_subject(original_subject), cc=cc)
    full_body = forwarded_body(
        body,
        str(original.get("body") or ""),
        sender=str(original.get("from") or ""),
        date=str(original.get("date") or ""),
        subject=original_subject,
        to=str(original.get("to") or ""),
    )
    message.attach(_text(full_body, is_html=is_html))
    for file in files:
        message.attach(attachment_part(file))
    return message
