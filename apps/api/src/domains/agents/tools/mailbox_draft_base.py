"""What every mailbox draft tool shares (ADR-344).

One base for the tools that read or write the person's mailbox drafts: the
active e-mail provider (Gmail, Outlook or iCloud) resolved by category, the
recipients a person names resolved from their contacts (« Marie » → « Marie
<marie@…> »), a refusal the model can act on for every failure a draft can meet
— told in technical English, by its code (ADR-256, ADR-303) — and one output:
the drafts under the domain's ``emails`` key, as message items with their
``mailbox_draft_id``, the person's own words as the body.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, ClassVar, Final

from langchain.tools import ToolRuntime

from src.core.exceptions import ConnectorAPIError
from src.core.field_names import FIELD_BODY, FIELD_SET_ASIDE_ON_PAGE
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import resolve_recipients_to_emails
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.mail_folders import (
    EXCLUDES_ITS_FOLDER,
    MAIL_QUERY_DATE_FORMAT_ERROR,
    MailFolderAmbiguousError,
    MailFolderLookupError,
    MailFolderNotFoundError,
)
from src.domains.connectors.clients.mailbox_drafts import (
    MailboxDraftChangedError,
    MailboxDraftNotFoundError,
    MailboxFolderUnavailableError,
    MailboxOperationUnavailableError,
)
from src.domains.connectors.clients.normalizers.reply_trimming import split_quoted_history
from src.domains.connectors.models import ConnectorType

#: Whether the body shown is the person's words above a quoted message.
FIELD_QUOTES_HISTORY: Final = "quotes_history"

#: Every failure a draft operation turns into a refusal (never an internal error).
MAILBOX_REFUSALS: Final = (
    MailboxDraftChangedError,
    MailboxDraftNotFoundError,
    MailboxFolderUnavailableError,
    MailboxOperationUnavailableError,
    ConnectorAPIError,
    ValueError,
)

#: What a mail search refuses of its query — a folder the mailbox cannot
#: resolve, said with the folders that exist; a date it cannot read; a folder it
#: excludes and reads — a refusal the model can act on, never an internal error.
MAIL_SEARCH_REFUSALS: Final = (
    MailFolderLookupError,
    MailboxFolderUnavailableError,
    MailboxOperationUnavailableError,
    ValueError,
)

#: Aggregate folder-name budget; external labels remain data, never instructions.
_FOLDER_REFUSAL_MAX_CHARS: Final = 300
_FOLDER_REFUSAL_MAX_CHOICES: Final = 10


def refusal(code: ToolErrorCode, message: str) -> dict[str, Any]:
    """A refusal, as ``execute_api_call`` returns it."""
    return {"error_code": code.value, "message": message}


def _folder_refusal(
    code: ToolErrorCode,
    message: str,
    error: MailFolderLookupError,
    names: Sequence[str],
    *,
    complete: bool = True,
) -> dict[str, Any]:
    """Offer bounded whole paths as external data, preserving the listing's limits."""
    selected: list[str] = []
    remaining = _FOLDER_REFUSAL_MAX_CHARS
    if len(names) > _FOLDER_REFUSAL_MAX_CHOICES:
        complete = False
    for name in names[:_FOLDER_REFUSAL_MAX_CHOICES]:
        if len(name) > remaining:
            complete = False
            break
        selected.append(name)
        remaining -= len(name)
    details = {
        "requested": error.requested[:_FOLDER_REFUSAL_MAX_CHARS],
        "folders": selected,
        "complete": complete,
    }
    if not complete:
        message += " The folder listing was cut."
    data = wrap_external_content(
        json.dumps(details, ensure_ascii=False), "mailbox_folders", "mailbox_folder_choices"
    )
    return refusal(code, f"{message}\n{data}")


def refusal_for(error: Exception) -> dict[str, Any]:
    """The refusal a mailbox failure deserves, by its type — never its wording.

    Args:
        error: One of :data:`MAILBOX_REFUSALS` or :data:`MAIL_SEARCH_REFUSALS`.

    Returns:
        The refusal to hand back to the model.

    Raises:
        ConnectorAPIError: Any provider refusal but a 404, re-raised: the base
            tool classifies it and raises the connector notice it calls for.
    """
    if isinstance(error, MailboxDraftChangedError):
        if error.copy_saved:
            return refusal(
                ToolErrorCode.CONFLICT,
                "A draft was saved, but its identity or cleanup could not be verified. "
                "Nothing was sent. List the drafts again before another change.",
            )
        return refusal(
            ToolErrorCode.CONFLICT,
            "The draft changed before the edit: nothing was modified. Read it again before editing.",
        )
    if isinstance(error, MailboxDraftNotFoundError):
        return refusal(
            ToolErrorCode.NOT_FOUND,
            "This draft is no longer in the mailbox (sent, deleted or moved): list the "
            "drafts again for a current mailbox_draft_id.",
        )
    if isinstance(error, MailFolderNotFoundError):
        return _folder_refusal(
            ToolErrorCode.NOT_FOUND,
            "No mail folder matches this name. Choose an available full path from the data.",
            error,
            error.available,
            complete=error.complete,
        )
    if isinstance(error, MailFolderAmbiguousError):
        return _folder_refusal(
            ToolErrorCode.DISAMBIGUATION_REQUIRED,
            "Several mail folders match this name. Choose one full path from the data.",
            error,
            error.candidates,
        )
    if isinstance(error, MailboxFolderUnavailableError):
        return refusal(ToolErrorCode.NOT_FOUND, "The mailbox has no folder for this operation.")
    if isinstance(error, MailboxOperationUnavailableError):
        return refusal(
            ToolErrorCode.DEPENDENCY_ERROR,
            "The mailbox server cannot safely remove only the requested messages. "
            "Nothing was changed; use the mailbox application for this operation.",
        )
    if isinstance(error, ConnectorAPIError):
        if error.status_code != 404:
            raise error
        return refusal(ToolErrorCode.NOT_FOUND, "The message is not in the mailbox.")
    message = (
        str(error)
        if isinstance(error, ValueError)
        and str(error) in {EXCLUDES_ITS_FOLDER, MAIL_QUERY_DATE_FORMAT_ERROR}
        else "The mailbox could not read a parameter. Check recipients, dates and message identifiers."
    )
    return refusal(ToolErrorCode.INVALID_PARAM_VALUE, message)


def one_line(text: str | None) -> str | None:
    """A subject on one line: a line break in a header would end it."""
    return " ".join(text.split()) if text is not None else None


def keep_own_words(draft: dict[str, Any]) -> None:
    """Give the draft the person's own words; say whether it quotes a message.

    The quoted history stays in the mailbox: an edit keeps it there, and the
    model would otherwise read the original twice.
    """
    body = draft.get(FIELD_BODY)
    own, history = split_quoted_history(body if isinstance(body, str) else "")
    draft[FIELD_BODY] = own.strip()
    draft[FIELD_QUOTES_HISTORY] = bool(history.strip())


def with_history(own_words: str, history: str) -> str:
    """New words above the history a draft already quoted."""
    if not history.strip():
        return own_words
    return f"{own_words.rstrip()}\n\n{history.lstrip(chr(10))}"


class MailboxDraftTool(ToolOutputMixin, ConnectorTool[GoogleGmailClient]):
    """A tool acting on the person's mailbox drafts, whatever their provider."""

    connector_type = ConnectorType.GOOGLE_GMAIL
    client_class = GoogleGmailClient
    functional_category = "email"
    registry_enabled = True

    #: Recipient fields resolved from the person's contacts before the call.
    RECIPIENT_FIELDS: ClassVar[tuple[str, ...]] = ()
    #: How the drafts the tool returns enter the conversation context.
    SAVE_MODE: ClassVar[ContextSaveMode] = ContextSaveMode.CURRENT

    async def execute(
        self,
        runtime: ToolRuntime[LiaRuntimeContext, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Resolve the named recipients, then run the tool.

        A name the contacts cannot resolve is kept as written; the mailbox
        client then refuses it as an address it cannot read.
        """
        for field in self.RECIPIENT_FIELDS:
            value = kwargs.get(field)
            if value:
                resolved = await resolve_recipients_to_emails(runtime, value, field)
                if resolved:
                    kwargs[field] = resolved
        return await super().execute(runtime=runtime, **kwargs)

    @staticmethod
    def drafts_result(drafts: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """The drafts a tool returns, the person's own words as their body."""
        for draft in drafts:
            keep_own_words(draft)
        return {
            "emails": drafts,
            "user_timezone": kwargs.get("user_timezone", "UTC"),
            "locale": kwargs.get("locale"),
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """A refusal, or the drafts as message cards entering the context."""
        if "error_code" in result:
            return UnifiedToolOutput.failure(
                message=str(result["message"]), error_code=str(result["error_code"])
            )
        output = self.build_emails_output(
            emails=result.get("emails", []),
            query=result.get("query"),
            from_cache=False,
            user_timezone=result.get("user_timezone", "UTC"),
            locale=result.get("locale"),
            result_size_estimate=result.get("result_size_estimate"),
            next_page_token=result.get("next_page_token"),
            **{FIELD_SET_ASIDE_ON_PAGE: result.get(FIELD_SET_ASIDE_ON_PAGE)},
        )
        output.context_save_mode = self.SAVE_MODE
        return output


__all__ = [
    "FIELD_QUOTES_HISTORY",
    "MAILBOX_REFUSALS",
    "MAIL_SEARCH_REFUSALS",
    "MailboxDraftTool",
    "keep_own_words",
    "one_line",
    "refusal",
    "refusal_for",
    "with_history",
]
