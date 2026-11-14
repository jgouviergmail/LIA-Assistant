"""A committed change to a person's conversation is SAID to their open tabs (ADR-320).

A person's chat may be open in several places while messages land from
elsewhere: a Telegram turn, a voice-session relay, a routine, a reminder, a
proactive notification, the same account in another browser. Most of those
paths published nothing, so an open tab only learned about the message when it
was reloaded by hand. Every one of them archives through ONE door,
``ConversationService.archive_message``, so that door arms a signal here — and
a reset arms its own.

**The signal leaves only once the transaction that wrote the row has
COMMITTED.** ``archive_message`` does not commit (its callers batch), and a tab
told « something changed » before the row is visible would read the old page
and conclude nothing had. A rollback drops what was armed. Over-signalling is
harmless (the tab reads a page that did not change); signalling early is the
failure this module exists to prevent.

The signal carries no content — the kind of change and the conversation — and
the tab reads its own history through the authenticated route. It is
best-effort: a tab that misses it catches up when it returns to the foreground
or reconnects, and every outcome is counted
(``conversation_sync_signals_total``).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Final, Literal

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

from src.domains.conversations.models import Conversation, ConversationMessage
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.cache.user_channel import publish_to_user
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_conversation_sync import (
    conversation_sync_signals_total,
)

logger = get_logger(__name__)

__all__ = [
    "CONVERSATION_RESET",
    "CONVERSATION_METADATA",
    "CONVERSATION_UPDATED",
    "SyncKind",
    "arm_after_archive",
    "arm_conversation_signal",
]

#: A message joined (or changed in) the conversation: read the newest page.
CONVERSATION_UPDATED: Final = "conversation_updated"
#: The conversation was emptied: the open tabs empty theirs.
CONVERSATION_RESET: Final = "conversation_reset"

#: Only the catalogue metadata changed. No history or checkpoint was touched.
CONVERSATION_METADATA: Final = "conversation_metadata"

SyncKind = Literal["conversation_updated", "conversation_reset", "conversation_metadata"]
_PRIORITY: dict[SyncKind, int] = {
    CONVERSATION_METADATA: 0,
    CONVERSATION_UPDATED: 1,
    CONVERSATION_RESET: 2,
}

#: ``Session.info`` keys — per session, so two requests never share a pending set.
_PENDING: Final = "lia_conversation_sync_pending"
_LISTENING: Final = "lia_conversation_sync_listening"

type SignalBatch = dict[tuple[uuid.UUID, uuid.UUID], SyncKind]
type TransactionBatches = dict[SessionTransaction | None, SignalBatch]


def _merge_signals(destination: SignalBatch, source: SignalBatch) -> None:
    """Coalesce a committed child without weakening its parent's reset."""
    for key, kind in source.items():
        if key not in destination or _PRIORITY[kind] > _PRIORITY[destination[key]]:
            destination[key] = kind


def arm_conversation_signal(
    db: AsyncSession, *, user_id: uuid.UUID, conversation_id: uuid.UUID, kind: SyncKind
) -> None:
    """Announce a change to the person's tabs once ``db``'s transaction commits.

    Several changes in one transaction make one signal per account/discussion
    pair. A reset wins over an update for that discussion alone.

    Args:
        db: The session whose transaction wrote the change.
        user_id: The account whose tabs are told.
        conversation_id: The conversation that changed.
        kind: What changed.
    """
    session = db.sync_session
    batches: TransactionBatches = session.info.setdefault(_PENDING, {})
    transaction = session.get_nested_transaction() or session.get_transaction()
    pending = batches.setdefault(transaction, {})
    key = (user_id, conversation_id)
    _merge_signals(pending, {key: kind})
    if not session.info.get(_LISTENING):
        session.info[_LISTENING] = True
        event.listen(session, "after_commit", _after_commit)
        event.listen(session, "after_rollback", _after_rollback)


async def arm_after_archive(db: AsyncSession, message: ConversationMessage) -> None:
    """Arm the update signal for a freshly archived message.

    A hidden row (the synthetic question of an out-of-turn run, ADR-276) is
    shown by no tab, so it announces nothing.

    Args:
        db: The session that wrote the message.
        message: The archived row.
    """
    if message.hidden:
        return
    # From the identity map when the caller already holds the conversation.
    conversation = await db.get(Conversation, message.conversation_id)
    if conversation is None:
        return
    arm_conversation_signal(
        db,
        user_id=conversation.user_id,
        conversation_id=conversation.id,
        kind=CONVERSATION_UPDATED,
    )


def _after_commit(session: Session) -> None:
    batches: TransactionBatches | None = session.info.get(_PENDING)
    if not batches:
        return
    nested = session.get_nested_transaction()
    if nested is not None:
        _merge_signals(batches.setdefault(nested.parent, {}), batches.pop(nested, {}))
        return
    session.info.pop(_PENDING, None)
    pending: SignalBatch = {}
    for batch in batches.values():
        _merge_signals(pending, batch)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop: a synchronous caller (a script). Checked BEFORE any
        # coroutine exists — one created and never awaited is a warning, and
        # the tabs catch up at their next foreground return anyway.
        for kind in pending.values():
            conversation_sync_signals_total.labels(kind=kind, outcome="no_loop").inc()
        return
    for (user_id, conversation_id), kind in pending.items():
        safe_fire_and_forget(
            _publish(user_id, conversation_id, kind),
            name="conversation_sync_signal",
            # Publication announces a committed fact even when the producing
            # graph was revoked while its final partial was being archived.
            independent_of_graph=True,
        )


def _after_rollback(session: Session) -> None:
    nested = session.get_nested_transaction()
    if nested is not None:
        batches: TransactionBatches = session.info.get(_PENDING, {})
        batches.pop(nested, None)
        return
    session.info.pop(_PENDING, None)


async def _publish(user_id: uuid.UUID, conversation_id: uuid.UUID, kind: SyncKind) -> None:
    try:
        sent = await publish_to_user(
            user_id, {"type": kind, "conversation_id": str(conversation_id)}
        )
    except Exception as exc:
        logger.warning(
            "conversation_sync_signal_failed",
            user_id=str(user_id),
            kind=kind,
            error_type=type(exc).__name__,
        )
        conversation_sync_signals_total.labels(kind=kind, outcome="failed").inc()
        return
    outcome = "published" if sent else "no_redis"
    conversation_sync_signals_total.labels(kind=kind, outcome=outcome).inc()
