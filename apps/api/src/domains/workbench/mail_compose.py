"""A message written by the person's own hand (ADR-369).

« Send » is the confirmation (ADR-316's doctrine): a message leaves once per
submission (``run_once``) — a second click is told what became of the first,
never sends again —, and a send whose answer was lost is « may have left »,
never « try again » (ADR-221: one attempt, ``act=True``). Every recipient is
read apart, strictly (``parse_recipients``): one that cannot be read refuses
the message, naming its field and its place, before anything leaves — a
recipient dropped in silence never receives what the person wrote. A new
message may carry the person's own files (``mail_files``): read BEFORE the send,
so a file that cannot be read is a refusal, never « may have left ».
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any
from uuid import UUID

from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import INVALID_RECIPIENT, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.idempotency import run_once
from src.domains.workbench.mail_files import outgoing_files
from src.domains.workbench.schemas.mail_compose import Forward, NewMessage, Reply, SentMessage
from src.infrastructure.email.outgoing import OutgoingAttachment
from src.infrastructure.email.recipients import name_addr, parse_recipients

_TOOL = WorkbenchTool.MAIL


async def send_message(user_id: UUID, message: NewMessage) -> SentMessage:
    """Send a new message, once per submission."""
    to, cc, bcc = (
        recipient_field(name, values)
        for name, values in (("to", message.to), ("cc", message.cc), ("bcc", message.bcc))
    )

    async def send(
        client: EmailClientProtocol, files: tuple[OutgoingAttachment, ...]
    ) -> Mapping[str, Any]:
        sent: Mapping[str, Any] = await client.send_email(
            to,
            message.subject,
            message.body,
            cc=cc or None,
            bcc=bcc or None,
            is_html=False,
            attachments=files,
            single_attempt=True,
        )
        return sent

    return await _once(user_id, message.idempotency_key, "send", send, files=message.attachment_ids)


async def reply(user_id: UUID, answer: Reply) -> SentMessage:
    """Reply to a message (and to all, when asked), once per submission."""

    async def send(
        client: EmailClientProtocol, _: tuple[OutgoingAttachment, ...]
    ) -> Mapping[str, Any]:
        sent: Mapping[str, Any] = await client.reply_email(
            answer.message_id, answer.body, reply_all=answer.reply_all, is_html=False
        )
        return sent

    return await _once(user_id, answer.idempotency_key, "reply", send)


async def forward(user_id: UUID, forwarded: Forward) -> SentMessage:
    """Forward a message with its files, once per submission."""
    to = recipient_field("to", forwarded.to)
    cc = recipient_field("cc", forwarded.cc)

    async def send(
        client: EmailClientProtocol, _: tuple[OutgoingAttachment, ...]
    ) -> Mapping[str, Any]:
        sent: Mapping[str, Any] = await client.forward_email(
            forwarded.message_id, to, body=forwarded.body, cc=cc or None, is_html=False
        )
        return sent

    return await _once(user_id, forwarded.idempotency_key, "forward", send)


async def _once(
    user_id: UUID,
    key: UUID,
    operation: str,
    act: Callable[
        [EmailClientProtocol, tuple[OutgoingAttachment, ...]], Awaitable[Mapping[str, Any]]
    ],
    *,
    files: Sequence[UUID] = (),
) -> SentMessage:
    """Run one send under the submission's key and the workbench's failure contract.

    The person's files are read inside the door (the provider's ceiling is its
    client's) and BEFORE the provider call, which alone is an act.
    """

    async def attempt() -> SentMessage:
        async with open_tool_client(_TOOL, user_id) as opened:
            client: EmailClientProtocol = opened.client
            attached = await outgoing_files(
                user_id, files, max_bytes=client.OUTGOING_FILE_MAX_BYTES
            )
            async with provider_call(_TOOL, operation, act=True):
                sent = await act(client, attached)
        return SentMessage(
            id=str(sent.get("id") or "") or None,
            thread_id=str(sent.get("threadId") or "") or None,
        )

    return await run_once(
        user_id,
        key,
        attempt,
        tool=_TOOL.value,
        record=lambda sent: {"message_id": sent.id} if sent.id else {},
    )


def recipient_field(name: str, recipients: Sequence[str]) -> str:
    """One recipient field, each recipient read apart; refused at the first unreadable.

    Raises:
        BaseAPIException: ``invalid_recipient`` with the field and the place.
    """
    mailboxes: list[str] = []
    for index, typed in enumerate(recipients):
        try:
            read = parse_recipients(typed)
        except ValueError:
            read = []
        if len(read) != 1:
            refuse(INVALID_RECIPIENT, field=name, index=index)
        display, address = read[0]
        mailboxes.append(name_addr(display, address))
    return ", ".join(mailboxes)
