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

import json
import uuid
from email.message import Message
from typing import Any, Final, Protocol

from src.core.constants import GOOGLE_GMAIL_UPLOAD_BASE_URL

_SEND_ENDPOINT: Final = "/users/me/messages/send"


def multipart_related(metadata: dict[str, Any], raw: bytes) -> tuple[bytes, str]:
    """The upload URI's multipart body: what the message belongs to, then the message."""
    boundary = f"lia_{uuid.uuid4().hex}"
    head = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\nContent-Type: message/rfc822\r\n\r\n"
    ).encode()
    return head + raw + f"\r\n--{boundary}--\r\n".encode(), (
        f"multipart/related; boundary={boundary}"
    )


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

    @staticmethod
    def _encode_email_header(addresses: str) -> str: ...


def stamp_sender(host: _GmailSendHost, message: Message) -> None:
    """Write the alias chosen on a message; none chosen, its ``From`` stays as it is."""
    sender = getattr(host, "_send_as", None)
    if sender:
        del message["From"]
        message["From"] = host._encode_email_header(sender)


class GmailSendMixin:
    """The one door a new Gmail message leaves through."""

    #: The alias of the mailbox its messages leave from; none: Gmail's own default.
    _send_as: str | None = None

    def send_from(self, address: str | None) -> None:
        """Choose the alias this client's messages leave from.

        A client is built for one act, so nothing outlives it. Gmail rewrites a ``From`` it
        does not know: the caller reads the mailbox's aliases first.

        Args:
            address: The alias, as a ``From`` header; None for the mailbox's default.
        """
        self._send_as = address

    async def _send_message(
        self: _GmailSendHost,
        message: Message,
        *,
        with_files: bool,
        single_attempt: bool = True,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a built message through the door its size needs.

        Args:
            message: The complete message, headers included.
            with_files: Whether it carries a file.
            thread_id: The conversation it answers: the upload's bare form holds a message
                and nothing else, so a file in a thread takes its multipart form.

        Returns:
            Gmail's answer (``id``, ``threadId``, ``labelIds``).
        """
        stamp_sender(self, message)
        # Sending is non-idempotent. The legacy keyword stays accepted, but
        # cannot enable replay after an acknowledgement is lost.
        retry_options = {"max_retries": 1}
        if with_files and thread_id:
            content, content_type = multipart_related({"threadId": thread_id}, message.as_bytes())
            return await self._make_request(
                "POST",
                _SEND_ENDPOINT,
                params={"uploadType": "multipart"},
                extra_headers={"Content-Type": content_type},
                content=content,
                base_url=GOOGLE_GMAIL_UPLOAD_BASE_URL,
                **retry_options,
            )
        if with_files:
            return await self._make_request(
                "POST",
                _SEND_ENDPOINT,
                params={"uploadType": "media"},
                extra_headers={"Content-Type": "message/rfc822"},
                content=message.as_bytes(),
                base_url=GOOGLE_GMAIL_UPLOAD_BASE_URL,
                **retry_options,
            )
        raw = self._encode_base64url(message.as_string())
        json_data = {"raw": raw, **({"threadId": thread_id} if thread_id else {})}
        return await self._make_request(
            "POST", _SEND_ENDPOINT, json_data=json_data, **retry_options
        )
