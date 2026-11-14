"""What a conversation says of one message's reply state — one rule for three mailboxes (ADR-379).

A received message is ANSWERED when the mailbox's owner sent, later and in the same
conversation, a message addressed to its sender (or to the address it asked replies
at) — or when the mailbox itself marks it answered. A forward to someone else is no
answer. A message the owner SENT got a reply when someone else wrote after it.

Pure: every client hands the same :class:`Conversation` (its own notion of one — a
Gmail thread, a Graph ``conversationId``, IMAP's headers), in the ``EmailMessage``
vocabulary, the owner's messages labelled ``SENT`` and their unsent ones ``DRAFT``.
What the conversation read knows of the message itself wins over its listing, which
may carry less. Whatever cannot be established is not claimed: a message with no
date, a conversation cut before it, or a message addressed to nobody but its own
sender (a note to oneself) has no state.

Recipients are compared on their PARSED address (``infrastructure/email/recipients``),
never on header text, as the replies themselves are addressed (``email_compose``).
What a state carries of the settling message is its writer's own words: a provider's
preview runs a short reply into the history it quotes (``reply_trimming``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from src.core.field_names import (
    FIELD_MAIL_ANSWERED,
    FIELD_MAIL_ANSWERED_AT,
    FIELD_MAIL_IN_REPLY_TO,
)
from src.core.mail_reply_state import ReplyMessage, ReplyState, ReplyStatus
from src.core.mail_vocabulary import DRAFT_LABEL, SENT_LABEL, instant_of, labels_of
from src.core.text_clip import clip_on_word
from src.domains.connectors.clients.mail_conversation import Conversation
from src.domains.connectors.clients.normalizers.reply_trimming import preview_own_words
from src.infrastructure.email.recipients import read_recipients

#: How many correspondents a state names before it counts the others.
_NAMED_CORRESPONDENTS_MAX: Final = 3
#: The longest line of names a state carries: a display name is a stranger's text.
_CORRESPONDENTS_MAX_CHARS: Final = 80
#: Sorts an undated message before every dated one.
_UNDATED: Final = datetime.min.replace(tzinfo=UTC)

_Row = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class _Finding:
    """What the conversation established, before it is dated in the account's zone.

    Attributes:
        status: The reply state.
        settled_by: The message that settles it, when one does.
        named_in: The header of that message naming who it concerns.
        marked_at: When the mailbox marked the message answered, when it dates it.
    """

    status: ReplyStatus
    settled_by: _Row | None = None
    named_in: str = "to"
    marked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class _Around:
    """What the conversation holds around one message.

    Attributes:
        later: The messages said after it, each one a reader can open and date.
        whole_since: Nothing said after it is missing from the read.
        size: The messages said in the conversation; None when the read was cut.
    """

    later: list[_Row]
    whole_since: bool
    size: int | None


def _text(row: _Row, field: str) -> str:
    value = row.get(field)
    return value if isinstance(value, str) else ""


def _when(row: _Row) -> datetime | None:
    return instant_of(row.get("internalDate"))


def _addresses(*headers: str) -> set[str]:
    """Every readable address the headers name, compared whatever their case."""
    return {address.casefold() for header in headers for _, address in read_recipients(header)}


def _named(header: str) -> str:
    """Who a header names, for a reader: a few display names, the others counted."""
    names = [name or address for name, address in read_recipients(header)]
    shown = ", ".join(names[:_NAMED_CORRESPONDENTS_MAX])
    extra = len(names) - _NAMED_CORRESPONDENTS_MAX
    return clip_on_word(f"{shown} +{extra}" if extra > 0 else shown, _CORRESPONDENTS_MAX_CHARS)


def _key(row: _Row) -> str:
    """What names a message whichever copy of it is read: its Message-ID, else its id."""
    return _text(row, "rfc_message_id") or _text(row, "id")


def _same_message(row: _Row, message: _Row) -> bool:
    """Whether ``row`` is ``message`` itself, or the mailbox's other copy of it."""
    if _text(row, "id") == _text(message, "id"):
        return True
    named = _text(message, "rfc_message_id")
    return bool(named) and _text(row, "rfc_message_id") == named


def _is_after(row: _Row, message: _Row, arrived: datetime) -> bool:
    """Whether ``row`` came after ``message``: by its date, or because it says it answers it.

    IMAP dates a message by its author's clock, so a quick reply from a slow clock may
    read earlier than what it answers: a message naming the one it replies to is later.
    By its date alone « later » is strict: Graph and IMAP date to the second, and a
    message of the same instant crossed the other one — it answers nothing.
    """
    answers = _text(row, FIELD_MAIL_IN_REPLY_TO)
    if answers and answers == _text(message, "rfc_message_id"):
        return True
    at = _when(row)
    return at is not None and at > arrived


def _settles_after(row: _Row, message: _Row, arrived: datetime) -> bool:
    """Whether ``row`` can settle the state of ``message``: openable, dated, and later."""
    usable = bool(_text(row, "id")) and _when(row) is not None
    return usable and _is_after(row, message, arrived)


def _latest(rows: Iterable[_Row]) -> _Row | None:
    """The newest of ``rows``, or None when there is none."""
    return max(rows, key=lambda row: _when(row) or _UNDATED, default=None)


def _reaches(row: _Row, addresses: set[str]) -> bool:
    """Whether ``row`` is addressed to one of ``addresses``."""
    return bool(addresses & _addresses(_text(row, "to"), _text(row, "cc")))


def _around(message: _Row, conversation: Conversation, arrived: datetime) -> _Around:
    """What was said around ``message``, the owner's unsent words left out.

    Unsent words are never part of what was said, wherever a client filed them; the
    mailbox's other copy of the message (a sent copy beside the received one) is the
    message itself. The newest messages are the ones a cut read keeps, so nothing
    after a message the read HOLDS is missing.
    """
    said = [row for row in conversation.messages if DRAFT_LABEL not in labels_of(row)]
    others = [row for row in said if not _same_message(row, message)]
    holds = len(others) < len(said)
    return _Around(
        later=[row for row in others if _settles_after(row, message, arrived)],
        whole_since=holds or not conversation.truncated,
        size=None if conversation.truncated else len({_key(row) for row in others}) + 1,
    )


def _own_reply(later: list[_Row], asked_from: set[str]) -> _Row | None:
    """The owner's newest later message addressed to who asked."""
    return _latest(
        row for row in later if SENT_LABEL in labels_of(row) and _reaches(row, asked_from)
    )


def _own_copy(message: _Row, conversation: Conversation) -> _Row | None:
    """The conversation's own copy of ``message``: what its mailbox read of it there.

    A listing may carry less than the conversation read — no Message-ID, no mark, no
    word that the owner sent it (Graph, measured 2026-11-11) or never sent it (IMAP
    labels nothing): that copy is the one read, the unsent ones included.
    """
    own_id = _text(message, "id")
    held = (*conversation.messages, *conversation.drafts)
    return next((row for row in held if _text(row, "id") == own_id), None)


def _to_its_sender_alone(message: _Row) -> bool:
    """Whether ``message`` is addressed to nobody but its own sender: a note to oneself,
    which awaits nobody and that nobody answers."""
    recipients = _addresses(_text(message, "to"), _text(message, "cc"))
    return bool(recipients) and recipients <= _addresses(_text(message, "from"))


def _unsent_answer(
    message: _Row, conversation: Conversation, arrived: datetime, asked_from: set[str]
) -> _Row | None:
    """The owner's newest unsent message addressed to who asked, saved after the message."""
    return _latest(
        row
        for row in conversation.drafts
        if _settles_after(row, message, arrived) and _reaches(row, asked_from)
    )


def mailbox_mark(message: _Row) -> tuple[bool, datetime | None]:
    """What a mailbox itself marks of a message it holds.

    Args:
        message: The message, as a read that carries the mark returned it.

    Returns:
        Whether the mailbox marks it answered, and when if it dates its mark (Graph
        does, IMAP's flag does not).
    """
    if message.get(FIELD_MAIL_ANSWERED) is not True:
        return False, None
    return True, instant_of(message.get(FIELD_MAIL_ANSWERED_AT))


def _received(
    message: _Row, conversation: Conversation, around: _Around, arrived: datetime
) -> _Finding | None:
    """Where a message the owner RECEIVED stands."""
    asked_from = _addresses(_text(message, "reply_to"), _text(message, "from"))
    if (reply := _own_reply(around.later, asked_from)) is not None:
        return _Finding("answered", reply)
    # What the mailbox itself says is the only evidence left of a reply filed outside
    # the conversation (another subject).
    marked, marked_at = mailbox_mark(message)
    if marked:
        return _Finding("answered", marked_at=marked_at)
    if (draft := _unsent_answer(message, conversation, arrived, asked_from)) is not None:
        return _Finding("answer_drafted", draft)
    return _Finding("unanswered") if around.whole_since else None


def _sent(around: _Around) -> _Finding | None:
    """Where a message the owner SENT stands."""
    answer = _latest(row for row in around.later if SENT_LABEL not in labels_of(row))
    if answer is not None:
        return _Finding("reply_received", answer, named_in="from")
    return _Finding("awaiting_reply") if around.whole_since else None


def _settling(
    finding: _Finding, observed_at: datetime, excerpt_max_chars: int
) -> ReplyMessage | None:
    """The message a finding names, dated in the account's zone and bounded."""
    row = finding.settled_by
    at = _when(row) if row is not None else None
    if row is None or at is None:
        return None
    return ReplyMessage(
        message_id=_text(row, "id"),
        at=at.astimezone(observed_at.tzinfo),
        correspondents=_named(_text(row, finding.named_in)),
        # A preview runs a short reply into the history it quotes: the writer's words alone.
        excerpt=clip_on_word(preview_own_words(_text(row, "snippet")), excerpt_max_chars),
    )


def reply_state_of(
    message: _Row,
    conversation: Conversation,
    *,
    observed_at: datetime,
    validity: timedelta,
    excerpt_max_chars: int,
) -> ReplyState | None:
    """Where ``message`` stands in ``conversation``, or None when nothing can be said.

    Args:
        message: The message, in the ``EmailMessage`` vocabulary.
        conversation: What its conversation holds, as its mailbox's client read it.
        observed_at: The instant of the reading, aware, in the ACCOUNT's zone: every
            instant the state carries is told in that zone.
        validity: How long a reading of a moment (« no reply yet ») may be repeated.
        excerpt_max_chars: The longest excerpt of the settling message, cut on a word.

    Returns:
        The state; None for a message with no date, a draft, a message addressed to
        nobody but its own sender, or a « nothing found » that a cut conversation
        cannot vouch for.

    Raises:
        pydantic.ValidationError: ``observed_at`` is not timezone-aware, or
            ``validity`` is not positive — a caller's error, never a mailbox's.
    """
    subject = _own_copy(message, conversation) or message
    arrived = _when(subject)
    labels = labels_of(subject)
    if arrived is None or DRAFT_LABEL in labels or _to_its_sender_alone(subject):
        return None
    around = _around(subject, conversation, arrived)
    if SENT_LABEL in labels:
        finding = _sent(around)
    else:
        finding = _received(subject, conversation, around, arrived)
    if finding is None:
        return None
    marked = finding.marked_at
    return ReplyState(
        status=finding.status,
        message=_settling(finding, observed_at, excerpt_max_chars),
        marked_at=marked.astimezone(observed_at.tzinfo) if marked is not None else None,
        conversation_size=around.size,
        observed_at=observed_at,
        valid_until=observed_at + validity,
    )


__all__ = ["mailbox_mark", "reply_state_of"]
