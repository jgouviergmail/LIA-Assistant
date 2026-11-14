"""Where each listed message stands in its conversation — the one door (ADR-379).

A message read alone cannot say whether it was answered: the reply is another message
of the same conversation. Every surface that lists mail for a model or for the person
asks HERE, so they all tell the same fact: one read of the page's conversations by the
mailbox's own client (``conversations_of``), one decider (``conversation_replies``),
one bound and one time budget (``MAIL_REPLY_STATE_*``).

Nothing is cached — a reply sent a second ago must be seen — and nothing here costs a
model call. The door fails OPEN: the switch turned off, a mailbox that cannot be read or
a budget reached leave the page WITHOUT states, which reads « not known », never
« unanswered » (ADR-303). The reason is counted and logged by its facts.

One reader cannot ask that much: a proactive discussion's evidence is versioned and
read again before any use (ADR-358), so what it tells must come WITH the message, the
same at every read, for no call of its own. It is told :func:`answered_mark` — what
the mailbox itself marks of the message, and nothing a conversation read would add.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any, Final, Literal, Protocol

import structlog

from src.core.config import settings
from src.core.field_names import FIELD_MAIL_ANSWERED, FIELD_MAIL_ANSWERED_AT
from src.core.mail_reply_state import REPLY_STATE_KEY, ReplyState, answered_words
from src.core.mail_vocabulary import DRAFT_LABEL, labels_of
from src.core.time_utils import now_in_timezone
from src.domains.connectors.clients.conversation_replies import mailbox_mark, reply_state_of
from src.domains.connectors.clients.mail_conversation import Conversation
from src.infrastructure.observability.metrics_mail_reply_state import (
    mail_reply_state_read_duration_seconds,
    mail_reply_state_reads_total,
    mail_reply_states_total,
)

logger = structlog.get_logger(__name__)

#: What nobody answers, as the mailboxes that label it say it: a message filed as
#: junk, one thrown away, one never sent. No conversation is read for these.
_NEVER_SITUATED: Final = frozenset({"SPAM", "TRASH", DRAFT_LABEL})
#: The state counted for a message nothing could be established of.
_UNKNOWN: Final = "unknown"
#: What a mailbox itself marks of a message: the decider's evidence, never a second
#: telling of the state beside it.
_MAILBOX_MARK: Final = (FIELD_MAIL_ANSWERED, FIELD_MAIL_ANSWERED_AT)

_ReadOutcome = Literal["read", "failed", "timeout"]


class _ConversationReader(Protocol):
    """What the door needs of a mailbox's client."""

    async def conversations_of(
        self, messages: Sequence[Mapping[str, Any]], max_messages: int
    ) -> dict[str, Conversation]: ...


def _provider(client: object) -> str:
    """The mailbox's connector type, as a bounded metric label."""
    value = getattr(getattr(client, "connector_type", None), "value", None)
    return value if isinstance(value, str) else _UNKNOWN


def _situated(messages: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The messages whose conversation is read: the first of the page, up to the bound."""
    asked = [
        message
        for message in messages
        if message.get("id")
        and message.get("threadId")
        and not _NEVER_SITUATED & set(labels_of(message))
    ]
    return asked[: settings.mail_reply_state_max_messages]


def _decided(
    asked: Sequence[Mapping[str, Any]],
    conversations: Mapping[str, Conversation],
    user_timezone: str | None,
) -> dict[str, ReplyState | None]:
    """What each asked message's conversation says of it; None where it says nothing."""
    observed_at = now_in_timezone(user_timezone)
    validity = timedelta(seconds=settings.mail_reply_state_validity_seconds)
    decided: dict[str, ReplyState | None] = {}
    for message in asked:
        conversation = conversations.get(str(message["threadId"]))
        decided[str(message["id"])] = (
            reply_state_of(
                message,
                conversation,
                observed_at=observed_at,
                validity=validity,
                excerpt_max_chars=settings.mail_reply_state_excerpt_max_chars,
            )
            if conversation is not None
            else None
        )
    return decided


async def reply_states_of(
    client: _ConversationReader,
    messages: Sequence[Mapping[str, Any]],
    *,
    user_timezone: str | None,
) -> dict[str, ReplyState]:
    """Where each of ``messages`` stands in its conversation.

    Args:
        client: The mailbox's client.
        messages: Listed messages, in the ``EmailMessage`` vocabulary.
        user_timezone: The ACCOUNT's zone: every instant a state carries is told in
            it. None or unknown falls back to the default display zone.

    Returns:
        The state of each message one could be established for, by message id. A
        message past the bound, one nobody answers (junk, trash, a draft), one whose
        conversation could not be read, and every message when the capability is off
        or the read failed, is ABSENT — « not known », never « unanswered ».
    """
    if not settings.mail_reply_state_enabled:
        return {}
    asked = _situated(messages)
    if not asked:
        return {}
    provider = _provider(client)
    outcome: _ReadOutcome = "read"
    decided: dict[str, ReplyState | None] = {}
    started = time.monotonic()
    try:
        async with asyncio.timeout(settings.mail_reply_state_timeout_seconds):
            conversations = await client.conversations_of(
                asked, settings.mail_reply_state_conversation_max_messages
            )
        decided = _decided(asked, conversations, user_timezone)
    except TimeoutError:
        outcome = "timeout"
    except Exception as error:
        # Fail-open by design (module docstring): the page is worth more than its states.
        outcome = "failed"
        logger.warning(
            "mail_reply_states_read_failed", provider=provider, error_type=type(error).__name__
        )
    elapsed = time.monotonic() - started
    mail_reply_state_read_duration_seconds.labels(provider=provider).observe(elapsed)
    mail_reply_state_reads_total.labels(provider=provider, outcome=outcome).inc()
    if outcome == "timeout":
        logger.warning(
            "mail_reply_states_read_timeout",
            provider=provider,
            asked=len(asked),
            budget_seconds=settings.mail_reply_state_timeout_seconds,
        )
    for state in decided.values():
        status = state.status if state is not None else _UNKNOWN
        mail_reply_states_total.labels(provider=provider, status=status).inc()
    return {key: state for key, state in decided.items() if state is not None}


async def attach_reply_states(
    client: _ConversationReader,
    messages: Sequence[dict[str, Any]],
    *,
    user_timezone: str | None,
) -> None:
    """Write on each of ``messages`` where it stands, under ``REPLY_STATE_KEY``.

    The state travels as plain data (``ReplyState`` dumped as JSON), beside the
    message's other annotations: what reads it goes through
    ``core.annotation_projection``, which decides at SHOW time what is still true.
    The mailbox's own mark, which a read may have left on the message, leaves it here:
    it was the decider's evidence, and a message tells where it stands ONE way —
    switched off, the capability tells nothing by another name.

    Args:
        client: The mailbox's client.
        messages: Listed messages, annotated in place.
        user_timezone: The account's zone (see :func:`reply_states_of`).
    """
    states = await reply_states_of(client, messages, user_timezone=user_timezone)
    for message in messages:
        state = states.get(str(message.get("id") or ""))
        if state is not None:
            message[REPLY_STATE_KEY] = state.model_dump(mode="json")
        for evidence in _MAILBOX_MARK:
            message.pop(evidence, None)


def answered_mark(message: Mapping[str, Any]) -> str:
    """What a message's own mailbox marks of it, in the words a model reads.

    For the reader that tells no more than the message itself carries (module
    docstring): no conversation is read, so an answer that left no mark is not seen.

    Args:
        message: A message as a read carrying the mark returned it — any IMAP read, a
            Graph read asked for it (``get_message(mailbox_mark=True)``); Gmail keeps none.

    Returns:
        ``answered on <UTC instant>`` when the mailbox dates its mark, ``answered`` when
        it does not, and an empty string when it marks nothing — « not known », never
        « unanswered ».
    """
    marked, at = mailbox_mark(message)
    return answered_words(at) if marked else ""


__all__ = ["answered_mark", "attach_reply_states", "reply_states_of"]
