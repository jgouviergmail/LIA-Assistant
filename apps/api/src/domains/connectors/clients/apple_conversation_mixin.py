"""A conversation on iCloud: IMAP keeps none, the headers do (ADR-369 lot 8, ADR-379).

Out of ``apple_email_client.py``, which is close to its size cap. Every message of a
conversation carries the id that names it (``conversation_opening``), so that id is searched
for: in the folder the message was read in first, so it keeps its own id when a copy lives
elsewhere, then in the inbox and the sent folder, where one's own answers are. Every other
folder would be one more round trip for what is rarely kept apart. Headers alone are read,
so a message here has no preview, and the bound holds per folder.

The conversations of a listed page (ADR-379) are read in ONE session: each folder is
searched once per group of conversations, the drafts folder included, and every message
found says what a listing does not — it is the owner's own when the sent folder holds it
(or holds another copy of it), unsent when the drafts folder does, and which message it
answers. IMAP dates a message by its author's clock: that last fact is what makes a reply
later than what it answers. That the mailbox flagged a message as answered comes with
every read of it, a conversation's or not (``normalize_imap_message``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from imap_tools import AND, OR, H, MailBox, MailMessage

from src.core.field_names import FIELD_MAIL_IN_REPLY_TO
from src.core.mail_vocabulary import DRAFT_LABEL, SENT_LABEL, labels_of
from src.domains.connectors.clients.apple_imap import (
    DRAFTS_ROLE,
    SENT_ROLE,
    ImapMessageNotFoundError,
    authenticated_imap_mailbox,
    located_message,
    mailbox_scope,
    select_message_folder,
    special_folder,
)
from src.domains.connectors.clients.mail_conversation import Conversation, conversation_answer
from src.domains.connectors.clients.mailbox_drafts import MailboxFolderUnavailableError
from src.domains.connectors.clients.normalizers.email_normalizer import (
    answered_message_id,
    conversation_opening,
    names_a_conversation,
    normalize_imap_message,
)
from src.domains.connectors.clients.normalizers.imap_handles import (
    INBOX,
    MessageLocation,
    folder_digest,
    read_message_handle,
)
from src.domains.connectors.schemas import AppleCredentials

#: The headers through which a message names its conversation.
_NAMING_HEADERS: Final = ("Message-ID", "References", "In-Reply-To")
#: How many conversations one SEARCH names (three header criteria each).
_CONVERSATIONS_PER_SEARCH: Final = 10


class _ConversationHost(Protocol):
    """What the mixin needs from its host."""

    credentials: AppleCredentials

    async def _execute_with_retry(
        self, operation: str, func: Any, *args: Any, max_retries: int = 3, **kwargs: Any
    ) -> Any: ...

    def _check_imap_auth_error(self, error: Exception) -> None: ...

    async def _conversation_impl(self, message_id: str, max_messages: int) -> dict[str, Any]: ...

    async def _conversations_impl(
        self, messages: Sequence[Mapping[str, Any]], max_messages: int
    ) -> dict[str, Conversation]: ...


@dataclass(frozen=True, slots=True)
class _Place:
    """A folder a conversation is searched in, and what holding a message there means."""

    name: str
    sent: bool = False
    drafts: bool = False


@dataclass(slots=True)
class _Found:
    """What a search found of one conversation: each message once, and whether it was cut."""

    rows: dict[str, dict[str, Any]] = field(default_factory=dict)
    more: bool = False


def _role_folder(mailbox: MailBox, role: str) -> str | None:
    """The folder holding ``role``; a server without one still answers."""
    try:
        return special_folder(mailbox, role)
    except MailboxFolderUnavailableError:
        return None


def _headers(mailbox: MailBox, criteria: Any, limit: int) -> Iterator[MailMessage]:
    """The newest ``limit`` hits of the selected folder, marked read by nothing."""
    return mailbox.fetch(criteria, limit=limit, mark_seen=False, reverse=True, headers_only=True)


def _places(mailbox: MailBox, first: Sequence[str], *, drafts: bool) -> list[_Place]:
    """Where conversations are searched, in order: the folders the messages were read in
    first (each keeps its own id when a copy lives elsewhere), then the inbox, the sent
    folder and, when asked, the drafts folder."""
    sent = _role_folder(mailbox, SENT_ROLE)
    unsent = _role_folder(mailbox, DRAFTS_ROLE) if drafts else None
    names = dict.fromkeys(filter(None, (*first, INBOX, sent, unsent)))
    return [_Place(name, sent=name == sent, drafts=name == unsent) for name in names]


def _labelled(row: dict[str, Any], label: str) -> None:
    """Say ``label`` of a message, once."""
    labels = labels_of(row)
    if label not in labels:
        row["labelIds"] = [*labels, label]


def _marked(row: dict[str, Any], hit: MailMessage, place: _Place) -> dict[str, Any]:
    """A message with what its listing does not say (``mail_conversation``).

    The mailbox's own « answered » flag is not among it: every read states it.
    """
    row["labelIds"] = list(labels_of(row))
    if place.sent:
        _labelled(row, SENT_LABEL)
    if place.drafts:
        _labelled(row, DRAFT_LABEL)
    if answers := answered_message_id(hit.headers):
        row[FIELD_MAIL_IN_REPLY_TO] = answers
    return row


def _named_among(hit: MailMessage, openings: Sequence[str]) -> list[str]:
    """The conversations a message belongs to: those its own headers name.

    A search of one conversation finds its messages alone; one naming several returns
    them mixed, and IMAP matches a header whatever its case.
    """
    if len(openings) == 1:
        return list(openings)
    named = " ".join(
        str(value) for name in _NAMING_HEADERS for value in hit.headers.get(name.lower()) or ()
    ).casefold()
    return [opening for opening in openings if opening.casefold() in named]


def _search(
    mailbox: MailBox,
    openings: Sequence[str],
    places: Sequence[_Place],
    principal: str,
    max_messages: int,
    *,
    marked: bool,
) -> dict[str, _Found]:
    """Every message naming one of ``openings``, folder by folder, each one once.

    The bound holds per folder and per group of conversations: one more than kept per
    conversation says the cut, which is then said of every conversation of the group.
    """
    found = {opening: _Found() for opening in openings}
    for place in places:
        mailbox.folder.set(place.name)
        scope = mailbox_scope(mailbox, place.name, principal)
        for start in range(0, len(openings), _CONVERSATIONS_PER_SEARCH):
            group = openings[start : start + _CONVERSATIONS_PER_SEARCH]
            criteria = OR(
                header=[H(name, opening) for opening in group for name in _NAMING_HEADERS]
            )
            limit = len(group) * (max_messages + 1)
            hits = list(_headers(mailbox, criteria, limit))
            for hit in hits:
                row = normalize_imap_message(hit, place.name, scope=scope)
                if marked:
                    row = _marked(row, hit, place)
                for opening in _named_among(hit, group):
                    kept = found[opening].rows.setdefault(
                        str(row["rfc_message_id"] or row["id"]), row
                    )
                    if marked and place.sent:
                        # Found again in the sent folder: the owner's own, whichever
                        # copy keeps its id (a message sent to oneself is held twice).
                        _labelled(kept, SENT_LABEL)
            if len(hits) >= limit:
                for opening in group:
                    found[opening].more = True
    return found


def _oldest_first(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: int(item["internalDate"] or 0))


def _read_conversation(
    mailbox: MailBox, location: MessageLocation, principal: str, max_messages: int
) -> dict[str, Any]:
    """Read a conversation in the open session; every value is extracted within it."""
    folder = select_message_folder(mailbox, location, principal=principal)
    anchor = None if folder is None else next(_headers(mailbox, AND(uid=location.uid), 1), None)
    if folder is None or anchor is None:
        raise ImapMessageNotFoundError("Message not found")
    opening = conversation_opening(anchor.headers)
    if opening is None:
        alone = normalize_imap_message(anchor, folder, scope=location.scope_digest)
        return conversation_answer([alone], max_messages)
    places = _places(mailbox, [folder], drafts=False)
    found = _search(mailbox, [opening], places, principal, max_messages, marked=False)[opening]
    said = [row for row in found.rows.values() if DRAFT_LABEL not in labels_of(row)]
    return conversation_answer(_oldest_first(said), max_messages, more=found.more)


def _listed_folders(mailbox: MailBox, messages: Sequence[Mapping[str, Any]]) -> list[str]:
    """The folders the listed messages were read in, as their ids name them."""
    digests = {
        location.folder_digest or folder_digest(INBOX)
        for message in messages
        if (location := read_message_handle(str(message.get("id") or ""))) is not None
    }
    return [info.name for info in mailbox.folder.list() if folder_digest(info.name) in digests]


def _read_conversations(
    mailbox: MailBox, messages: Sequence[Mapping[str, Any]], principal: str, max_messages: int
) -> dict[str, Conversation]:
    """Read the conversations of listed messages in the open session."""
    conversations: dict[str, Conversation] = {}
    openings: list[str] = []
    for message in messages:
        thread = str(message.get("threadId") or "")
        if not thread or thread in conversations or thread in openings:
            continue
        if names_a_conversation(thread):
            openings.append(thread)
        else:
            # A message naming nothing is a conversation of one: itself.
            conversations[thread] = Conversation(messages=(dict(message),))
    if not openings:
        return conversations
    places = _places(mailbox, _listed_folders(mailbox, messages), drafts=True)
    searched = _search(mailbox, openings, places, principal, max_messages, marked=True)
    for opening, found in searched.items():
        rows = list(found.rows.values())
        said = _oldest_first([row for row in rows if DRAFT_LABEL not in labels_of(row)])
        kept = conversation_answer(said, max_messages, more=found.more)
        conversations[opening] = Conversation(
            messages=tuple(kept["messages"]),
            drafts=tuple(row for row in rows if DRAFT_LABEL in labels_of(row)),
            truncated=bool(kept["truncated"]),
        )
    return conversations


class AppleConversationMixin:
    """A conversation, walked back from its headers."""

    async def get_conversation(
        self: _ConversationHost, message_id: str, max_messages: int
    ) -> dict[str, Any]:
        """The conversation of a message, headers alone (``mail_conversation``).

        Args:
            message_id: Any message of it.
            max_messages: How many are kept, the newest.

        Returns:
            ``{"messages": [...], "truncated": bool}``, oldest first, drafts left out.

        Raises:
            ImapMessageNotFoundError: The id names no message of this mailbox.
        """
        return await self._execute_with_retry(
            "get_conversation", self._conversation_impl, message_id, max_messages
        )

    async def conversations_of(
        self: _ConversationHost, messages: Sequence[Mapping[str, Any]], max_messages: int
    ) -> dict[str, Conversation]:
        """What the conversations of listed messages hold (``mail_conversation``).

        Args:
            messages: Listed messages; each names its conversation by ``threadId``.
            max_messages: How many messages of a conversation are kept, the newest.

        Returns:
            One :class:`Conversation` per conversation, by the id that names it; a
            message naming none is a conversation of one. No session is opened for
            an empty page.
        """
        if not messages:
            return {}
        return await self._execute_with_retry(
            "conversations_of", self._conversations_impl, list(messages), max_messages
        )

    async def _conversation_impl(
        self: _ConversationHost, message_id: str, max_messages: int
    ) -> dict[str, Any]:
        location = located_message(message_id)
        principal = self.credentials.apple_id

        def _read() -> dict[str, Any]:
            try:
                with authenticated_imap_mailbox(
                    MailBox, principal, self.credentials.app_password
                ) as mailbox:
                    return _read_conversation(mailbox, location, principal, max_messages)
            except ValueError:
                raise
            except Exception as error:
                self._check_imap_auth_error(error)
                raise

        return await asyncio.to_thread(_read)

    async def _conversations_impl(
        self: _ConversationHost, messages: Sequence[Mapping[str, Any]], max_messages: int
    ) -> dict[str, Conversation]:
        principal = self.credentials.apple_id

        def _read() -> dict[str, Conversation]:
            try:
                with authenticated_imap_mailbox(
                    MailBox, principal, self.credentials.app_password
                ) as mailbox:
                    return _read_conversations(mailbox, messages, principal, max_messages)
            except ValueError:
                raise
            except Exception as error:
                self._check_imap_auth_error(error)
                raise

        return await asyncio.to_thread(_read)
