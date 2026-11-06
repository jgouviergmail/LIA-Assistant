"""What an e-mail written by the assistant carries (ADR-369, lot 7, D2, A3).

What the screen's composer attaches reaches the assistant through the same doors: a file
LIA holds, named as the person knows it, and a file of their drive, by its id. The card
names them before anything leaves, read here; the send reads what the person confirmed,
and a file gone since stops the message, which leaves whole or not at all (``mail_files``).
The person's signature joins the body the card shows, where they can read and change it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from fastapi import status

from src.core.constants import WORKBENCH_MAIL_ATTACHMENTS_MAX
from src.core.exceptions import ConnectorAPIError
from src.domains.agents.tools.exceptions import EmailValidationError
from src.domains.attachments.attachable_queries import build_attachable_statement
from src.domains.connectors.active_client import ActiveClient, open_active_client
from src.domains.connectors.clients.email_attachments import attachment_mime
from src.domains.connectors.clients.gmail_attachments_mixin import GmailAttachmentsMixin
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.connectors.preferences.mail_signature import read_signature, signature_block
from src.domains.workbench.mail_files import carried_files
from src.infrastructure.database.session import get_db_context
from src.infrastructure.email.outgoing import OutgoingAttachment

#: Where a file on a card is read from when the message leaves.
HELD: Final = "held"
DRIVE: Final = "drive"

_FILE_NAMES_FIELD: Final = "file_names"
_DRIVE_FIELD: Final = "drive_file_ids"
_DRIVE_FIELDS: Final = ["id", "name", "mimeType", "size"]
_NO_NAME: Final = "attachment"
_ANY_TYPE: Final = "application/octet-stream"


async def signed_body(user_id: UUID, body: str, *, is_html: bool = False) -> str:
    """The body as the card shows it and the message leaves: signed, when the person signs."""
    return body + signature_block(await read_signature(user_id), is_html=is_html)


def original_files(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The files a message holds, as a card names them: Gmail's parts, the others' list."""
    payload = message.get("payload")
    listed = (
        GmailAttachmentsMixin._extract_attachment_info(payload)
        if payload
        else message.get("attachments") or []
    )
    return [
        {
            "filename": str(item.get("filename") or _NO_NAME),
            "mime_type": attachment_mime(item),
            "size": item.get("size") or 0,
        }
        for item in listed
    ]


async def card_files(
    client: EmailClientProtocol,
    user_id: UUID,
    names: Sequence[str] | None,
    drive_ids: Sequence[str] | None,
) -> list[dict[str, Any]]:
    """What the card names, read before anything leaves.

    Args:
        client: The mailbox, whose bound the files must fit.
        user_id: Whose files.
        names: Files LIA holds, as the person knows them.
        drive_ids: Files of the person's drive.

    Returns:
        Each file once, with what the send reads it by.

    Raises:
        EmailValidationError: A file nothing answers to, or more than a message carries.
    """
    wanted_names = list(dict.fromkeys(names or ()))
    wanted_ids = list(dict.fromkeys(drive_ids or ()))
    if len(wanted_names) + len(wanted_ids) > WORKBENCH_MAIL_ATTACHMENTS_MAX:
        raise EmailValidationError(
            f"A message carries {WORKBENCH_MAIL_ATTACHMENTS_MAX} files at most.",
            field=_FILE_NAMES_FIELD,
        )
    held = await _held(user_id, wanted_names) if wanted_names else []
    kept = await _on_drive(user_id, wanted_ids) if wanted_ids else []
    files = [*{item["id"]: item for item in held}.values(), *kept]
    if files and sum(item["size"] for item in files) > client.OUTGOING_FILE_MAX_BYTES:
        raise EmailValidationError(
            f"These files pass the {client.OUTGOING_FILE_MAX_BYTES} bytes the mailbox carries.",
            field=_FILE_NAMES_FIELD,
        )
    return files


async def files_to_send(
    content: Mapping[str, Any], user_id: UUID, client: EmailClientProtocol
) -> tuple[OutgoingAttachment, ...]:
    """What the person confirmed, read whole under the mailbox's bound; a card with none reads
    nothing."""
    files = content.get("files") or []
    if not files:
        return ()
    return await carried_files(
        user_id,
        [UUID(str(item["id"])) for item in files if item.get("origin") == HELD],
        [str(item["id"]) for item in files if item.get("origin") == DRIVE],
        max_bytes=client.OUTGOING_FILE_MAX_BYTES,
    )


async def _held(user_id: UUID, names: Sequence[str]) -> list[dict[str, Any]]:
    """The newest live file each name designates, by the door the send reads through."""
    async with get_db_context() as db:
        found = await db.execute(
            build_attachable_statement(user_id, now=datetime.now(UTC), names=names)
        )
        rows = list(found.scalars().all())
    return [_held_file(_named(rows, name)) for name in names]


def _named(rows: Sequence[Any], name: str) -> Any:
    wanted = name.casefold()
    for row in rows:
        if wanted in (str(row.title or "").casefold(), str(row.original_filename).casefold()):
            return row
    raise EmailValidationError(f"No file LIA holds answers to {name!r}.", field=_FILE_NAMES_FIELD)


def _held_file(row: Any) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "filename": str(row.original_filename),
        "mime_type": str(row.mime_type),
        "size": int(row.file_size),
        "origin": HELD,
    }


async def _on_drive(user_id: UUID, ids: Sequence[str]) -> list[dict[str, Any]]:
    """Each drive file as the card names it; no session is open across these reads."""
    async with open_active_client("files", user_id) as opened:
        if not isinstance(opened, ActiveClient):
            raise EmailValidationError("No drive is connected.", field=_DRIVE_FIELD)
        return [await _drive_file(opened.client, file_id) for file_id in ids]


async def _drive_file(client: Any, file_id: str) -> dict[str, Any]:
    try:
        item = await client.get_file_metadata(file_id, fields=_DRIVE_FIELDS)
    except ConnectorAPIError as error:
        if error.upstream_status_code == status.HTTP_404_NOT_FOUND:
            raise EmailValidationError(
                f"The drive holds no file {file_id!r}.", field=_DRIVE_FIELD
            ) from error
        raise
    return {
        "id": file_id,
        "filename": str(item.get("name") or _NO_NAME),
        "mime_type": str(item.get("mimeType") or _ANY_TYPE),
        # A Google document states no size of its own: its export is measured when it leaves.
        "size": int(item.get("size") or 0),
        "origin": DRIVE,
    }
