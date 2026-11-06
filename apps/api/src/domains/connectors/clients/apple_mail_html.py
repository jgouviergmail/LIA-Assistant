"""The HTML of an iCloud message, mixed into ``AppleEmailClient`` (ADR-369, D3).

Which parts are the body's HTML is ``mail_html``'s rule — not ``imap_tools``'
``MailMessage.html``, which also joins the HTML of a message forwarded as an
attachment. The message is read in the folder its id names (``imap_handles``),
off the event loop, without setting ``\\Seen``: reading is not an act. The images it
carries and the way out it names are read from the same fetch.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from email.message import Message
from typing import Any, Protocol, TypeVar

from imap_tools import AND, MailBox

from src.domains.connectors.clients.apple_imap import (
    ImapMessageNotFoundError,
    authenticated_imap_mailbox,
    located_message,
    select_message_folder,
)
from src.domains.connectors.clients.mail_html import (
    ATTACHED_MESSAGE_TYPE,
    HTML_TYPE,
    decode_text,
)
from src.domains.connectors.clients.mail_inline_images import InlineBudget, content_id_of
from src.domains.connectors.clients.mail_unsubscribe import Unsubscribe, read_unsubscribe
from src.domains.connectors.schemas import AppleCredentials

_Read = TypeVar("_Read")


def html_body(message: Message) -> str | None:
    """The body's ``text/html`` parts, in document order, joined (``mail_html``)."""
    pieces: list[str] = []
    pending: list[Message] = [message]
    while pending:
        part = pending.pop()
        if part.get_filename() or (
            part is not message and part.get_content_type() == ATTACHED_MESSAGE_TYPE
        ):
            continue
        if part.is_multipart():
            children: list[Message] = part.get_payload()
            pending.extend(reversed(children))
        elif part.get_content_type() == HTML_TYPE:
            payload = part.get_payload(decode=True)
            data = payload if isinstance(payload, bytes) else b""
            pieces.append(decode_text(data, part.get_content_charset()))
    return "".join(pieces) or None


def admit_inline_images(message: Message, cids: set[str], budget: InlineBudget) -> None:
    """Read into ``budget`` the images a message's HTML names, a forwarded one's left out."""
    pending: list[Message] = [message]
    while pending:
        part = pending.pop()
        if part is not message and part.get_content_type() == ATTACHED_MESSAGE_TYPE:
            continue
        if part.is_multipart():
            children: list[Message] = part.get_payload()
            pending.extend(reversed(children))
            continue
        cid = content_id_of(part.get("Content-ID"))
        if cid not in cids or not budget.worth_reading(None):
            continue
        payload = part.get_payload(decode=True)
        budget.admit(
            str(cid), part.get_content_type(), payload if isinstance(payload, bytes) else b""
        )


class _AppleHtmlHost(Protocol):
    """What the mixin needs from its host."""

    credentials: AppleCredentials

    async def _execute_with_retry(
        self, operation: str, func: Any, *args: Any, max_retries: int = 3, **kwargs: Any
    ) -> Any: ...

    def _check_imap_auth_error(self, error: Exception) -> None: ...

    async def _read_message_impl(
        self, message_id: str, read: Callable[[Message], _Read], *, headers_only: bool = False
    ) -> _Read: ...


class AppleMailHtmlMixin:
    """The HTML body of iCloud messages."""

    async def get_message_html(self: _AppleHtmlHost, message_id: str) -> str | None:
        """The message's HTML body, or None when it carries none.

        Raises:
            ImapMessageNotFoundError: The id names no message of this mailbox.
        """
        result: str | None = await self._execute_with_retry(
            "get_message_html", self._read_message_impl, message_id, html_body
        )
        return result

    async def read_inline_images(
        self: _AppleHtmlHost, message_id: str, cids: set[str], budget: InlineBudget
    ) -> None:
        """Read into ``budget`` the images of a message its HTML names."""
        await self._execute_with_retry(
            "read_inline_images",
            self._read_message_impl,
            message_id,
            lambda message: admit_inline_images(message, cids, budget),
        )

    async def read_unsubscribe(self: _AppleHtmlHost, message_id: str) -> Unsubscribe | None:
        """The ways out a message names."""
        result: Unsubscribe | None = await self._execute_with_retry(
            "read_unsubscribe",
            self._read_message_impl,
            message_id,
            lambda message: read_unsubscribe(
                message.get("List-Unsubscribe"), message.get("List-Unsubscribe-Post")
            ),
            headers_only=True,
        )
        return result

    async def _read_message_impl(
        self: _AppleHtmlHost,
        message_id: str,
        read: Callable[[Message], _Read],
        *,
        headers_only: bool = False,
    ) -> _Read:
        """What ``read`` makes of a message, off the event loop, marking nothing read.

        Args:
            message_id: The message.
            read: What to make of it.
            headers_only: Fetch its headers alone: a message may weigh its files.
        """
        location = located_message(message_id)
        apple_id, password = self.credentials.apple_id, self.credentials.app_password

        def fetch() -> _Read:
            try:
                with authenticated_imap_mailbox(MailBox, apple_id, password) as mailbox:
                    if select_message_folder(mailbox, location, principal=apple_id) is not None:
                        for msg in mailbox.fetch(
                            AND(uid=location.uid), mark_seen=False, headers_only=headers_only
                        ):
                            return read(msg.obj)
                    raise ImapMessageNotFoundError(f"Message {message_id} not found")
            except ImapMessageNotFoundError:
                raise
            except Exception as error:
                self._check_imap_auth_error(error)
                raise

        return await asyncio.to_thread(fetch)
