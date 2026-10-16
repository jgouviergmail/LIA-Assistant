"""Sending the person's mailbox drafts: the one draft act that asks first (ADR-344).

Saving, editing or trashing a draft reaches nobody; SENDING it reaches its
recipients, so it goes through a confirmation card (``DraftType.
MAILBOX_DRAFT_SEND``) showing the draft as the mailbox holds it: its
recipients, its subject, the person's own words and its files.

What is confirmed is what leaves. The card carries a digest of the draft as it
was read; at the confirmation the draft is read again, and one edited in the
mailbox meanwhile is NOT sent — the person approved another text (ADR-276 lot
7's digest lock). A change asked on the card itself (« make it shorter ») is
written to the draft first, its quoted history kept, and only then does the
draft leave: the Sent folder holds exactly what was approved. A send is one
attempt, never retried (the clients' contract).
"""

from __future__ import annotations

from typing import Annotated, Any, Final
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.field_names import (
    FIELD_BODY,
    FIELD_ERROR,
    FIELD_ERROR_CODE,
    FIELD_MAILBOX_DRAFT_ID,
    FIELD_MAILBOX_DRAFT_REVISION,
    FIELD_SUCCESS,
    FIELD_THREAD_ID,
)
from src.domains.agents.constants import AGENT_EMAIL, CONTEXT_DOMAIN_EMAILS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.effects.digest import payload_digest
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mailbox_draft_base import (
    MAILBOX_REFUSALS,
    MailboxDraftTool,
    one_line,
    refusal,
    refusal_for,
    with_history,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.mailbox_drafts import (
    MailboxDraftChangedError,
    MailboxDraftNotFoundError,
)
from src.domains.connectors.clients.normalizers.reply_trimming import split_quoted_history
from src.domains.connectors.provider_resolver import resolve_client_for_category
from src.infrastructure.email.recipients import read_recipients, same_recipients

logger = structlog.get_logger(__name__)

#: The draft's fingerprint as it was shown, carried by the card.
FIELD_DIGEST: Final = "digest"
#: The recipient fields a draft holds, in the order a card shows them.
ADDRESS_FIELDS: Final = ("to", "cc", "bcc")
#: Why a confirmed draft did not leave.
DRAFT_CHANGED: Final = "DRAFT_CHANGED"
DRAFT_GONE: Final = "DRAFT_GONE"
NO_RECIPIENT: Final = "NO_RECIPIENT"


def _files(draft: dict[str, Any]) -> list[dict[str, str]]:
    """The names of a draft's files, as the card shows them."""
    files = draft.get("attachments") or []
    return [{"filename": str(f.get("filename") or "")} for f in files if isinstance(f, dict)]


def live_digest(draft: dict[str, Any]) -> str:
    """The fingerprint of a draft as the mailbox holds it.

    Its recipients, its subject, its WHOLE text — the quoted message included —
    its file descriptors and the provider revision of the complete MIME
    message: replacing bytes or HTML without changing visible words changes it.

    Args:
        draft: The draft, as ``get_draft`` returns it.

    Returns:
        A hex digest.
    """
    shown = {name: str(draft.get(name) or "") for name in (*ADDRESS_FIELDS, "subject")}
    files = [
        {key: str(file.get(key) or "") for key in ("filename", "attachmentId", "mimeType", "size")}
        for file in draft.get("attachments") or []
        if isinstance(file, dict)
    ]
    return payload_digest(
        {
            **shown,
            FIELD_BODY: str(draft.get(FIELD_BODY) or ""),
            FIELD_MAILBOX_DRAFT_REVISION: str(draft.get(FIELD_MAILBOX_DRAFT_REVISION) or ""),
            "files": files,
        }
    )


def _addresses(field: object) -> list[str]:
    """The addresses a recipient field names, compared without their display names."""
    return sorted({address.lower() for _, address in read_recipients(str(field or ""))})


def _reaches_nobody(draft: dict[str, Any]) -> bool:
    """Whether no recipient field of a draft names a readable address."""
    return not any(_addresses(draft.get(name)) for name in ADDRESS_FIELDS)


def confirmed_changes(confirmed: dict[str, Any], live: dict[str, Any]) -> dict[str, str]:
    """What the confirmed card changes in the live draft (a change asked on the card).

    Args:
        confirmed: The card's content, as the person confirmed it.
        live: The draft, as the mailbox holds it now.

    Returns:
        The fields to write, as ``update_draft`` takes them: the body keeps the
        message the draft quotes below the person's words.
    """
    changes = {
        name: str(confirmed.get(name) or "")
        for name in ADDRESS_FIELDS
        if not same_recipients(confirmed.get(name), live.get(name))
    }
    subject = one_line(str(confirmed.get("subject") or "")) or ""
    if subject != (one_line(str(live.get("subject") or "")) or ""):
        changes["subject"] = subject
    own_words, history = split_quoted_history(str(live.get(FIELD_BODY) or ""))
    words = str(confirmed.get(FIELD_BODY) or "")
    if words.strip() != own_words.strip():
        changes[FIELD_BODY] = with_history(words, history)
    return changes


def _refused(code: str, message: str) -> dict[str, Any]:
    """A send the executor refused — nothing left the mailbox."""
    return {FIELD_SUCCESS: False, FIELD_ERROR_CODE: code, FIELD_ERROR: message}


async def execute_mailbox_draft_send_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """Send the confirmed draft — the one the person saw, with the changes they asked.

    Registered in ``draft_executor_registry.ensure_executors_registered()``.

    Args:
        draft_content: The card's content, as confirmed.
        user_id: The draft's owner.
        deps: ToolDependencies (the mailbox's credentials come through it).

    Returns:
        The sent message, or a typed refusal when the draft changed or went.
    """
    client, _ = await resolve_client_for_category("email", user_id, deps)
    handle = str(draft_content[FIELD_MAILBOX_DRAFT_ID])
    try:
        live = await client.get_draft(handle)
    except MailboxDraftNotFoundError:
        return _refused(
            DRAFT_GONE,
            "The draft is no longer in the mailbox (sent, deleted or moved): nothing was sent.",
        )
    if live_digest(live) != draft_content.get(FIELD_DIGEST):
        return _refused(
            DRAFT_CHANGED,
            "The draft changed in the mailbox after it was shown: nothing was sent. Show it "
            "again to send it as it is now.",
        )
    changes = confirmed_changes(draft_content, live)
    if _reaches_nobody({**live, **changes}):
        return _refused(NO_RECIPIENT, "The draft as confirmed has no recipient: nothing was sent.")
    if changes:
        try:
            edited = await client.update_draft(
                handle, expected_revision=live[FIELD_MAILBOX_DRAFT_REVISION], **changes
            )
        except MailboxDraftChangedError:
            return _refused(
                DRAFT_CHANGED,
                "The draft changed before the confirmed edit: nothing was sent. Show it again.",
            )
        # iCloud gives an edited draft a new handle.
        handle = str(edited.get(FIELD_MAILBOX_DRAFT_ID) or handle)
    sent = await client.send_draft(handle)
    logger.info(
        "mailbox_draft_sent",
        user_id=str(user_id),
        edited=sorted(changes),
        draft_kept=bool(sent.get("draft_kept")),
    )
    return {
        FIELD_SUCCESS: True,
        "message_id": sent.get("id"),
        FIELD_THREAD_ID: sent.get("threadId"),
        # The draft became this message: no draft handle survives the send.
        FIELD_MAILBOX_DRAFT_ID: None,
        "draft_kept": bool(sent.get("draft_kept")),
        **({"sent_copy_filed": sent["sent_copy_filed"]} if "sent_copy_filed" in sent else {}),
        "edited": sorted(changes),
        "to": changes.get("to", draft_content.get("to")),
        "subject": changes.get("subject", draft_content.get("subject")),
    }


class SendMailboxDraftTool(MailboxDraftTool):
    """Build the confirmation that sending a draft needs."""

    def __init__(self) -> None:
        """Initialise the draft send tool."""
        super().__init__(tool_name="send_mailbox_draft_tool", operation="send_draft")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Read the draft as the mailbox holds it; refuse one that has nobody to reach."""
        handle = str(kwargs.get(FIELD_MAILBOX_DRAFT_ID) or "").strip()
        if not handle:
            return refusal(ToolErrorCode.MISSING_REQUIRED_PARAM, "mailbox_draft_id is required.")
        try:
            live = await client.get_draft(handle)
        except MAILBOX_REFUSALS as error:
            return refusal_for(error)
        if _reaches_nobody(live):
            return refusal(
                ToolErrorCode.INVALID_INPUT,
                "This draft has no recipient: add one with update_mailbox_draft_tool first.",
            )
        revision = live.get(FIELD_MAILBOX_DRAFT_REVISION)
        if not isinstance(revision, str) or not revision.strip():
            return refusal(
                ToolErrorCode.INVALID_RESPONSE_FORMAT,
                "The mailbox did not provide the complete draft revision: no send confirmation "
                "can be built. Read the draft again.",
            )
        own_words, history = split_quoted_history(str(live.get(FIELD_BODY) or ""))
        return {
            FIELD_MAILBOX_DRAFT_ID: str(live.get(FIELD_MAILBOX_DRAFT_ID) or handle),
            **{name: str(live.get(name) or "") for name in (*ADDRESS_FIELDS, "subject")},
            FIELD_BODY: own_words.strip(),
            "quotes_history": bool(history.strip()),
            "attachments": _files(live),
            FIELD_DIGEST: live_digest(live),
            "user_language": self.get_user_language(),
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """A refusal, or the confirmation card the person answers."""
        if FIELD_ERROR_CODE in result:
            return super().format_registry_response(result)
        return DraftService().create_draft(
            draft_type=DraftType.MAILBOX_DRAFT_SEND,
            content=result,
            source_tool="send_mailbox_draft_tool",
            user_language=str(result["user_language"]),
        )


_send_mailbox_draft_tool_instance = SendMailboxDraftTool()


@connector_tool(
    name="send_mailbox_draft",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    context_save_mode=ContextSaveMode.NONE,
    category="write",
)
async def send_mailbox_draft_tool(
    mailbox_draft_id: Annotated[str, "The draft's handle (from list_mailbox_drafts or CONTEXT)"],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    SEND a draft of the person's mailbox, after their confirmation.

    The person is shown the draft as their mailbox holds it and confirms,
    edits or cancels; nothing leaves before that. One draft per call.

    Args:
        mailbox_draft_id: The draft's handle.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput carrying the confirmation the person answers.
    """
    return await _send_mailbox_draft_tool_instance.execute(
        runtime=runtime, mailbox_draft_id=mailbox_draft_id
    )


__all__ = [
    "DRAFT_CHANGED",
    "DRAFT_GONE",
    "NO_RECIPIENT",
    "SendMailboxDraftTool",
    "confirmed_changes",
    "execute_mailbox_draft_send_draft",
    "live_digest",
    "send_mailbox_draft_tool",
]
