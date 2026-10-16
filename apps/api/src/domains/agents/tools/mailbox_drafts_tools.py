"""The person's mailbox drafts, as tools: list, write, answer, forward (ADR-344).

A mailbox draft is the person's own unsent message, stored by their provider —
Gmail, Outlook or iCloud — and never the confirmation card LIA builds before an
action (``DraftType``). Its handle is ``mailbox_draft_id``.

Saving a draft asks for no confirmation: it stays in the person's mailbox, sends
nothing to anyone, and can be edited or deleted there (``mutation_policy``
``reversible``, its reason written in the manifests). Only SENDING one reaches
a third party, and that goes through a confirmation card.

Every item travels under the domain's ``emails`` key with its handle. No
top-level key names a « draft »: outcome evidence reads one as « awaiting
confirmation » (ADR-336), and a draft saved in the mailbox is a thing done.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.core.exceptions_domains import UsageLimitExceededError
from src.core.field_names import FIELD_SET_ASIDE_ON_PAGE
from src.core.i18n import get_locale_for_language
from src.domains.agents.constants import AGENT_EMAIL, CONTEXT_DOMAIN_EMAILS
from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    tool_runtime_context,
)
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.emails.content_generation import resolve_email_content
from src.domains.agents.emails.mailbox_drafts_manifests import LIST_MAX_RESULTS_DESCRIPTION
from src.domains.agents.emails.message_finishing import finish_messages
from src.domains.agents.emails.reply_drafting import draft_reply_body
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mailbox_draft_base import (
    MAILBOX_REFUSALS,
    MailboxDraftTool,
    one_line,
    refusal,
    refusal_for,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import get_user_preferences
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.infrastructure.llm.structured_output_errors import StructuredOutputError

logger = structlog.get_logger(__name__)


def _page_size(asked: object) -> int:
    """The number of drafts to read: the published default, clamped to the maximum.

    What the catalogue publishes is what is enforced (ADR-184), and an
    out-of-bounds count is repaired, never failed.
    """
    if not isinstance(asked, int) or isinstance(asked, bool) or asked <= 0:
        return settings.emails_tool_default_limit
    return min(asked, settings.emails_tool_default_max_results)


# ============================================================================
# LIST
# ============================================================================


class ListMailboxDraftsTool(MailboxDraftTool):
    """The drafts folder of the person's mailbox, newest saves first."""

    SAVE_MODE = ContextSaveMode.LIST

    def __init__(self) -> None:
        """Initialise the drafts listing tool."""
        super().__init__(tool_name="list_mailbox_drafts_tool", operation="list_drafts")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Read one page of drafts, whole.

        Args:
            client: The active mailbox (Gmail, Outlook or iCloud).
            user_id: The person.
            **kwargs: ``query``, ``max_results``, ``page_token`` and the
                person's ``user_timezone`` / ``locale``.

        Returns:
            The drafts under ``emails``, the provider's total and the next page.
        """
        query = str(kwargs.get("query") or "")
        listing = await client.list_drafts(
            query=query,
            max_results=_page_size(kwargs.get("max_results")),
            page_token=kwargs.get("page_token"),
            headers_only=False,
        )
        drafts = await finish_messages(client, list(listing.get("messages", [])))
        logger.info("mailbox_drafts_listed", user_id=str(user_id), count=len(drafts))
        return {
            **self.drafts_result(drafts, **kwargs),
            "query": query or None,
            "result_size_estimate": listing.get("resultSizeEstimate"),
            "next_page_token": listing.get("next_page_token"),
            FIELD_SET_ASIDE_ON_PAGE: listing.get(FIELD_SET_ASIDE_ON_PAGE),
            "locale": kwargs.get("locale", get_locale_for_language(None)),
        }


_list_mailbox_drafts_tool_instance = ListMailboxDraftsTool()


@connector_tool(
    name="list_mailbox_drafts",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    context_save_mode=ContextSaveMode.LIST,
    category="read",
)
async def list_mailbox_drafts_tool(
    query: Annotated[
        str | None,
        "Narrow the drafts: to:/cc:/subject: or words (optional; every draft by default)",
    ] = None,
    max_results: Annotated[int, LIST_MAX_RESULTS_DESCRIPTION] = settings.emails_tool_default_limit,
    page_token: Annotated[
        str | None, "next_page_token of a previous page, to continue the same listing"
    ] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    List the person's mailbox DRAFTS — their own unsent messages — newest first.

    Each item carries ``mailbox_draft_id``, the handle the other draft tools
    take, and the person's own words (``quotes_history`` says a message is
    quoted below them).

    Args:
        query: to:/cc:/subject: or words, to narrow the drafts.
        max_results: How many drafts.
        page_token: Continuation token of a previous page.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput with the drafts as message items; ``set_aside_on_page``,
        when present, counts drafts of the page a date condition set aside after
        the provider's search — more may follow on ``next_page_token``.
    """
    user_timezone, _, locale = await get_user_preferences(runtime)
    return await _list_mailbox_drafts_tool_instance.execute(
        runtime=runtime,
        query=query,
        max_results=max_results,
        page_token=page_token,
        user_timezone=user_timezone,
        locale=locale,
    )


# ============================================================================
# CREATE
# ============================================================================


class CreateMailboxDraftTool(MailboxDraftTool):
    """A new draft in the person's mailbox."""

    RECIPIENT_FIELDS = ("to", "cc", "bcc")

    def __init__(self) -> None:
        """Initialise the draft creation tool."""
        super().__init__(tool_name="create_mailbox_draft_tool", operation="create_draft")

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Save the draft as given; a draft may wait for its recipient or its words."""
        try:
            draft = await client.create_draft(
                to=str(kwargs.get("to") or ""),
                subject=one_line(kwargs.get("subject")) or "",
                body=str(kwargs.get("body") or ""),
                cc=kwargs.get("cc") or None,
                bcc=kwargs.get("bcc") or None,
                is_html=bool(kwargs.get("is_html", False)),
            )
        except MAILBOX_REFUSALS as error:
            return refusal_for(error)
        logger.info("mailbox_draft_created", user_id=str(user_id))
        return self.drafts_result([draft], **kwargs)


_create_mailbox_draft_tool_instance = CreateMailboxDraftTool()


@connector_tool(
    name="create_mailbox_draft",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    context_save_mode=ContextSaveMode.CURRENT,
    category="write",
)
async def create_mailbox_draft_tool(
    to: Annotated[
        str | None, "Recipient(s): addresses or contact names, comma-separated (optional)"
    ] = None,
    subject: Annotated[str | None, "Subject (optional)"] = None,
    body: Annotated[str | None, "The draft's text, when the person dictated it"] = None,
    content_instruction: Annotated[
        str | None,
        "What the draft should say, for LIA to write it (use instead of body; omit when the "
        "person asked for an empty draft)",
    ] = None,
    cc: Annotated[str | None, "Copies (optional, comma-separated)"] = None,
    bcc: Annotated[str | None, "Blind copies (optional, comma-separated)"] = None,
    is_html: Annotated[bool, "True if body is HTML (default False)"] = False,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Save a new DRAFT in the person's mailbox: nothing is sent, no confirmation.

    The draft may wait for its recipient or its words; LIA writes them only
    when the person said what the draft should say (``content_instruction``).

    Args:
        to: Recipient(s), addresses or contact names.
        subject: Subject.
        body: The draft's text, as dictated.
        content_instruction: What the draft should say, for LIA to write.
        cc: Copies.
        bcc: Blind copies.
        is_html: Whether body is HTML.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput with the saved draft.
    """
    if content_instruction:
        content = await resolve_email_content(
            runtime=runtime,
            recipient=to or "",
            subject=subject,
            body=body,
            content_instruction=content_instruction,
        )
        if isinstance(content, UnifiedToolOutput):
            return content
        subject, body = content.subject, content.body
    user_timezone, _, locale = await get_user_preferences(runtime)
    return await _create_mailbox_draft_tool_instance.execute(
        runtime=runtime,
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        is_html=is_html,
        user_timezone=user_timezone,
        locale=locale,
    )


# ============================================================================
# REPLY
# ============================================================================


class CreateMailboxReplyDraftTool(MailboxDraftTool):
    """The reply to a received e-mail, saved as a draft in its thread."""

    def __init__(self) -> None:
        """Initialise the reply draft tool."""
        super().__init__(
            tool_name="create_mailbox_reply_draft_tool", operation="create_reply_draft"
        )

    async def _written_reply(
        self, client: GoogleGmailClient, user_id: UUID, message_id: str, instruction: str | None
    ) -> str | dict[str, Any]:
        """The reply LIA writes from the received e-mail — or why it could not."""
        runtime = self.runtime
        context = tool_runtime_context(runtime) if runtime is not None else None
        original = await client.get_message(message_id)
        try:
            body = await draft_reply_body(
                original,
                instruction=instruction,
                sender_name=context.display_name if context is not None else None,
                user_language=self.get_user_language(),
                user_id=str(user_id),
                config=runtime.config if runtime is not None else None,
            )
        except UsageLimitExceededError:
            return refusal(
                ToolErrorCode.RATE_LIMIT_EXCEEDED,
                "A spending ceiling refused writing the reply: give its text, or try later.",
            )
        except StructuredOutputError:
            return refusal(
                ToolErrorCode.EXTERNAL_API_ERROR,
                "The reply could not be written: give its text.",
            )
        if not body.strip():
            return refusal(ToolErrorCode.EMPTY_RESULT, "No reply was written: give its text.")
        return body.strip()

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Write the reply when no text was given, then save it in the thread."""
        message_id = str(kwargs.get("message_id") or "")
        if not message_id:
            return refusal(ToolErrorCode.MISSING_REQUIRED_PARAM, "message_id is required.")
        try:
            # A blank text is no text: LIA writes the reply.
            body = str(kwargs.get("body") or "").strip() or await self._written_reply(
                client, user_id, message_id, kwargs.get("content_instruction")
            )
            if isinstance(body, dict):
                return body
            draft = await client.create_reply_draft(
                message_id, str(body), reply_all=bool(kwargs.get("reply_all", False))
            )
        except MAILBOX_REFUSALS as error:
            return refusal_for(error)
        logger.info("mailbox_reply_draft_created", user_id=str(user_id))
        return self.drafts_result([draft], **kwargs)


_create_mailbox_reply_draft_tool_instance = CreateMailboxReplyDraftTool()


@connector_tool(
    name="create_mailbox_reply_draft",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    context_save_mode=ContextSaveMode.CURRENT,
    category="write",
)
async def create_mailbox_reply_draft_tool(
    message_id: Annotated[str, "The received e-mail to answer (from get_emails or CONTEXT)"],
    body: Annotated[str | None, "The reply's text, when the person dictated it"] = None,
    content_instruction: Annotated[
        str | None, "What the reply should say ('accept', 'ask for Friday'), for LIA to write it"
    ] = None,
    reply_all: Annotated[bool, "Answer every recipient of the e-mail (default False)"] = False,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Save the reply to a received e-mail as a DRAFT in its thread: nothing is sent.

    Without ``body`` LIA writes the reply from the received e-mail, following
    ``content_instruction`` when the person gave one.

    Args:
        message_id: The received e-mail.
        body: The reply's text, as dictated.
        content_instruction: What the reply should say.
        reply_all: Answer every recipient.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput with the saved draft.
    """
    user_timezone, _, locale = await get_user_preferences(runtime)
    return await _create_mailbox_reply_draft_tool_instance.execute(
        runtime=runtime,
        message_id=message_id,
        body=body,
        content_instruction=content_instruction,
        reply_all=reply_all,
        user_timezone=user_timezone,
        locale=locale,
    )


# ============================================================================
# FORWARD
# ============================================================================


class CreateMailboxForwardDraftTool(MailboxDraftTool):
    """The forward of a received e-mail, saved as a draft with its files."""

    RECIPIENT_FIELDS = ("to", "cc")

    def __init__(self) -> None:
        """Initialise the forward draft tool."""
        super().__init__(
            tool_name="create_mailbox_forward_draft_tool", operation="create_forward_draft"
        )

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Save the forward; Outlook refuses one without a recipient, so every road does."""
        message_id = str(kwargs.get("message_id") or "")
        to = str(kwargs.get("to") or "")
        if not message_id or not to:
            return refusal(ToolErrorCode.MISSING_REQUIRED_PARAM, "message_id and to are required.")
        try:
            draft = await client.create_forward_draft(
                message_id, to, body=kwargs.get("body") or None, cc=kwargs.get("cc") or None
            )
        except MAILBOX_REFUSALS as error:
            return refusal_for(error)
        logger.info("mailbox_forward_draft_created", user_id=str(user_id))
        return self.drafts_result([draft], **kwargs)


_create_mailbox_forward_draft_tool_instance = CreateMailboxForwardDraftTool()


@connector_tool(
    name="create_mailbox_forward_draft",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    context_save_mode=ContextSaveMode.CURRENT,
    category="write",
)
async def create_mailbox_forward_draft_tool(
    message_id: Annotated[str, "The received e-mail to forward (from get_emails or CONTEXT)"],
    to: Annotated[str, "Recipient(s): addresses or contact names, comma-separated"],
    body: Annotated[str | None, "A note above the forwarded e-mail (optional)"] = None,
    cc: Annotated[str | None, "Copies (optional, comma-separated)"] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Save the forward of a received e-mail as a DRAFT, with its files: nothing is sent.

    Args:
        message_id: The received e-mail.
        to: Recipient(s), addresses or contact names.
        body: A note above the forwarded e-mail.
        cc: Copies.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput with the saved draft.
    """
    user_timezone, _, locale = await get_user_preferences(runtime)
    return await _create_mailbox_forward_draft_tool_instance.execute(
        runtime=runtime,
        message_id=message_id,
        to=to,
        body=body,
        cc=cc,
        user_timezone=user_timezone,
        locale=locale,
    )


__all__ = [
    "CreateMailboxDraftTool",
    "CreateMailboxForwardDraftTool",
    "CreateMailboxReplyDraftTool",
    "ListMailboxDraftsTool",
    "create_mailbox_draft_tool",
    "create_mailbox_forward_draft_tool",
    "create_mailbox_reply_draft_tool",
    "list_mailbox_drafts_tool",
]
