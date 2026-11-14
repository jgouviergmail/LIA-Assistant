"""Gmail thread listing and reading, mixed into ``GoogleGmailClient`` (ADR-262).

The Gmail client had no thread endpoint at all (measured 2026-09-03: no call
to ``/threads`` anywhere) and is frozen at its audited size, so the two calls
the mail RAG source needs live here. Nothing is cached: a thread read here
becomes a document on disk, never a prompt, and a cached copy would only
double the personal content. A conversation (ADR-369, lot 8) is a thread read
as headers, in the answer the three providers share (``mail_conversation``).

The conversations of a listed page (ADR-379) are one thread read each, at the
search's own concurrency. A conversation is read by its NAMED headers and a
partial response: every header of every message made a thread of a hundred
messages weigh 588 KB, against 60 KB that way (measured on a real mailbox,
2026-11-11).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any, Final, Protocol

import structlog

from src.core.config import settings
from src.core.constants import GMAIL_FORMAT_FULL, GMAIL_FORMAT_METADATA
from src.core.mail_vocabulary import DRAFT_LABEL, labels_of
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.mail_conversation import Conversation, conversation_answer
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

#: What a conversation's reader needs of each message: who, to whom, what about, when,
#: its own name, and whether it declares files.
CONVERSATION_HEADERS: Final[tuple[str, ...]] = (
    "From",
    "To",
    "Cc",
    "Reply-To",
    "Subject",
    "Date",
    "Message-ID",
    "Content-Type",
)
#: The parts of a thread that reader needs, as Gmail's partial response names them.
_CONVERSATION_FIELDS: Final = "messages(id,threadId,labelIds,internalDate,snippet,payload/headers)"


class _JsonRequester(Protocol):
    """What the mixin needs from its host: the OAuth client's request seam."""

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class _ConversationHost(Protocol):
    """What a conversation needs from its host."""

    async def get_message(self, message_id: str, format: str = ...) -> dict[str, Any]: ...

    async def get_thread(
        self,
        thread_id: str,
        *,
        format: str = ...,
        metadata_headers: Sequence[str] = ...,
        fields: str | None = ...,
    ) -> dict[str, Any]: ...

    @staticmethod
    def _normalize_message_fields(message: dict[str, Any], format: str) -> None: ...


async def _conversation_thread(host: _ConversationHost, thread_id: str) -> dict[str, Any]:
    """One thread as a conversation's reader needs it: headers named, nothing else."""
    return await host.get_thread(
        thread_id,
        format=GMAIL_FORMAT_METADATA,
        metadata_headers=CONVERSATION_HEADERS,
        fields=_CONVERSATION_FIELDS,
    )


def _said_and_unsent(
    host: _ConversationHost, thread: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A thread's messages in the shared vocabulary: what was said, oldest first, and
    the person's unsent words apart."""
    said: list[dict[str, Any]] = []
    unsent: list[dict[str, Any]] = []
    for item in thread.get("messages") or []:
        host._normalize_message_fields(item, GMAIL_FORMAT_METADATA)
        (unsent if DRAFT_LABEL in labels_of(item) else said).append(item)
    said.sort(key=lambda item: int(item.get("internalDate") or 0))
    return said, unsent


class GmailThreadsMixin:
    """``users.threads`` reads for a client exposing ``_make_request``."""

    async def get_conversation(
        self: _ConversationHost, message_id: str, max_messages: int
    ) -> dict[str, Any]:
        """The thread of a message, headers alone (``mail_conversation``).

        Args:
            message_id: Any message of it.
            max_messages: How many are kept, the newest.

        Returns:
            ``{"messages": [...], "truncated": bool}``, oldest first, drafts left out.
        """
        message = await self.get_message(message_id, format=GMAIL_FORMAT_METADATA)
        thread = await _conversation_thread(self, str(message["threadId"]))
        said, _ = _said_and_unsent(self, thread)
        return conversation_answer(said, max_messages)

    async def conversations_of(
        self: _ConversationHost, messages: Sequence[Mapping[str, Any]], max_messages: int
    ) -> dict[str, Conversation]:
        """What the conversations of listed messages hold (``mail_conversation``).

        Args:
            messages: Listed messages; each names its conversation by ``threadId``.
            max_messages: How many messages of a conversation are kept, the newest.

        Returns:
            One :class:`Conversation` per thread that could be read, by thread id. A
            thread that could not is ABSENT: its messages get no state, and one lost
            thread never costs the page.
        """
        thread_ids = list(
            dict.fromkeys(str(thread) for item in messages if (thread := item.get("threadId")))
        )
        gate = asyncio.Semaphore(settings.emails_search_fetch_concurrency)

        async def _read(thread_id: str) -> Conversation | None:
            async with gate:
                try:
                    thread = await _conversation_thread(self, thread_id)
                except Exception as error:
                    # Facts only: a thread id names a conversation of the person's.
                    logger.warning(
                        "gmail_conversation_read_failed", error_type=type(error).__name__
                    )
                    return None
            said, unsent = _said_and_unsent(self, thread)
            kept = conversation_answer(said, max_messages)
            return Conversation(tuple(kept["messages"]), tuple(unsent), bool(kept["truncated"]))

        found = await asyncio.gather(*(_read(thread_id) for thread_id in thread_ids))
        return {
            thread_id: conversation
            for thread_id, conversation in zip(thread_ids, found, strict=True)
            if conversation is not None
        }

    async def get_thread(
        self: _JsonRequester,
        thread_id: str,
        *,
        format: str = GMAIL_FORMAT_FULL,
        metadata_headers: Sequence[str] = (),
        fields: str | None = None,
    ) -> dict[str, Any]:
        """Read one thread with every message in the requested format.

        Args:
            thread_id: Gmail thread id.
            format: ``full`` (headers + bodies, the default the renderer needs),
                ``metadata`` or ``minimal``.
            metadata_headers: Under ``metadata``, the only headers to return; every
                header when none is named.
            fields: A partial response selector, when only some parts are wanted.

        Returns:
            The thread resource: ``id``, ``historyId``, ``messages`` (each a
            message resource with ``labelIds``, ``internalDate``, ``payload``).
        """
        thread = path_segment(thread_id, connector_type=ConnectorType.GOOGLE_GMAIL)
        params: dict[str, Any] = {"format": format}
        if metadata_headers:
            params["metadataHeaders"] = list(metadata_headers)
        if fields:
            params["fields"] = fields
        return await self._make_request("GET", f"/users/me/threads/{thread}", params=params)

    async def list_threads(
        self: _JsonRequester,
        *,
        label_ids: list[str],
        max_results: int,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """List the threads carrying EVERY label in ``label_ids``.

        Args:
            label_ids: Labels a thread must carry (``labelIds`` is an AND).
            max_results: Page size, hard-capped by ``apply_max_items_limit``.
            page_token: Continuation token from a previous page.

        Returns:
            ``threads`` (``id``, ``historyId``, ``snippet``), ``nextPageToken``
            when there is more, ``resultSizeEstimate``.
        """
        params: dict[str, Any] = {
            "labelIds": list(label_ids),
            "maxResults": apply_max_items_limit(max_results),
        }
        if page_token:
            params["pageToken"] = page_token
        return await self._make_request("GET", "/users/me/threads", params=params)
