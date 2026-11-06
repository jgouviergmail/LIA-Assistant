"""A conversation on iCloud: IMAP keeps none, the headers do (ADR-369, lot 8).

Out of ``apple_email_client.py``, which is close to its size cap. Every message of a
conversation carries the id that names it (``conversation_opening``), so that id is searched
for: in the folder the message was read in first, so it keeps its own id when a copy lives
elsewhere, then in the inbox and the sent folder, where one's own answers are. Every other
folder would be one more round trip for what is rarely kept apart. Headers alone are read,
so a message here has no preview, and the bound holds per folder.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any, Final, Protocol

from imap_tools import AND, OR, H, MailBox, MailMessage

from src.domains.connectors.clients.apple_imap import (
    SENT_ROLE,
    ImapMessageNotFoundError,
    authenticated_imap_mailbox,
    located_message,
    mailbox_scope,
    select_message_folder,
    special_folder,
)
from src.domains.connectors.clients.mail_conversation import conversation_answer
from src.domains.connectors.clients.mailbox_drafts import MailboxFolderUnavailableError
from src.domains.connectors.clients.normalizers.email_normalizer import (
    conversation_opening,
    normalize_imap_message,
)
from src.domains.connectors.clients.normalizers.imap_handles import INBOX, MessageLocation
from src.domains.connectors.schemas import AppleCredentials

_DRAFT_LABEL: Final = "DRAFT"


class _ConversationHost(Protocol):
    """What the mixin needs from its host."""

    credentials: AppleCredentials

    async def _execute_with_retry(
        self, operation: str, func: Any, *args: Any, max_retries: int = 3, **kwargs: Any
    ) -> Any: ...

    def _check_imap_auth_error(self, error: Exception) -> None: ...

    async def _conversation_impl(self, message_id: str, max_messages: int) -> dict[str, Any]: ...


def _sent_folder(mailbox: MailBox) -> str | None:
    """Where one's own answers are; a server without such a folder still answers."""
    try:
        return special_folder(mailbox, SENT_ROLE)
    except MailboxFolderUnavailableError:
        return None


def _headers(mailbox: MailBox, criteria: Any, limit: int) -> Iterator[MailMessage]:
    """The newest ``limit`` hits of the selected folder, marked read by nothing."""
    return mailbox.fetch(criteria, limit=limit, mark_seen=False, reverse=True, headers_only=True)


def _read_conversation(
    mailbox: MailBox, location: MessageLocation, principal: str, max_messages: int
) -> dict[str, Any]:
    """Read a conversation in the open session; every value is extracted within it."""
    folder = select_message_folder(mailbox, location, principal=principal)
    anchor = None if folder is None else next(_headers(mailbox, AND(uid=location.uid), 1), None)
    if folder is None or anchor is None:
        raise ImapMessageNotFoundError("Message not found")
    opening = conversation_opening(anchor.headers)
    if opening is None:
        alone = normalize_imap_message(anchor, folder, scope=location.scope_digest)
        return conversation_answer([alone], max_messages)
    criteria = OR(
        header=[H("Message-ID", opening), H("References", opening), H("In-Reply-To", opening)]
    )
    said: dict[str, dict[str, Any]] = {}
    more = False
    for place in dict.fromkeys(filter(None, (folder, INBOX, _sent_folder(mailbox)))):
        mailbox.folder.set(place)
        scope = mailbox_scope(mailbox, place, principal)
        hits = list(_headers(mailbox, criteria, max_messages + 1))
        more = more or len(hits) > max_messages
        for hit in hits:
            message = normalize_imap_message(hit, place, scope=scope)
            if _DRAFT_LABEL not in message["labelIds"]:
                said.setdefault(str(message["rfc_message_id"] or message["id"]), message)
    ordered = sorted(said.values(), key=lambda item: int(item["internalDate"] or 0))
    return conversation_answer(ordered, max_messages, more=more)


class AppleConversationMixin:
    """A conversation, walked back from its headers."""

    async def get_conversation(
        self: _ConversationHost, message_id: str, max_messages: int
    ) -> dict[str, Any]:
        """The conversation of a message, headers alone (``mail_conversation``).

        Args:
            message_id: Any message of it.
            max_messages: How many are kept, the newest.

        Returns:
            ``{"messages": [...], "truncated": bool}``, oldest first, drafts left out.

        Raises:
            ImapMessageNotFoundError: The id names no message of this mailbox.
        """
        return await self._execute_with_retry(
            "get_conversation", self._conversation_impl, message_id, max_messages
        )

    async def _conversation_impl(
        self: _ConversationHost, message_id: str, max_messages: int
    ) -> dict[str, Any]:
        location = located_message(message_id)
        principal = self.credentials.apple_id

        def _read() -> dict[str, Any]:
            try:
                with authenticated_imap_mailbox(
                    MailBox, principal, self.credentials.app_password
                ) as mailbox:
                    return _read_conversation(mailbox, location, principal, max_messages)
            except ValueError:
                raise
            except Exception as error:
                self._check_imap_auth_error(error)
                raise

        return await asyncio.to_thread(_read)
