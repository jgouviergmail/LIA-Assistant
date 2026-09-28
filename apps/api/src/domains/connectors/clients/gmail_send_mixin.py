"""How a Gmail message leaves, mixed into ``GoogleGmailClient`` (ADR-321).

Gmail offers two doors to ``users.messages.send``. The METADATA URI takes the
message base64url-encoded inside a JSON body, and refuses a request past about
1 MiB (a public report measured 1 048 576 bytes); the UPLOAD URI takes the raw
RFC 822 bytes up to the ``maxSize`` of the API's discovery document
(``GMAIL_SEND_MESSAGE_MAX_BYTES``). A message carrying a file — a new message
or a forward — therefore takes the upload URI; a message of words keeps the
metadata URI it always used.

Lives here because the client is frozen at its audited size.
"""

from __future__ import annotations

from email.message import Message
from typing import Any, Final, Protocol

from src.core.constants import GOOGLE_GMAIL_UPLOAD_BASE_URL

_SEND_ENDPOINT: Final = "/users/me/messages/send"


class _GmailSendHost(Protocol):
    """What the mixin needs from its host: the request seam and the encoder."""

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
    ) -> dict[str, Any]: ...

    @staticmethod
    def _encode_base64url(text: str) -> str: ...


class GmailSendMixin:
    """The one door a new Gmail message leaves through."""

    async def _send_message(
        self: _GmailSendHost, message: Message, *, with_files: bool
    ) -> dict[str, Any]:
        """Send a built message through the door its size needs.

        Args:
            message: The complete message, headers included.
            with_files: Whether it carries a file.

        Returns:
            Gmail's answer (``id``, ``threadId``, ``labelIds``).
        """
        if with_files:
            return await self._make_request(
                "POST",
                _SEND_ENDPOINT,
                params={"uploadType": "media"},
                extra_headers={"Content-Type": "message/rfc822"},
                content=message.as_bytes(),
                base_url=GOOGLE_GMAIL_UPLOAD_BASE_URL,
            )
        raw = self._encode_base64url(message.as_string())
        return await self._make_request("POST", _SEND_ENDPOINT, json_data={"raw": raw})
