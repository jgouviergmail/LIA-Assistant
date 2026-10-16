"""Mailbox drafts on Outlook through Microsoft Graph, mixed into ``MicrosoftOutlookClient`` (ADR-344).

A Graph draft is a message with ``isDraft`` in the Drafts folder; its handle,
published as ``mailbox_draft_id``, is the message id. What this mixin rests on,
from Graph's documentation (the test account's Outlook connector could not be
reconnected for a live measurement — ADR-344 says so):

* ``createReply``/``createReplyAll``/``createForward`` answer the draft, its body
  quoting the original — and the ``comment`` parameter is NOT written into that
  body (a documented known issue): the person's words are written by a PATCH,
  above the quote, and a draft whose words could not be written is removed;
* ``createForward`` refuses a draft without a recipient;
* only a draft's body and recipients can be changed, so every operation on a
  handle first checks that it designates a draft still in the Drafts folder —
  a received message's id must never be edited, trashed or sent as a draft;
* a query is ONE request Graph accepts (``graph_mail_query``): a search keeps
  its terms and the dates are checked on its page, a filter is led by the last
  save (``InefficientFilter`` otherwise);
* a creation and a send are attempted once: retried after a timeout, they could
  leave two drafts or send twice.

Lives beside the client, which keeps the reads and sends of received mail.
"""

from __future__ import annotations

import html
import re
from collections.abc import Sequence
from typing import Any, Final, Protocol
from uuid import UUID

import structlog

from src.core.exceptions import ConnectorAPIError
from src.core.field_names import (
    FIELD_MAILBOX_DRAFT_ID,
    FIELD_MAILBOX_DRAFT_REVISION,
    FIELD_SET_ASIDE_ON_PAGE,
)
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.mailbox_drafts import (
    MailboxDraftNotFoundError,
    ensure_draft_revision,
    trash_each,
)
from src.domains.connectors.clients.normalizers.graph_mail_query import (
    GraphMailQuery,
    graph_mail_query,
)
from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
    build_graph_recipients,
    normalize_graph_message,
)

logger = structlog.get_logger(__name__)

_LISTING: Final = "/me/mailFolders/drafts/messages"
_DRAFTS_FOLDER: Final = "/me/mailFolders/drafts"
#: A draft's date: the listing sorts on its last save, filters on it and shows it.
_SAVED: Final = "lastModifiedDateTime"
_HEADER_FIELDS: Final = (
    "id,conversationId,subject,from,toRecipients,ccRecipients,bccRecipients,bodyPreview,"
    "receivedDateTime,lastModifiedDateTime,isRead,isDraft,hasAttachments,flag,importance,"
    "webLink,parentFolderId,changeKey"
)
_FULL_FIELDS: Final = f"{_HEADER_FIELDS},body"
_LOCATION_FIELDS: Final = "id,isDraft,parentFolderId,changeKey"
_ATTACHMENTS: Final = "attachments($select=id,name,contentType,size)"

#: What a Graph message id is made of (base64, ``=`` padding); ``/``, ``.``
#: and the rest never reach a URL path, where they would leave the message.
_MESSAGE_ID: Final = re.compile(r"[A-Za-z0-9=_+-]+")
_BODY_OPEN: Final = re.compile(r"<body\b[^>]*>", re.IGNORECASE)


class _OutlookDraftsHost(Protocol):
    """What the mixin needs from its host."""

    user_id: UUID

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

    async def _make_request_full_url(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def _is_graph_continuation(self, url: str) -> bool: ...

    async def _fetch_message(self, message_id: str, *, full: bool = True) -> dict[str, Any]: ...

    async def _live_draft(
        self, draft_id: str, *, folder_id: str | None = None, full: bool = True
    ) -> dict[str, Any]: ...

    async def _drafts_folder_id(self) -> str: ...

    async def _write_words(
        self, created: dict[str, Any], words: str | None, *, is_html: bool
    ) -> str: ...


def _checked(message_id: str) -> str:
    """The id itself, or not found when it cannot be a Graph message id."""
    if not _MESSAGE_ID.fullmatch(message_id):
        raise MailboxDraftNotFoundError(message_id)
    return message_id


def _as_html(text: str) -> str:
    """Plain text as HTML: escaped, its line breaks kept."""
    return html.escape(text).replace("\n", "<br>")


def with_own_words(current: dict[str, Any], words: str, *, is_html: bool) -> dict[str, str]:
    """The draft's body with the person's words above what Graph wrote (the quote).

    Args:
        current: The draft's Graph ``body`` (``contentType``, ``content``).
        words: The person's words.
        is_html: Whether ``words`` is HTML (text is escaped, lines kept).

    Returns:
        The Graph ``body`` to PATCH.
    """
    content = str(current.get("content") or "")
    html_body = str(current.get("contentType") or "html").lower() == "html"
    if not html_body and not is_html:
        return {"contentType": "Text", "content": f"{words}\n\n{content}" if content else words}
    if not html_body:
        content = _as_html(content)
    own = words if is_html else f"<div>{_as_html(words)}</div>"
    opening = _BODY_OPEN.search(content)
    cut = opening.end() if opening else 0
    return {"contentType": "HTML", "content": f"{content[:cut]}{own}{content[cut:]}"}


def _as_draft(message: dict[str, Any]) -> dict[str, Any]:
    """A Graph message in the draft vocabulary: dated by its last save, its quote kept."""
    saved_at = message.get("lastModifiedDateTime") or message.get("receivedDateTime")
    draft = normalize_graph_message({**message, "receivedDateTime": saved_at}, keep_quoted=True)
    draft[FIELD_MAILBOX_DRAFT_ID] = str(message.get("id", ""))
    revision = message.get("changeKey")
    draft[FIELD_MAILBOX_DRAFT_REVISION] = revision if isinstance(revision, str) else ""
    return draft


def _listing_params(
    translated: GraphMailQuery, max_results: int, *, headers_only: bool
) -> dict[str, Any]:
    """The drafts folder's listing parameters for a translated query.

    A recipient, a subject or words make it a search (Graph cannot combine one
    with a filter: the dates are then checked on the page); without one the
    newest saves come first, filtered on the last save.
    """
    return {
        "$top": apply_max_items_limit(max_results),
        "$select": _HEADER_FIELDS if headers_only else _FULL_FIELDS,
        **translated.params,
    }


class OutlookDraftsMixin:
    """The person's own unsent messages on Graph."""

    async def _drafts_folder_id(self: _OutlookDraftsHost) -> str:
        folder = await self._make_request("GET", _DRAFTS_FOLDER, {"$select": "id"})
        return str(folder.get("id", ""))

    async def _fetch_message(
        self: _OutlookDraftsHost, message_id: str, *, full: bool = True
    ) -> dict[str, Any]:
        """One message by id — its location only, or whole with its files listed."""
        params: dict[str, Any] = {"$select": _FULL_FIELDS if full else _LOCATION_FIELDS}
        if full:
            params["$expand"] = _ATTACHMENTS
        try:
            return await self._make_request("GET", f"/me/messages/{_checked(message_id)}", params)
        except ConnectorAPIError as error:
            if error.status_code == 404:
                raise MailboxDraftNotFoundError(message_id) from error
            raise

    async def _live_draft(
        self: _OutlookDraftsHost,
        draft_id: str,
        *,
        folder_id: str | None = None,
        full: bool = True,
    ) -> dict[str, Any]:
        """The message ``draft_id`` names, when it is a draft still in the Drafts folder.

        Raises:
            MailboxDraftNotFoundError: Unknown id, a received or sent message,
                or a draft moved out of the Drafts folder (the trash included).
        """
        message = await self._fetch_message(draft_id, full=full)
        folder = folder_id or await self._drafts_folder_id()
        if not message.get("isDraft") or message.get("parentFolderId") != folder:
            raise MailboxDraftNotFoundError(draft_id)
        return message

    async def _write_words(
        self: _OutlookDraftsHost, created: dict[str, Any], words: str | None, *, is_html: bool
    ) -> str:
        """Write the person's words into a draft Graph just created; its id.

        A draft whose words could not be written is removed: left in place, it
        would be an empty reply the person never asked for.
        """
        draft_id = str(created.get("id", ""))
        if not words:
            return draft_id
        body = with_own_words(created.get("body") or {}, words, is_html=is_html)
        try:
            await self._make_request("PATCH", f"/me/messages/{draft_id}", json_data={"body": body})
        except Exception:
            try:
                await self._make_request("DELETE", f"/me/messages/{draft_id}")
            except Exception as cleanup:
                logger.warning(
                    "outlook_mailbox_draft_rollback_failed",
                    user_id=str(self.user_id),
                    error_type=type(cleanup).__name__,
                )
            raise
        return draft_id

    async def list_drafts(
        self: _OutlookDraftsHost,
        query: str = "",
        max_results: int = 10,
        page_token: str | None = None,
        headers_only: bool = True,
    ) -> dict[str, Any]:
        """The Drafts folder, newest saves first unless a search orders by relevance.

        Args:
            query: Gmail-style query (``to:``, ``subject:``, words, dates).
            max_results: Page size.
            page_token: Graph's ``@odata.nextLink`` of a previous page — accepted
                only on the Graph host: the request carries the person's token.
            headers_only: Leave the bodies out.

        Returns:
            ``messages`` (each with its ``mailbox_draft_id``), Graph's
            ``@odata.count`` when stated, ``next_page_token``, and
            ``set_aside_on_page`` when a page check set drafts aside.

        Raises:
            ValueError: A ``page_token`` that does not point at the Graph host,
                or a date operator whose value is not a date.
        """
        translated = graph_mail_query(query, sort_property=_SAVED)
        if page_token:
            if not self._is_graph_continuation(page_token):
                raise ValueError("page_token must be a Graph continuation url")
            response = await self._make_request_full_url("GET", page_token)
        else:
            params = _listing_params(translated, max_results, headers_only=headers_only)
            response = await self._make_request("GET", _LISTING, params)
        kept, set_aside = translated.screen(response.get("value", []))
        listing: dict[str, Any] = {
            "messages": [_as_draft(m) for m in kept if m.get("isDraft")],
            "resultSizeEstimate": response.get("@odata.count"),
            "next_page_token": response.get("@odata.nextLink"),
        }
        if set_aside:
            listing[FIELD_SET_ASIDE_ON_PAGE] = set_aside
        return listing

    async def get_draft(self: _OutlookDraftsHost, draft_id: str) -> dict[str, Any]:
        """One draft, whole, its files listed and its quoted history kept."""
        return _as_draft(await self._live_draft(draft_id))

    async def create_draft(
        self: _OutlookDraftsHost,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """Save a new draft; an empty ``to`` leaves the recipient unset.

        Raises:
            ValueError: An address that cannot be read.
        """
        payload: dict[str, Any] = {
            "subject": subject,
            "body": {"contentType": "HTML" if is_html else "Text", "content": body},
        }
        for key, value in (("toRecipients", to), ("ccRecipients", cc), ("bccRecipients", bcc)):
            if value:
                payload[key] = build_graph_recipients(value)
        created = await self._make_request("POST", "/me/messages", json_data=payload, max_retries=1)
        logger.info("outlook_mailbox_draft_created", user_id=str(self.user_id))
        return _as_draft(await self._fetch_message(str(created.get("id", ""))))

    async def create_reply_draft(
        self: _OutlookDraftsHost,
        message_id: str,
        body: str,
        reply_all: bool = False,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """Save the reply to ``message_id`` as a draft, addressed by Graph itself."""
        action = "createReplyAll" if reply_all else "createReply"
        created = await self._make_request(
            "POST", f"/me/messages/{_checked(message_id)}/{action}", json_data={}, max_retries=1
        )
        draft_id = await self._write_words(created, body, is_html=is_html)
        logger.info("outlook_mailbox_reply_draft_created", user_id=str(self.user_id))
        return _as_draft(await self._fetch_message(draft_id))

    async def create_forward_draft(
        self: _OutlookDraftsHost,
        message_id: str,
        to: str,
        body: str | None = None,
        cc: str | None = None,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """Save the forward of ``message_id`` as a draft; Graph carries the files.

        Raises:
            ValueError: An address that cannot be read.
        """
        message: dict[str, Any] = {"toRecipients": build_graph_recipients(to)}
        if cc:
            message["ccRecipients"] = build_graph_recipients(cc)
        created = await self._make_request(
            "POST",
            f"/me/messages/{_checked(message_id)}/createForward",
            json_data={"message": message},
            max_retries=1,
        )
        draft_id = await self._write_words(created, body, is_html=is_html)
        logger.info("outlook_mailbox_forward_draft_created", user_id=str(self.user_id))
        return _as_draft(await self._fetch_message(draft_id))

    async def update_draft(
        self: _OutlookDraftsHost,
        draft_id: str,
        *,
        to: str | None = None,
        cc: str | None = None,
        bcc: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        """Change the fields given (None keeps one, "" clears it), keep the rest.

        A new body is plain text: an HTML draft loses its formatting, never its
        files.

        Raises:
            MailboxDraftNotFoundError: The id names no draft in the Drafts folder.
            ValueError: An address that cannot be read (nothing is saved).
        """
        current = await self._live_draft(draft_id, full=False)
        ensure_draft_revision(
            {FIELD_MAILBOX_DRAFT_REVISION: current.get("changeKey")}, expected_revision
        )
        changes: dict[str, Any] = {}
        if subject is not None:
            changes["subject"] = subject
        for key, value in (("toRecipients", to), ("ccRecipients", cc), ("bccRecipients", bcc)):
            if value is not None:
                changes[key] = build_graph_recipients(value)
        if body is not None:
            changes["body"] = {"contentType": "Text", "content": body}
        if changes:
            await self._make_request(
                "PATCH", f"/me/messages/{current['id']}", json_data=changes, max_retries=1
            )
            logger.info("outlook_mailbox_draft_updated", user_id=str(self.user_id))
        return _as_draft(await self._fetch_message(str(current["id"])))

    async def trash_drafts(self: _OutlookDraftsHost, draft_ids: Sequence[str]) -> dict[str, Any]:
        """Move drafts to Deleted Items, where they stay recoverable.

        Returns:
            ``{"trashed": [ids], "failed": [{"mailbox_draft_id", "status"}]}``.
        """
        folder_id = await self._drafts_folder_id()

        async def trash_one(draft_id: str) -> None:
            await self._live_draft(draft_id, folder_id=folder_id, full=False)
            await self._make_request(
                "POST", f"/me/messages/{draft_id}/move", json_data={"destinationId": "deleteditems"}
            )

        result = await trash_each(draft_ids, trash_one)
        logger.info(
            "outlook_mailbox_drafts_trashed",
            user_id=str(self.user_id),
            trashed=len(result["trashed"]),
            failed=len(result["failed"]),
        )
        return result

    async def send_draft(self: _OutlookDraftsHost, draft_id: str) -> dict[str, Any]:
        """Send a draft as it is stored — one attempt, never retried.

        The caller reads the draft first. Graph answers 202 with no body: the
        sent copy's id is not known.

        Raises:
            MailboxDraftNotFoundError: Unknown id.
        """
        try:
            await self._make_request(
                "POST", f"/me/messages/{_checked(draft_id)}/send", max_retries=1
            )
        except ConnectorAPIError as error:
            if error.status_code == 404:
                raise MailboxDraftNotFoundError(draft_id) from error
            raise
        logger.info("outlook_mailbox_draft_sent", user_id=str(self.user_id))
        # Graph sends and files in one act: the draft never stays behind.
        return {"id": None, FIELD_MAILBOX_DRAFT_ID: draft_id, "draft_kept": False}


__all__ = ["OutlookDraftsMixin", "with_own_words"]
