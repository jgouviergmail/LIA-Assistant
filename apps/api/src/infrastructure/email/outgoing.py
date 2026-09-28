"""One outgoing e-mail carrying a file, for every road that speaks MIME (ADR-321).

A person may send a file LIA generated, or an answer as the ``.md`` file
« Download » writes, by e-mail — through their own mailbox (Gmail, Apple,
Outlook) or, without one, through LIA's relay to their own verified address.
Gmail (raw RFC 822), Apple (SMTP) and the relay (SMTP) all send MIME, so the
file part is built HERE once; Outlook's Graph speaks JSON and reads the same
:class:`OutgoingAttachment`.

Each provider limits the MESSAGE, while a person thinks in FILES: the largest
file a road accepts is derived from its message limit by
:func:`max_file_bytes` — base64 lines plus an envelope headroom — so a limit is
written once, where the provider documents it, and never re-typed as a file
size that could drift from it.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass
from email import encoders
from email.message import Message
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from typing import Final

__all__ = [
    "MESSAGE_ENVELOPE_HEADROOM_BYTES",
    "OutgoingAttachment",
    "attachment_part",
    "encoded_size",
    "max_file_bytes",
    "plain_text_bodies",
    "with_attachments",
]

#: Base64 writes 76 characters per line for 57 source bytes, then CRLF.
_LINE_SOURCE_BYTES: Final = 57
_LINE_WIRE_BYTES: Final = 76 + 2

#: What a message carries besides its file: headers, the typed body (bounded
#: by the request schema), the MIME boundaries — generously rounded up.
MESSAGE_ENVELOPE_HEADROOM_BYTES: Final = 64 * 1024

_FALLBACK_TYPE: Final = ("application", "octet-stream")


@dataclass(frozen=True, slots=True)
class OutgoingAttachment:
    """A file to send, as its bytes.

    Attributes:
        filename: The name the reader sees (any script: it is RFC 2231-encoded).
        mime_type: ``type/subtype``; anything else is sent as bytes.
        data: The file's bytes.
        charset: The text encoding, for a ``text/*`` file.
    """

    filename: str
    mime_type: str
    data: bytes
    charset: str | None = None


def encoded_size(raw_bytes: int) -> int:
    """How many bytes a file occupies on the wire once base64-encoded.

    Args:
        raw_bytes: The file's size.

    Returns:
        Its size as whole base64 lines ended by CRLF — exact for a file that
        fills its last line, an upper bound otherwise.
    """
    lines = -(-raw_bytes // _LINE_SOURCE_BYTES)
    return lines * _LINE_WIRE_BYTES


def max_file_bytes(message_max_bytes: int) -> int:
    """The largest file a message limit leaves room for.

    Args:
        message_max_bytes: What the road accepts for a whole message.

    Returns:
        The largest file whose encoded form, plus the envelope headroom, fits.
    """
    usable = message_max_bytes - MESSAGE_ENVELOPE_HEADROOM_BYTES
    return max(0, usable // _LINE_WIRE_BYTES * _LINE_SOURCE_BYTES)


def attachment_part(attachment: OutgoingAttachment) -> MIMEBase:
    """The MIME part of one file: base64, named, offered as an attachment.

    Args:
        attachment: The file.

    Returns:
        The part, ready to attach to a ``multipart/mixed`` message.
    """
    maintype, _, subtype = attachment.mime_type.partition("/")
    if not maintype or not subtype or "/" in subtype:
        maintype, subtype = _FALLBACK_TYPE
    part = MIMEBase(maintype, subtype)
    if attachment.charset:
        part.set_param("charset", attachment.charset)
    part.set_payload(attachment.data)
    encoders.encode_base64(part)
    # A non-ASCII name is written as an RFC 2231 parameter by the email package.
    part.add_header("Content-Disposition", "attachment", filename=attachment.filename)
    return part


def plain_text_bodies(text: str) -> tuple[str, str]:
    """The HTML and plain alternatives of text that is not markup.

    The text is ESCAPED into its HTML part: words a person typed, or a model
    wrote, never become markup in someone's mail client.

    Args:
        text: The plain text.

    Returns:
        ``(html_body, text_body)``.
    """
    escaped = html.escape(text)
    return f'<pre style="white-space:pre-wrap;font-family:inherit">{escaped}</pre>', text


def with_attachments(body: Message, attachments: Sequence[OutgoingAttachment]) -> Message:
    """The message to send: ``body`` alone, or ``body`` first then the files.

    Args:
        body: The typed part (plain, HTML, or an ``alternative`` of both).
        attachments: The files, possibly none.

    Returns:
        ``body`` itself when there is nothing to attach — a message without a
        file is built exactly as before — else a ``multipart/mixed`` holding it.
    """
    if not attachments:
        return body
    message = MIMEMultipart("mixed")
    message.attach(body)
    for attachment in attachments:
        message.attach(attachment_part(attachment))
    return message
