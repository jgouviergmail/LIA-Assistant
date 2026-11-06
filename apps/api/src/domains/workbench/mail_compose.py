"""A message written by the person's own hand (ADR-369).

« Send » is the confirmation (ADR-316's doctrine): a message leaves once per
submission (``run_once``) — a second click is told what became of the first,
never sends again —, and a send whose answer was lost is « may have left »,
never « try again » (ADR-221: one attempt, ``act=True``). Every recipient is
read apart, strictly (``parse_recipients``): one that cannot be read refuses
the message, naming its field and its place, before anything leaves — a
recipient dropped in silence never receives what the person wrote. A new
message, a reply and a forward may carry the person's own files (``mail_files``):
read BEFORE the send, so a file that cannot be read is a refusal, never « may
have left ». A reply goes to whom the person saw in it: recipients left out are
the provider's to compute. Words written with formatting are rebuilt from an
allowlist here (``html_body``): what the page sent never leaves as it came.
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
from src.domains.workbench.mail_files import carried_files
from src.domains.workbench.mail_settings import apply_send_as
from src.domains.workbench.schemas.mail_compose import Forward, NewMessage, Reply, SentMessage
from src.infrastructure.email.html_body import clean_message_html
from src.infrastructure.email.outgoing import OutgoingAttachment
from src.infrastructure.email.recipients import name_addr, parse_recipients

_TOOL = WorkbenchTool.MAIL


def words_of(html: str | None, text: str) -> tuple[str, bool]:
    """What a body says and whether it is HTML: formatted words, rebuilt, or the text."""
    return (text, False) if html is None else (clean_message_html(html), True)


async def send_message(user_id: UUID, message: NewMessage) -> SentMessage:
    """Send a new message, once per submission."""
    to, cc, bcc = (
        recipient_field(name, values)
        for name, values in (("to", message.to), ("cc", message.cc), ("bcc", message.bcc))
    )
    body, is_html = words_of(message.html, message.body)

    async def send(
        client: EmailClientProtocol, files: tuple[OutgoingAttachment, ...]
    ) -> Mapping[str, Any]:
        sent: Mapping[str, Any] = await client.send_email(
            to,
            message.subject,
            body,
            cc=cc or None,
            bcc=bcc or None,
            is_html=is_html,
            attachments=files,
            single_attempt=True,
        )
        return sent

    return await _once(
        user_id,
        message.idempotency_key,
        "send",
        send,
        message,
    )


async def reply(user_id: UUID, answer: Reply) -> SentMessage:
    """Reply to a message (and to all, when asked), once per submission."""
    to = None if answer.to is None else recipient_field("to", answer.to)
    cc = None if answer.cc is None else recipient_field("cc", answer.cc)
    body, is_html = words_of(answer.html, answer.body)

    async def send(
        client: EmailClientProtocol, files: tuple[OutgoingAttachment, ...]
    ) -> Mapping[str, Any]:
        sent: Mapping[str, Any] = await client.reply_email(
            answer.message_id,
            body,
            reply_all=answer.reply_all,
            is_html=is_html,
            to=to,
            cc=cc,
            attachments=files,
        )
        return sent

    return await _once(
        user_id,
        answer.idempotency_key,
        "reply",
        send,
        answer,
    )


async def forward(user_id: UUID, forwarded: Forward) -> SentMessage:
    """Forward a message with its files, once per submission."""
    to = recipient_field("to", forwarded.to)
    cc = recipient_field("cc", forwarded.cc)
    body, is_html = words_of(forwarded.html, forwarded.body)

    async def send(
        client: EmailClientProtocol, files: tuple[OutgoingAttachment, ...]
    ) -> Mapping[str, Any]:
        sent: Mapping[str, Any] = await client.forward_email(
            forwarded.message_id,
            to,
            body=body,
            cc=cc or None,
            is_html=is_html,
            attachments=files,
        )
        return sent

    return await _once(
        user_id,
        forwarded.idempotency_key,
        "forward",
        send,
        forwarded,
    )


async def _once(
    user_id: UUID,
    key: UUID,
    operation: str,
    act: Callable[
        [EmailClientProtocol, tuple[OutgoingAttachment, ...]], Awaitable[Mapping[str, Any]]
    ],
    outgoing: NewMessage | Reply | Forward,
) -> SentMessage:
    """Run one send under the submission's key and the workbench's failure contract.

    The address it leaves from is settled and the person's files are read inside the
    door (the provider's ceiling is its client's), BEFORE the provider call, which
    alone is an act.
    """

    async def attempt() -> SentMessage:
        async with open_tool_client(_TOOL, user_id) as opened:
            client: EmailClientProtocol = opened.client
            if outgoing.send_as:
                await apply_send_as(opened, user_id, outgoing.send_as)
            attached = await carried_files(
                user_id,
                outgoing.attachment_ids,
                outgoing.drive_file_ids,
                max_bytes=client.OUTGOING_FILE_MAX_BYTES,
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
