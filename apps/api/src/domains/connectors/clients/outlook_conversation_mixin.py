"""A conversation on Outlook: Graph keeps a ``conversationId`` (ADR-369 lot 8, ADR-379).

Beside the client, which keeps the reads and sends of received mail. A conversation
is read by its id across the mailbox's folders, the filter LED by the field it sorts
on: Graph refuses a sort beside that filter otherwise (400, measured on a real mailbox
on 2026-11-05), and a filter that does not lead with it crawls (seven conversations in
4.3 s against 0.2 s, measured 2026-11-11). The date bound excludes nothing.

The conversations of a listed page are read in ONE request — Graph's JSON batching,
twenty sub-requests at most: seven conversations in 222 ms against 853 ms one after
the other (measured 2026-11-11).

What a listing does not say travels with each message of a conversation. Graph labels
nothing, so the owner's own messages are those of the Sent folder — and every other copy
of one, a message sent to oneself being held twice under one Message-ID. And Exchange stamps
on a message it answered the verb of the answer (``PidTagLastVerbExecuted``: 102 reply,
103 reply to all, 104 forward) with its instant — observed on a real mailbox right
after a reply sent through Graph (2026-11-11). A reply filed under another subject
leaves the conversation; that mark is then the only evidence left of it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, Protocol
from urllib.parse import quote

import structlog

from src.core.mail_vocabulary import DRAFT_LABEL, SENT_LABEL, labels_of
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.mail_conversation import Conversation, conversation_answer
from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
    GRAPH_ANSWERED_MARK_EXPAND,
    normalize_graph_message,
)
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

#: Leads the filter with the field it sorts on, and excludes nothing.
_ANY_TIME: Final = "receivedDateTime ge 1900-01-01T00:00:00Z"
#: What Graph accepts in one JSON batch.
_BATCH_MAX: Final = 20
#: The sub-request naming the Sent folder, in the first batch.
_SENT_FOLDER_REQUEST: Final = "sent"
#: What a conversation's reader needs of each message, headers alone.
_CONVERSATION_FIELDS: Final = (
    "id,conversationId,internetMessageId,subject,from,toRecipients,ccRecipients,replyTo,"
    "bodyPreview,receivedDateTime,isRead,isDraft,hasAttachments,flag,importance,parentFolderId"
)


class _ConversationHost(Protocol):
    """What the mixin needs from its host: the OAuth client's request seam."""

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        *,
        idempotent: bool | None = None,
    ) -> dict[str, Any]: ...


def _quoted(conversation_id: str) -> str:
    """A conversation id inside an OData string literal."""
    return conversation_id.replace("'", "''")


def _conversation_request(
    request_id: str, conversation_id: str, max_messages: int
) -> dict[str, str]:
    """One sub-request reading a conversation, the newest first, drafts and marks included."""
    query = {
        "$filter": f"{_ANY_TIME} and conversationId eq '{_quoted(conversation_id)}'",
        "$orderby": "receivedDateTime desc",
        "$select": _CONVERSATION_FIELDS,
        "$expand": GRAPH_ANSWERED_MARK_EXPAND,
        # One more than kept says the cut; past the ceiling, the next page does.
        "$top": str(apply_max_items_limit(max_messages + 1)),
    }
    encoded = "&".join(f"{name}={quote(value, safe='')}" for name, value in query.items())
    return {"id": request_id, "method": "GET", "url": f"/me/messages?{encoded}"}


def _row(item: Mapping[str, Any], sent_folder: str) -> dict[str, Any]:
    """One message of a conversation, with what its listing does not say.

    The mailbox's own « answered » mark comes with the normalised message: the
    conversation read expands it.
    """
    row = normalize_graph_message(dict(item))
    row["rfc_message_id"] = item.get("internetMessageId") or None
    if item.get("parentFolderId") == sent_folder and SENT_LABEL not in row["labelIds"]:
        row["labelIds"] = [*row["labelIds"], SENT_LABEL]
    return row


def _own_copies(rows: Sequence[dict[str, Any]]) -> None:
    """Say of every copy of a message the Sent folder holds that its owner sent it.

    A message sent to oneself exists twice under one Message-ID, in the Sent folder and
    where it was received (measured on a real mailbox, 2026-11-11): the received copy
    is no stranger's message.
    """
    sent = {row["rfc_message_id"] for row in rows if SENT_LABEL in labels_of(row)} - {None}
    for row in rows:
        if row["rfc_message_id"] in sent and SENT_LABEL not in labels_of(row):
            row["labelIds"] = [*labels_of(row), SENT_LABEL]


def _conversation(body: Mapping[str, Any], sent_folder: str, max_messages: int) -> Conversation:
    """What one sub-answer holds: what was said, oldest first, the unsent words apart."""
    rows = [_row(item, sent_folder) for item in body.get("value") or []]
    _own_copies(rows)
    said = [row for row in rows if DRAFT_LABEL not in labels_of(row)][::-1]
    unsent = [row for row in rows if DRAFT_LABEL in labels_of(row)]
    # Graph's bound counts every row, the unsent ones too: only a next page says that
    # rows are missing, and the answer itself says when more was said than is kept.
    kept = conversation_answer(said, max_messages, more=bool(body.get("@odata.nextLink")))
    return Conversation(tuple(kept["messages"]), tuple(unsent), bool(kept["truncated"]))


def _answered_body(answer: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """The body of a sub-answer Graph accepted; an empty one for a refusal."""
    if answer is None or answer.get("status") != 200:
        return {}
    body = answer.get("body")
    return body if isinstance(body, Mapping) else {}


class OutlookConversationMixin:
    """Conversations, read by their id."""

    async def get_conversation(
        self: _ConversationHost, message_id: str, max_messages: int
    ) -> dict[str, Any]:
        """The conversation of a message, headers alone (``mail_conversation``).

        Args:
            message_id: Any message of it.
            max_messages: How many are kept, the newest.

        Returns:
            ``{"messages": [...], "truncated": bool}``, oldest first, drafts left out.
        """
        message = path_segment(message_id, connector_type=ConnectorType.MICROSOFT_OUTLOOK)
        anchor = await self._make_request(
            "GET", f"/me/messages/{message}", params={"$select": "conversationId"}
        )
        conversation_id = str(anchor.get("conversationId") or "")
        found = await self._make_request(
            "GET",
            "/me/messages",
            params={
                "$filter": (
                    f"{_ANY_TIME} and conversationId eq '{_quoted(conversation_id)}' "
                    "and isDraft eq false"
                ),
                "$orderby": "receivedDateTime desc",
                "$select": _CONVERSATION_FIELDS,
                # One more than kept says the cut; past the ceiling, the next page does.
                "$top": str(apply_max_items_limit(max_messages + 1)),
            },
        )
        newest_first = [normalize_graph_message(item) for item in found.get("value") or []]
        more = bool(found.get("@odata.nextLink"))
        return conversation_answer(newest_first[::-1], max_messages, more=more)

    async def conversations_of(
        self: _ConversationHost, messages: Sequence[Mapping[str, Any]], max_messages: int
    ) -> dict[str, Conversation]:
        """What the conversations of listed messages hold (``mail_conversation``).

        Args:
            messages: Listed messages; each names its conversation by ``threadId``.
            max_messages: How many messages of a conversation are kept, the newest.

        Returns:
            One :class:`Conversation` per conversation Graph answered for, by its id;
            one it refused is ABSENT. Nothing at all when the Sent folder cannot be
            named: without it the owner's own messages cannot be told from the others,
            and a reply read as a stranger's would be worse than no answer.
        """
        conversation_ids = list(
            dict.fromkeys(str(thread) for item in messages if (thread := item.get("threadId")))
        )
        if not conversation_ids:
            return {}
        requests: list[dict[str, str]] = [
            {
                "id": _SENT_FOLDER_REQUEST,
                "method": "GET",
                "url": "/me/mailFolders/sentitems?$select=id",
            },
            *(
                _conversation_request(str(index), conversation_id, max_messages)
                for index, conversation_id in enumerate(conversation_ids)
            ),
        ]
        answers: dict[str, Mapping[str, Any]] = {}
        for start in range(0, len(requests), _BATCH_MAX):
            # A batch of reads has no effect: it may be sent again after a lost answer.
            response = await self._make_request(
                "POST",
                "/$batch",
                json_data={"requests": requests[start : start + _BATCH_MAX]},
                idempotent=True,
            )
            answers.update({str(item.get("id")): item for item in response.get("responses") or []})
        sent_folder = _answered_body(answers.get(_SENT_FOLDER_REQUEST)).get("id")
        if not sent_folder:
            logger.warning("outlook_conversations_sent_folder_unavailable")
            return {}
        found: dict[str, Conversation] = {}
        for index, conversation_id in enumerate(conversation_ids):
            answer = answers.get(str(index))
            if answer is None or answer.get("status") != 200:
                continue
            found[conversation_id] = _conversation(
                _answered_body(answer), str(sent_folder), max_messages
            )
        if len(found) < len(conversation_ids):
            # Facts only: how many, never which (an id names a conversation of the person's).
            logger.warning(
                "outlook_conversations_partly_unread",
                asked=len(conversation_ids),
                answered=len(found),
            )
        return found


__all__ = ["OutlookConversationMixin"]
