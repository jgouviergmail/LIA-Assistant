"""What every e-mail provider shares about a draft in the person's MAILBOX (ADR-344).

A mailbox draft is the person's own unsent message, stored by the provider —
never the confirmation card LIA builds before an action (``DraftType``). Its
handle is ``mailbox_draft_id``: Gmail's draft resource id, the message id on
Graph, a scoped account/folder/UIDVALIDITY handle on IMAP.

Gmail replaces a draft's whole message on update and IMAP stores a new one, so
an edit rebuilt from the visible fields alone would drop the files a forward
carries and the headers that keep a reply in its thread. :func:`edit_draft_message`
rewrites the RAW message instead: the fields given change, everything else stays.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from typing import Any, Final

import structlog

from src.core.exceptions import ConnectorAPIError
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID, FIELD_MAILBOX_DRAFT_REVISION
from src.infrastructure.email.recipients import parse_recipients

logger = structlog.get_logger(__name__)

#: Headers whose value is replaced when an edit names them.
_EDITABLE_HEADERS = ("To", "Cc", "Bcc", "Subject")

#: Headers that describe the body, rebuilt when the body changes.
_BODY_HEADERS = frozenset({"content-type", "content-transfer-encoding", "mime-version"})

#: What became of a draft a batch did not trash — a closed vocabulary the tool
#: layer reads, member by member.
TRASH_NOT_FOUND: Final = "not_found"  # not in the mailbox: sent, deleted, already trashed
TRASH_REFUSED: Final = "refused"  # the provider refused this draft
TRASH_UNAVAILABLE: Final = "unavailable"  # the mailbox stopped answering before it
TRASH_FAILURE_STATUSES: Final = frozenset({TRASH_NOT_FOUND, TRASH_REFUSED, TRASH_UNAVAILABLE})


class MailboxDraftNotFoundError(LookupError):
    """The draft is not in the mailbox: sent, deleted, or never there."""


class MailboxDraftChangedError(LookupError):
    """The live draft no longer matches the version an edit was based on."""

    def __init__(self, message: str = "The draft changed.", *, copy_saved: bool = False) -> None:
        super().__init__(message)
        self.copy_saved = copy_saved


def ensure_draft_revision(draft: dict[str, Any], expected: str | None) -> None:
    """Refuse a stale transformation before writing; legacy calls without one stay valid."""
    if expected is not None and draft.get(FIELD_MAILBOX_DRAFT_REVISION) != expected:
        raise MailboxDraftChangedError("The draft changed before the edit: read it again.")


class MailboxFolderUnavailableError(LookupError):
    """The mailbox has no folder for a role a draft needs (drafts, trash, sent)."""


class MailboxOperationUnavailableError(LookupError):
    """The server cannot perform a mailbox operation without affecting other messages."""


def parse_message(raw: bytes) -> EmailMessage:
    """Parse RFC 822 bytes into an ``EmailMessage`` (modern policy).

    Args:
        raw: The message as the provider stores it.

    Returns:
        The parsed message.
    """
    return BytesParser(_class=EmailMessage, policy=policy.default).parsebytes(raw)


def edit_draft_message(
    raw: bytes,
    *,
    to: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> EmailMessage:
    """A draft rebuilt with the fields given, and everything else kept.

    A header given replaces its value, and an empty one removes the header. A
    body given becomes the plain-text body, after which the files and every
    other header (``In-Reply-To``, ``References``…) are those of the original:
    an HTML draft loses its formatting when its body is rewritten, never its
    files. A field not given is not touched — editing a recipient leaves the
    body byte for byte.

    Args:
        raw: The draft as the provider stores it.
        to: New ``To`` value, or None to keep it.
        cc: New ``Cc`` value, or None to keep it.
        bcc: New ``Bcc`` value, or None to keep it.
        subject: New subject, or None to keep it.
        body: New plain-text body, or None to keep it.

    Returns:
        The edited message.
    """
    message = parse_message(raw)
    if body is not None:
        message = _with_body(message, body)
    for name, value in zip(_EDITABLE_HEADERS, (to, cc, bcc, subject), strict=True):
        if value is None:
            continue
        del message[name]
        if value:
            message[name] = value
    return message


def _with_body(message: EmailMessage, body: str) -> EmailMessage:
    """The message with a new plain-text body, its headers and files kept."""
    files = list(message.iter_attachments()) if message.is_multipart() else []
    rebuilt = EmailMessage(policy=policy.default)
    for name, value in message.items():
        if name.lower() not in _BODY_HEADERS:
            rebuilt[name] = value
    # Seven bits on every road (Gmail's upload, an IMAP APPEND, SMTP): left to
    # itself, the modern policy writes accented text as raw 8-bit bytes.
    rebuilt.set_content(body, cte="quoted-printable")
    if files:
        rebuilt.make_mixed()
        for part in files:
            rebuilt.attach(part)
    return rebuilt


def prepare_for_smtp(message: Message) -> list[str]:
    """The envelope recipients of a message about to leave by SMTP, its ``Bcc`` removed.

    The blind copies are recipients of the envelope and never a header of the
    message: a ``Bcc`` line left in would show every recipient who was hidden.
    One rule for a message composed to be sent and for a draft read back from
    the mailbox. The headers are read as STORED (the ``compat32`` policy a
    composed message and ``email.message_from_bytes`` use): the modern policy
    re-reads ``a@x.com; b@x.com`` as one address and loses the second.

    Args:
        message: The message, ``compat32``; its ``Bcc`` header is deleted.

    Returns:
        Every address of ``To``, ``Cc`` and ``Bcc``, each once, in order.

    Raises:
        ValueError: A recipient that cannot be read.
    """
    recipients: dict[str, str] = {}
    for header in ("To", "Cc", "Bcc"):
        for value in message.get_all(header, []):
            for _name, address in parse_recipients(str(value)):
                recipients.setdefault(address.casefold(), address)
    del message["Bcc"]
    return list(recipients.values())


async def trash_each(
    draft_ids: Sequence[str], trash_one: Callable[[str], Awaitable[None]]
) -> dict[str, Any]:
    """Trash drafts one at a time, and say what became of each.

    A draft missing from the mailbox is ``not_found``, one the provider refused
    is ``refused``. Any other failure is the mailbox's, not the draft's — it
    stops the batch: raised when nothing was trashed yet (the caller reports
    it like any other failed call), otherwise the drafts from that one on are
    ``unavailable``, because a raise would hide the drafts already in the trash.
    A draft named twice is handled once.

    Args:
        draft_ids: The ``mailbox_draft_id`` of each draft.
        trash_one: Moves one draft to the trash; raises
            ``MailboxDraftNotFoundError`` when it is not in the mailbox.

    Returns:
        ``{"trashed": [ids], "failed": [{"mailbox_draft_id", "status"}]}``.
    """
    pending = list(dict.fromkeys(draft_ids))
    trashed: list[str] = []
    failed: list[dict[str, str]] = []
    for index, draft_id in enumerate(pending):
        try:
            await trash_one(draft_id)
        except MailboxDraftNotFoundError:
            failed.append({FIELD_MAILBOX_DRAFT_ID: draft_id, "status": TRASH_NOT_FOUND})
        except ConnectorAPIError:
            failed.append({FIELD_MAILBOX_DRAFT_ID: draft_id, "status": TRASH_REFUSED})
        except Exception as error:
            if not trashed:
                raise
            logger.warning(
                "mailbox_drafts_trash_interrupted",
                trashed=len(trashed),
                not_attempted=len(pending) - index,
                error_type=type(error).__name__,
            )
            failed.extend(
                {FIELD_MAILBOX_DRAFT_ID: rest, "status": TRASH_UNAVAILABLE}
                for rest in pending[index:]
            )
            break
        else:
            trashed.append(draft_id)
    return {"trashed": trashed, "failed": failed}


__all__ = [
    "TRASH_FAILURE_STATUSES",
    "TRASH_NOT_FOUND",
    "TRASH_REFUSED",
    "TRASH_UNAVAILABLE",
    "MailboxDraftNotFoundError",
    "MailboxDraftChangedError",
    "MailboxFolderUnavailableError",
    "MailboxOperationUnavailableError",
    "edit_draft_message",
    "ensure_draft_revision",
    "parse_message",
    "prepare_for_smtp",
    "trash_each",
]
