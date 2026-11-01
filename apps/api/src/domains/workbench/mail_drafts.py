"""The mailbox's drafts, by the person's own hand (ADR-369, ADR-344).

A draft is saved — created once per submission (``run_once``), or changed
against the revision the editor holds: a draft changed elsewhere since is
refused (``conflict``), never overwritten — and the answer carries the draft's
id, which iCloud CHANGES on every save (it stores a new message). Sending one
re-reads it first (as the assistant's executor does): changed since it was
shown, it is refused; addressed to nobody, nothing leaves; otherwise it leaves
once, a lost answer being « may have left » (ADR-221). Trashing answers each
draft — never all-or-nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

from src.core.field_names import FIELD_MAILBOX_DRAFT_ID, FIELD_MAILBOX_DRAFT_REVISION
from src.domains.connectors.clients.mailbox_drafts import ensure_draft_revision
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import INVALID_REQUEST, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.idempotency import run_once
from src.domains.workbench.mail_compose import recipient_field
from src.domains.workbench.mail_projection import addresses, attachments_of, received_at
from src.domains.workbench.schemas.acts import ActFailure, ActOutcome, ActStatus
from src.domains.workbench.schemas.mail_compose import (
    DraftSave,
    DraftSelection,
    DraftSend,
    DraftsPage,
    DraftSummary,
    MailDraft,
    SentMessage,
)
from src.infrastructure.email.recipients import read_recipients

_TOOL = WorkbenchTool.MAIL
#: The recipient fields a draft is sent to.
_ADDRESS_FIELDS: Final = ("to", "cc", "bcc")
#: ``mailbox_drafts``' trash statuses, as the act's vocabulary says them.
_TRASH_STATUSES: Final[dict[str, ActStatus]] = {
    "not_found": "not_found",
    "refused": "failed",
    "unavailable": "unavailable",
}


async def list_drafts(user_id: UUID, *, page_token: str | None) -> DraftsPage:
    """One page of the drafts, newest first."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "list_drafts", act=False):
            raw = await client.list_drafts(
                max_results=listing_page_size(), page_token=page_token, headers_only=True
            )
    return DraftsPage(
        items=[_summary(draft) for draft in raw.get("messages") or []],
        next_page_token=raw.get("next_page_token") or None,
    )


async def read_draft(user_id: UUID, draft_id: str) -> MailDraft:
    """One draft, whole, with its revision."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "read_draft", act=False):
            raw = await client.get_draft(draft_id)
        provider = opened.connector_type
    return _draft(raw, provider)


async def save_draft(user_id: UUID, request: DraftSave) -> MailDraft:
    """Create a draft once per submission, or change one against its revision."""
    recipients = _draft_recipients(request)
    if request.draft_id is None:
        return await _create_draft(user_id, request, recipients)
    return await _change_draft(user_id, request.draft_id, request, recipients)


#: A draft's recipient fields as headers; None leaves a field as it is.
_Recipients = tuple[str | None, str | None, str | None]


def _draft_recipients(request: DraftSave) -> _Recipients:
    """Each recipient read apart and rebuilt (``recipient_field``); a field left out stays."""
    to, cc, bcc = (
        None if values is None else recipient_field(name, values)
        for name, values in (("to", request.to), ("cc", request.cc), ("bcc", request.bcc))
    )
    return to, cc, bcc


async def _create_draft(user_id: UUID, request: DraftSave, recipients: _Recipients) -> MailDraft:
    """A new draft, once per the page's key."""
    assert request.idempotency_key is not None  # the schema requires it for a creation
    to, cc, bcc = recipients

    async def create() -> MailDraft:
        async with open_tool_client(_TOOL, user_id) as opened:
            client: EmailClientProtocol = opened.client
            async with provider_call(_TOOL, "create_draft", act=True):
                raw = await client.create_draft(
                    to or "",
                    request.subject or "",
                    request.body or "",
                    cc=cc or None,
                    bcc=bcc or None,
                    is_html=False,
                )
            provider = opened.connector_type
        return _draft(raw, provider)

    return await run_once(
        user_id,
        request.idempotency_key,
        create,
        tool=_TOOL.value,
        record=lambda made: {"draft_id": made.id},
    )


async def _change_draft(
    user_id: UUID, draft_id: str, request: DraftSave, recipients: _Recipients
) -> MailDraft:
    """A draft changed against the revision the editor holds (a field left out is kept)."""
    to, cc, bcc = recipients
    async with open_tool_client(_TOOL, user_id) as opened:
        mailbox: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "update_draft", act=True):
            raw = await mailbox.update_draft(
                draft_id,
                to=to,
                cc=cc,
                bcc=bcc,
                subject=request.subject,
                body=request.body,
                expected_revision=request.expected_revision,
            )
        provider = opened.connector_type
    return _draft(raw, provider)


async def send_draft(user_id: UUID, request: DraftSend) -> SentMessage:
    """Send a draft as the person last saw it, once per submission."""

    async def attempt() -> SentMessage:
        async with open_tool_client(_TOOL, user_id) as opened:
            client: EmailClientProtocol = opened.client
            async with provider_call(_TOOL, "read_draft", act=False):
                live = await client.get_draft(request.draft_id)
                # Changed since it was shown: refused (conflict), never sent as it is now.
                ensure_draft_revision(live, request.expected_revision)
                if not any(read_recipients(str(live.get(name) or "")) for name in _ADDRESS_FIELDS):
                    refuse(INVALID_REQUEST)
            async with provider_call(_TOOL, "send_draft", act=True):
                sent = await client.send_draft(request.draft_id)
        return SentMessage(
            id=str(sent.get("id") or "") or None,
            thread_id=str(sent.get("threadId") or "") or None,
        )

    return await run_once(
        user_id,
        request.idempotency_key,
        attempt,
        tool=_TOOL.value,
        record=lambda sent: {"message_id": sent.id} if sent.id else {},
    )


async def trash_drafts(user_id: UUID, selection: DraftSelection) -> ActOutcome:
    """Move drafts to the trash (recoverable there); each draft answered."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "trash_drafts", act=False):
            raw = await client.trash_drafts(selection.draft_ids)
    return ActOutcome(
        done=list(raw.get("trashed") or []),
        failed=[
            ActFailure(
                id=str(item.get(FIELD_MAILBOX_DRAFT_ID) or ""),
                status=_TRASH_STATUSES.get(str(item.get("status")), "unavailable"),
            )
            for item in raw.get("failed") or []
        ],
    )


def _summary(draft: Mapping[str, Any]) -> DraftSummary:
    return DraftSummary(
        id=str(draft.get(FIELD_MAILBOX_DRAFT_ID) or ""),
        to=addresses(draft.get("to")),
        subject=str(draft.get("subject") or ""),
        snippet=str(draft.get("snippet") or ""),
        updated_at=received_at(draft.get("internalDate")),
    )


def _draft(raw: Mapping[str, Any], provider: ConnectorType) -> MailDraft:
    return MailDraft(
        id=str(raw.get(FIELD_MAILBOX_DRAFT_ID) or ""),
        revision=str(raw.get(FIELD_MAILBOX_DRAFT_REVISION) or ""),
        to=addresses(raw.get("to")),
        cc=addresses(raw.get("cc")),
        bcc=addresses(raw.get("bcc")),
        subject=str(raw.get("subject") or ""),
        body=str(raw.get("body") or ""),
        attachments=attachments_of(raw, provider),
        updated_at=received_at(raw.get("internalDate")),
    )
