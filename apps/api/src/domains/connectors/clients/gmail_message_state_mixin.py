"""Where a Gmail message is and whether it was read (ADR-369).

Trash, restore, permanent deletion and the read state: the acts that change a
message's STATE without composing anything. Out of ``google_gmail_client.py``,
which is frozen at its audited size, and together because each of them must
make the client's caches forget the message (the cache generation, Task 2.2).

The read state is Gmail's ``UNREAD`` system label, moved for a whole selection
in one ``batchModify``. Gmail refuses the WHOLE batch when one id is unknown,
so a refused batch is retried message by message to say which one left the
mailbox — the rest of the selection is still marked (owner decision D2: the
same contract on the three providers).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Final, Protocol
from uuid import UUID

import structlog

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.mail_read_state import (
    GMAIL_UNREAD_LABEL,
    READ_STATE_FAILED,
    READ_STATE_NOT_FOUND,
    read_state_result,
    unique_ids,
)
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

#: What a Gmail message id is made of; anything else never reaches a URL path.
_MESSAGE_ID: Final = re.compile(r"[A-Za-z0-9_-]+")
#: What Gmail answers for a batch naming an id it does not know.
_BATCH_REFUSALS: Final = frozenset({400, 404})
#: A message that is not there any more.
_GONE: Final = frozenset({404, 410})


class _GmailStateHost(Protocol):
    """What the mixin needs from its host."""

    user_id: UUID

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        max_retries: int = 3,
        extra_headers: dict[str, str] | None = None,
        *,
        content: bytes | None = None,
        base_url: str | None = None,
        idempotent: bool | None = None,
    ) -> dict[str, Any]: ...

    async def batch_modify_labels(
        self,
        message_ids: list[str],
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> bool: ...

    async def modify_message_labels(
        self,
        message_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]: ...

    async def _mark_each(
        self, message_ids: list[str], add: list[str] | None, remove: list[str] | None
    ) -> dict[str, Any]: ...


class GmailMessageStateMixin:
    """Trash, restore, delete and read state of Gmail messages."""

    async def trash_email(self: _GmailStateHost, message_id: str) -> dict[str, Any]:
        """Move an email to the trash, where it stays recoverable for 30 days.

        Args:
            message_id: Message ID to move to the trash.

        Returns:
            The trashed message's details (id, threadId, labelIds).
        """
        # Trashing a trashed message changes nothing: a lost answer may be resent (S1).
        response = await self._make_request(
            "POST", f"/users/me/messages/{_path_id(message_id)}/trash", idempotent=True
        )
        logger.info("gmail_email_trashed", user_id=str(self.user_id), message_id=message_id)
        return response

    async def untrash_email(self: _GmailStateHost, message_id: str) -> dict[str, Any]:
        """Restore an email from the trash to where it was.

        Args:
            message_id: Message ID to restore.

        Returns:
            The restored message's details (id, threadId, labelIds).
        """
        response = await self._make_request(
            "POST", f"/users/me/messages/{_path_id(message_id)}/untrash", idempotent=True
        )
        logger.info("gmail_email_untrashed", user_id=str(self.user_id), message_id=message_id)
        return response

    async def delete_email_permanently(self: _GmailStateHost, message_id: str) -> None:
        """Delete an email for good. IRREVERSIBLE: prefer ``trash_email``.

        Args:
            message_id: Message ID to delete.
        """
        await self._make_request("DELETE", f"/users/me/messages/{_path_id(message_id)}")
        logger.info(
            "gmail_email_deleted_permanently", user_id=str(self.user_id), message_id=message_id
        )

    async def mark_read(
        self: _GmailStateHost, message_ids: Sequence[str], read: bool
    ) -> dict[str, Any]:
        """Mark messages read or unread, and say which could not be.

        Args:
            message_ids: The messages (each counted once).
            read: True to mark them read, False unread.

        Returns:
            ``{"updated": [ids], "failed": [{"id", "status"}]}``
            (``mail_read_state``).
        """
        ids = unique_ids(message_ids)
        malformed = [message_id for message_id in ids if not _MESSAGE_ID.fullmatch(message_id)]
        wanted = [message_id for message_id in ids if message_id not in malformed]
        add, remove = (None, [GMAIL_UNREAD_LABEL]) if read else ([GMAIL_UNREAD_LABEL], None)
        result = read_state_result(wanted, [])
        if wanted:
            try:
                await self.batch_modify_labels(wanted, add_label_ids=add, remove_label_ids=remove)
            except ConnectorAPIError as refused:
                if refused.upstream_status_code not in _BATCH_REFUSALS:
                    raise
                result = await self._mark_each(wanted, add, remove)
        result["failed"] += [{"id": bad, "status": READ_STATE_NOT_FOUND} for bad in malformed]
        logger.info(
            "gmail_read_state_changed",
            user_id=str(self.user_id),
            read=read,
            updated=len(result["updated"]),
            failed=len(result["failed"]),
        )
        return result

    async def _mark_each(
        self: _GmailStateHost,
        message_ids: list[str],
        add: list[str] | None,
        remove: list[str] | None,
    ) -> dict[str, Any]:
        """The batch was refused: one message at a time, to name the one gone."""
        updated: list[str] = []
        failed: list[tuple[str, str]] = []
        for message_id in message_ids:
            try:
                await self.modify_message_labels(
                    message_id, add_label_ids=add, remove_label_ids=remove
                )
            except ConnectorAPIError as refused:
                gone = refused.upstream_status_code in _GONE | _BATCH_REFUSALS
                failed.append((message_id, READ_STATE_NOT_FOUND if gone else READ_STATE_FAILED))
                continue
            updated.append(message_id)
        return read_state_result(updated, failed)


def _path_id(message_id: str) -> str:
    """A message id fit for a URL path — anything else names no message, and asks nothing.

    The id comes from a browser or a model: interpolated raw, ``x/../drafts/y``
    would send the person's token to another endpoint of their mailbox.

    Raises:
        ConnectorAPIError: 404, the id names no message (never quoted back).
    """
    if not _MESSAGE_ID.fullmatch(message_id):
        raise ConnectorAPIError(
            connector_type=ConnectorType.GOOGLE_GMAIL.value,
            status_code=404,
            detail="google_gmail API error: no such message",
        )
    return message_id


__all__ = ["GmailMessageStateMixin"]
