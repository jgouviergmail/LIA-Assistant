"""The HTML of an iCloud message, mixed into ``AppleEmailClient`` (ADR-369, D3).

Which parts are the body's HTML is ``mail_html``'s rule — not ``imap_tools``'
``MailMessage.html``, which also joins the HTML of a message forwarded as an
attachment. The message is read in the folder its id names (``imap_handles``),
off the event loop, without setting ``\\Seen``: reading is not an act.
"""

from __future__ import annotations

import asyncio
from email.message import Message
from typing import Any, Protocol

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
from src.domains.connectors.schemas import AppleCredentials


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


class _AppleHtmlHost(Protocol):
    """What the mixin needs from its host."""

    credentials: AppleCredentials

    async def _execute_with_retry(
        self, operation: str, func: Any, *args: Any, max_retries: int = 3, **kwargs: Any
    ) -> Any: ...

    def _check_imap_auth_error(self, error: Exception) -> None: ...

    async def _message_html_impl(self, message_id: str) -> str | None: ...


class AppleMailHtmlMixin:
    """The HTML body of iCloud messages."""

    async def get_message_html(self: _AppleHtmlHost, message_id: str) -> str | None:
        """The message's HTML body, or None when it carries none.

        Raises:
            ImapMessageNotFoundError: The id names no message of this mailbox.
        """
        result: str | None = await self._execute_with_retry(
            "get_message_html", self._message_html_impl, message_id
        )
        return result

    async def _message_html_impl(self: _AppleHtmlHost, message_id: str) -> str | None:
        location = located_message(message_id)
        apple_id, password = self.credentials.apple_id, self.credentials.app_password

        def fetch_html() -> str | None:
            try:
                with authenticated_imap_mailbox(MailBox, apple_id, password) as mailbox:
                    if select_message_folder(mailbox, location, principal=apple_id) is not None:
                        for msg in mailbox.fetch(AND(uid=location.uid), mark_seen=False):
                            return html_body(msg.obj)
                    raise ImapMessageNotFoundError(f"Message {message_id} not found")
            except ImapMessageNotFoundError:
                raise
            except Exception as error:
                self._check_imap_auth_error(error)
                raise

        return await asyncio.to_thread(fetch_html)
