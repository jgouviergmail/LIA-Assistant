"""Editing and trashing the person's mailbox drafts (ADR-344).

An edit changes what the person asked and nothing else: a field given replaces
its value, an instruction ("make it shorter") is applied by the draft modifier
to the person's OWN words, and the history a reply quotes stays below them —
the quote is the mailbox's, never rewritten. A body rewritten as plain text
loses an HTML draft's formatting, never its files.

Deleting moves drafts to the mailbox's trash, where they stay recoverable
(measured on Gmail 2026-10-13; Outlook's Deleted Items; iCloud's trash folder).
The drafts are named one way — their handles, or a search and a count, or « all »
— and at most ``email_drafts_bulk_max`` move per call: what remains is stated,
never dropped, and what each draft became is said draft by draft.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.core.field_names import FIELD_BODY, FIELD_MAILBOX_DRAFT_ID, FIELD_MAILBOX_DRAFT_REVISION
from src.core.run_config import run_id_of
from src.domains.agents.constants import AGENT_EMAIL, CONTEXT_DOMAIN_EMAILS
from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    tool_runtime_context,
)
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.emails.mailbox_drafts_manifests import DELETE_MAX_RESULTS_DESCRIPTION
from src.domains.agents.services.hitl.draft_modifier import get_draft_modification_service
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.lookup_parameters import bounded_count
from src.domains.agents.tools.mailbox_draft_base import (
    MAILBOX_REFUSALS,
    MailboxDraftTool,
    one_line,
    refusal,
    refusal_for,
    with_history,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    get_user_preferences,
    resolve_recipients_to_emails,
)
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.mailbox_drafts import TRASH_NOT_FOUND, ensure_draft_revision
from src.domains.connectors.clients.normalizers.reply_trimming import split_quoted_history

logger = structlog.get_logger(__name__)

#: The fields an edit may change, as the mailbox clients name them.
EDITABLE_FIELDS: tuple[str, ...] = ("to", "cc", "bcc", "subject", "body")


def _edited_fields(
    generated: dict[str, str], given: dict[str, Any], history: str
) -> dict[str, Any]:
    """Explicit values take priority; a rewritten body retains its quoted history."""
    changes: dict[str, Any] = {**generated, **given}
    if FIELD_BODY in changes:
        changes[FIELD_BODY] = with_history(str(changes[FIELD_BODY]), history)
    if "subject" in changes:
        changes["subject"] = one_line(str(changes["subject"]))
    return changes


# ============================================================================
# UPDATE
# ============================================================================


class UpdateMailboxDraftTool(MailboxDraftTool):
    """Change a draft's fields, by value or by instruction."""

    RECIPIENT_FIELDS = ("to", "cc", "bcc")

    def __init__(self) -> None:
        """Initialise the draft edit tool."""
        super().__init__(tool_name="update_mailbox_draft_tool", operation="update_draft")

    async def _instructed_changes(
        self, current: dict[str, Any], own_words: str, instructions: str
    ) -> dict[str, str]:
        """What an instruction changes, applied to the person's own words."""
        runtime = self.runtime
        context = tool_runtime_context(runtime) if runtime is not None else None
        config = runtime.config if runtime is not None else None
        original = {name: str(current.get(name) or "") for name in EDITABLE_FIELDS}
        original[FIELD_BODY] = own_words
        modified = await get_draft_modification_service().modify(
            original_draft=original,
            instructions=instructions,
            draft_type="email",
            user_language=self.get_user_language(),
            run_id=run_id_of(config) if config is not None else None,
            sender_name=context.display_name if context is not None else None,
            config=config,
        )
        return {
            name: str(modified[name])
            for name in EDITABLE_FIELDS
            if modified.get(name) is not None and str(modified[name]) != original[name]
        }

    async def _resolve_instructed_recipients(
        self, changes: dict[str, str], given: dict[str, Any]
    ) -> None:
        """Resolve the names an instruction put in a recipient field (« add Paul in copy »).

        The modifier writes the name it read; a field the person also gave is
        theirs and needs no lookup.
        """
        for field in self.RECIPIENT_FIELDS:
            if changes.get(field) and field not in given:
                resolved = await resolve_recipients_to_emails(self.runtime, changes[field], field)
                changes[field] = str(resolved or changes[field])

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Apply the changes to the live draft; its quoted history stays."""
        draft_id = str(kwargs.get(FIELD_MAILBOX_DRAFT_ID) or "")
        given = {name: kwargs[name] for name in EDITABLE_FIELDS if kwargs.get(name) is not None}
        instructions = str(kwargs.get("instructions") or "").strip()
        if not draft_id:
            return refusal(ToolErrorCode.MISSING_REQUIRED_PARAM, "mailbox_draft_id is required.")
        if not given and not instructions:
            return refusal(
                ToolErrorCode.INVALID_INPUT,
                "Nothing to change: give the fields to change, or an instruction.",
            )
        try:
            current = await client.get_draft(draft_id)
            revision = current.get(FIELD_MAILBOX_DRAFT_REVISION)
            if not isinstance(revision, str) or not revision.strip():
                return refusal(
                    ToolErrorCode.INVALID_RESPONSE_FORMAT,
                    "The mailbox did not provide the complete draft revision: nothing was modified.",
                )
            own_words, history = split_quoted_history(str(current.get(FIELD_BODY) or ""))
            changes = (
                await self._instructed_changes(current, own_words.strip(), instructions)
                if instructions
                else {}
            )
            await self._resolve_instructed_recipients(changes, given)
            if instructions:
                ensure_draft_revision(await client.get_draft(draft_id), revision)
            changes = _edited_fields(changes, given, history)
            draft = await client.update_draft(draft_id, expected_revision=revision, **changes)
        except MAILBOX_REFUSALS as error:
            return refusal_for(error)
        logger.info(
            "mailbox_draft_updated",
            user_id=str(user_id),
            fields=sorted(changes),
            instructed=bool(instructions),
        )
        return self.drafts_result([draft], **kwargs)


_update_mailbox_draft_tool_instance = UpdateMailboxDraftTool()


@connector_tool(
    name="update_mailbox_draft",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    context_save_mode=ContextSaveMode.CURRENT,
    category="write",
)
async def update_mailbox_draft_tool(
    mailbox_draft_id: Annotated[str, "The draft's handle (from list_mailbox_drafts or CONTEXT)"],
    to: Annotated[str | None, "New recipient(s); empty string clears them"] = None,
    cc: Annotated[str | None, "New copies; empty string clears them"] = None,
    bcc: Annotated[str | None, "New blind copies; empty string clears them"] = None,
    subject: Annotated[str | None, "New subject"] = None,
    body: Annotated[str | None, "New text, replacing the person's own words"] = None,
    instructions: Annotated[
        str | None, "A change to apply ('make it shorter', 'add that I am late')"
    ] = None,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Edit a DRAFT in the person's mailbox: nothing is sent, no confirmation.

    Fields not given stay as they are; the history a reply quotes stays below
    the person's words. On iCloud the edited draft gets a new mailbox_draft_id.

    Args:
        mailbox_draft_id: The draft's handle.
        to: New recipient(s).
        cc: New copies.
        bcc: New blind copies.
        subject: New subject.
        body: New text.
        instructions: A change to apply to the draft.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput with the edited draft.
    """
    user_timezone, _, locale = await get_user_preferences(runtime)
    return await _update_mailbox_draft_tool_instance.execute(
        runtime=runtime,
        mailbox_draft_id=mailbox_draft_id,
        to=to,
        cc=cc,
        bcc=bcc,
        subject=subject,
        body=body,
        instructions=instructions,
        user_timezone=user_timezone,
        locale=locale,
    )


# ============================================================================
# DELETE
# ============================================================================


def _named_handles(value: object) -> list[str]:
    """The handles a call names; one given as text is one draft, never its characters."""
    named = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    return [str(handle).strip() for handle in named if str(handle).strip()]


def _asked_count(value: object) -> int | None:
    """The count the person gave, or None when they gave none."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _more_remaining(listing: dict[str, Any], served: int) -> bool:
    """Whether the mailbox holds more matching drafts than one call served."""
    total = listing.get("resultSizeEstimate")
    if isinstance(total, int) and not isinstance(total, bool):
        return total > served
    return bool(listing.get("next_page_token"))


class DeleteMailboxDraftsTool(MailboxDraftTool):
    """Move drafts to the mailbox's trash, named one way."""

    SAVE_MODE = ContextSaveMode.NONE

    def __init__(self) -> None:
        """Initialise the draft deletion tool."""
        super().__init__(tool_name="delete_mailbox_drafts_tool", operation="trash_drafts")

    async def _selection(
        self,
        client: GoogleGmailClient,
        *,
        query: str,
        max_results: int | None,
        all_drafts: bool,
    ) -> tuple[list[str], dict[str, dict[str, Any]], bool]:
        """The drafts a search, a count or « all » names; whether more remain."""
        bound = settings.email_drafts_bulk_max
        size = bound if all_drafts else bounded_count(max_results, bound)
        listing = await client.list_drafts(query=query, max_results=size, headers_only=True)
        drafts = list(listing.get("messages", []))
        handles = [str(draft[FIELD_MAILBOX_DRAFT_ID]) for draft in drafts]
        # A count within the bound is all the person asked for: nothing « remains ».
        # Beyond it, the call moved the bound and says what is left.
        asked_beyond = max_results is None or max_results > bound
        more = asked_beyond and _more_remaining(listing, len(handles))
        return handles, {str(d[FIELD_MAILBOX_DRAFT_ID]): d for d in drafts}, more

    async def execute_api_call(
        self,
        client: GoogleGmailClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Select the drafts, trash them, say what became of each."""
        handles = _named_handles(kwargs.get("mailbox_draft_ids"))
        query = str(kwargs.get("query") or "").strip()
        max_results = _asked_count(kwargs.get("max_results"))
        all_drafts = bool(kwargs.get("all_drafts"))
        if kwargs.get("max_results") is not None and max_results is None:
            return refusal(
                ToolErrorCode.INVALID_INPUT,
                "max_results must be a positive integer: no drafts were moved.",
            )
        if sum((bool(handles), bool(query or max_results), all_drafts)) != 1:
            return refusal(
                ToolErrorCode.INVALID_INPUT,
                "Name the drafts one way: mailbox_draft_ids, or query and/or max_results, "
                "or all_drafts=true.",
            )
        bound = settings.email_drafts_bulk_max
        described: dict[str, dict[str, Any]] = {}
        try:
            if handles:
                unique = list(dict.fromkeys(handles))
                handles, more = unique[:bound], len(unique) > bound
            else:
                handles, described, more = await self._selection(
                    client, query=query, max_results=max_results, all_drafts=all_drafts
                )
            result = (
                await client.trash_drafts(handles) if handles else {"trashed": [], "failed": []}
            )
        except MAILBOX_REFUSALS as error:
            return refusal_for(error)
        trashed = [
            {
                FIELD_MAILBOX_DRAFT_ID: handle,
                "subject": described.get(handle, {}).get("subject"),
                "to": described.get(handle, {}).get("to"),
            }
            for handle in result["trashed"]
        ]
        logger.info(
            "mailbox_drafts_deleted",
            user_id=str(user_id),
            trashed=len(trashed),
            failed=len(result["failed"]),
            more_remaining=more,
        )
        return {
            "emails": trashed,
            "failed": result["failed"],
            "more_remaining": more,
            "complete": not result["failed"] and not more,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """What became of each draft; a call that trashed none of the named ones fails."""
        if "error_code" in result:
            return super().format_registry_response(result)
        trashed, failed = result["emails"], result["failed"]
        if failed and not trashed:
            gone = all(f["status"] == TRASH_NOT_FOUND for f in failed)
            return UnifiedToolOutput.failure(
                message=(
                    "None of these drafts is in the mailbox any more: list them again."
                    if gone
                    else "The mailbox moved none of these drafts to the trash."
                ),
                error_code=(
                    ToolErrorCode.NOT_FOUND.value
                    if gone
                    else ToolErrorCode.EXTERNAL_API_ERROR.value
                ),
            )
        output = UnifiedToolOutput.data_success(
            message=f"[mailbox drafts] {len(trashed)} moved to the trash, {len(failed)} not",
            structured_data=result,
        )
        output.context_save_mode = self.SAVE_MODE
        return output


_delete_mailbox_drafts_tool_instance = DeleteMailboxDraftsTool()


@connector_tool(
    name="delete_mailbox_drafts",
    agent_name=AGENT_EMAIL,
    context_domain=CONTEXT_DOMAIN_EMAILS,
    context_save_mode=ContextSaveMode.NONE,
    category="write",
)
async def delete_mailbox_drafts_tool(
    mailbox_draft_ids: Annotated[
        list[str] | None, "The drafts' handles (from list_mailbox_drafts or CONTEXT)"
    ] = None,
    query: Annotated[str | None, "Or a search among the drafts: to:/subject:/words"] = None,
    max_results: Annotated[int | None, DELETE_MAX_RESULTS_DESCRIPTION] = None,
    all_drafts: Annotated[bool, "Or every draft ('delete all my drafts')"] = False,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Move the person's mailbox DRAFTS to the trash, where they stay recoverable.

    Name them ONE way: their handles, or a search and/or a count, or all of
    them. Each call moves a bounded number and says whether more remain.

    Args:
        mailbox_draft_ids: The drafts' handles.
        query: A search among the drafts.
        max_results: How many of the newest drafts.
        all_drafts: Every draft.
        runtime: Tool runtime (injected).

    Returns:
        UnifiedToolOutput saying what became of each draft.
    """
    return await _delete_mailbox_drafts_tool_instance.execute(
        runtime=runtime,
        mailbox_draft_ids=mailbox_draft_ids,
        query=query,
        max_results=max_results,
        all_drafts=all_drafts,
    )


__all__ = [
    "DeleteMailboxDraftsTool",
    "UpdateMailboxDraftTool",
    "delete_mailbox_drafts_tool",
    "update_mailbox_draft_tool",
]
