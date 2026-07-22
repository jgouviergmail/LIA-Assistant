"""Response feedback on ordinary assistant messages (QW-5, ADR-138).

Ordinary responses only had a Copy button while proactive interest
notifications had the full 👍/👎 loop. This module closes that gap:

- the verdict (and the optional 👎 comment) is persisted on the message row
  via a server-side atomic ``jsonb_set`` UPDATE scoped by owner — the exact
  ``mark_interest_feedback_submitted`` pattern (never an in-place mutation);
- on the FIRST verdict only, the evidence/contradiction counters of the
  journal entries injected into that turn are incremented
  (``FIELD_INJECTED_JOURNAL_IDS``, IDs archived with the message). Counters
  are system-managed increments with no decrement path, so a verdict CHANGE
  updates the stored verdict but never re-feeds the counters;
- a 👎 comment additionally lands as an L0 ``user_correction`` journal entry
  (same shape as the portrait-feedback lever) WITHOUT triggering a
  consolidation — arbitration 2026-07-21: no LLM cost per thumb.

The journal side-effects go through an injected port
(:class:`JournalFeedbackHooks`): the journals domain already depends on
conversations, so importing it from here — even lazily — would close a
domain cycle (F009 ratchet). The implementation lives in
``journals/feedback_hooks.py`` and is registered at startup
(``infrastructure/startup/registries.init_response_feedback_hooks``), the
layer allowed to see both domains.

Sovereignty: no automatic regeneration ever happens here — the user decides.
Lives in its own module: ``conversations/repository.py`` is one file-size
ratchet away from its frozen cap.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol
from uuid import UUID

from sqlalchemy import cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB, array
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import RESPONSE_FEEDBACK_JOURNAL_IDS_MAX
from src.core.field_names import FIELD_INJECTED_JOURNAL_IDS, FIELD_RESPONSE_FEEDBACK
from src.domains.conversations.models import Conversation, ConversationMessage
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

ResponseFeedbackVerdict = Literal["thumbs_up", "thumbs_down"]

#: Verdict → journal evidence outcome (system-managed counters, ADR-135 taxonomy).
_VERDICT_TO_OUTCOME: dict[str, str] = {
    "thumbs_up": "evidence",
    "thumbs_down": "contradiction",
}


class JournalFeedbackHooks(Protocol):
    """Port for the journal side-effects of a response verdict.

    Implemented by ``journals/feedback_hooks.py`` and injected at startup —
    conversations must not import journals (domain-cycle ratchet).
    """

    async def apply_verdict(
        self, db: AsyncSession, user_id: UUID, entry_ids: list[str], outcome: str
    ) -> int:
        """Increment the outcome counter on the user's entries; return count."""
        ...

    async def record_correction(self, db: AsyncSession, user_id: UUID, comment: str) -> None:
        """Land a correction comment as an L0 ``user_correction`` entry."""
        ...


_journal_hooks: JournalFeedbackHooks | None = None


def register_journal_feedback_hooks(hooks: JournalFeedbackHooks) -> None:
    """Register the journals implementation (called once at startup)."""
    global _journal_hooks
    _journal_hooks = hooks
    logger.info("response_feedback_journal_hooks_registered")


async def get_assistant_message_for_user(
    db: AsyncSession, user_id: UUID, message_id: UUID
) -> ConversationMessage | None:
    """Fetch an assistant message owned by ``user_id``, or None.

    Ownership is enforced through the conversation join — a foreign
    ``message_id`` resolves to None (the router raises 404, hiding existence).
    """
    stmt = (
        select(ConversationMessage)
        .where(
            ConversationMessage.id == message_id,
            ConversationMessage.role == "assistant",
            ConversationMessage.conversation_id.in_(
                select(Conversation.id).where(Conversation.user_id == user_id)
            ),
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def persist_verdict(
    db: AsyncSession,
    user_id: UUID,
    message_id: UUID,
    verdict: ResponseFeedbackVerdict,
    comment: str | None,
) -> int:
    """Persist the verdict on the message metadata (atomic, owner-scoped).

    Returns:
        Number of rows updated (0 when the message vanished concurrently).
    """
    payload: dict[str, Any] = {"verdict": verdict}
    if comment:
        payload["comment"] = comment

    conv_ids_subq = select(Conversation.id).where(Conversation.user_id == user_id)
    stmt = (
        update(ConversationMessage)
        .where(
            ConversationMessage.id == message_id,
            ConversationMessage.conversation_id.in_(conv_ids_subq),
        )
        .values(
            message_metadata=func.jsonb_set(
                func.coalesce(ConversationMessage.message_metadata, cast("{}", JSONB)),
                array([FIELD_RESPONSE_FEEDBACK]),
                cast(payload, JSONB),
            )
        )
    )
    result = await db.execute(stmt)
    return int(getattr(result, "rowcount", 0) or 0)


def _journals_ready() -> bool:
    """True when journal coupling is enabled AND the hooks are registered."""
    if not getattr(settings, "journals_enabled", False):
        return False
    if _journal_hooks is None:
        # Journals enabled but nothing registered: the coupling silently dying
        # is how features disappear — make the miswiring visible.
        logger.warning("response_feedback_journal_hooks_missing")
        return False
    return True


async def apply_verdict_to_journals(
    db: AsyncSession,
    user_id: UUID,
    metadata: dict[str, Any] | None,
    verdict: ResponseFeedbackVerdict,
) -> int:
    """Feed the injected entries' evidence/contradiction counters (first verdict).

    Args:
        db: Session shared with the endpoint transaction.
        user_id: Owner — entries are updated user-scoped, foreign IDs skipped.
        metadata: The message's metadata (source of the injected IDs).
        verdict: Maps to ``evidence`` (👍) or ``contradiction`` (👎).

    Returns:
        Number of entries actually updated.
    """
    raw_ids = (metadata or {}).get(FIELD_INJECTED_JOURNAL_IDS)
    if not isinstance(raw_ids, list) or not raw_ids or not _journals_ready():
        return 0
    assert _journal_hooks is not None  # narrowed by _journals_ready

    entry_ids = [str(rid) for rid in raw_ids[:RESPONSE_FEEDBACK_JOURNAL_IDS_MAX]]
    updated = await _journal_hooks.apply_verdict(
        db, user_id, entry_ids, _VERDICT_TO_OUTCOME[verdict]
    )
    if updated:
        logger.info(
            "response_feedback_journal_counters_updated",
            user_id=str(user_id),
            verdict=verdict,
            entries_updated=updated,
        )
    return updated


async def record_comment_as_correction(db: AsyncSession, user_id: UUID, comment: str) -> None:
    """Land a 👎 comment as an L0 ``user_correction`` entry (no consolidation).

    Same shape as the portrait-feedback lever so the next consolidation picks
    it up in priority — but WITHOUT the synchronous recompilation (no LLM cost
    per thumb, arbitration 2026-07-21). No-op when journals are disabled.
    """
    if not _journals_ready():
        return
    assert _journal_hooks is not None  # narrowed by _journals_ready
    await _journal_hooks.record_correction(db, user_id, comment)
