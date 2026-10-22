"""Old wording reaches a model only with its complete freshly permitted support set.

An opening an SMS informed never comes back at all (ADR-357): its support set may
be SMS-free while its words are not.
"""

from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.conversations.models import ConversationMessage
from src.domains.proactive_discussions.context_store.schemas import ContextEvidenceLink
from src.domains.proactive_discussions.models import DiscussionOpeningRecord
from src.domains.proactive_discussions.privacy import DISCUSSION_SMS_CONTEXT_FIELD
from src.domains.proactive_discussions.schemas import PriorOpening
from src.domains.shared.discussion_sources import DiscussionEvidence

_PROOFS = TypeAdapter(tuple[ContextEvidenceLink, ...])


async def relevant_opening_history(
    db: AsyncSession, owner: UUID, evidence: tuple[DiscussionEvidence, ...]
) -> tuple[PriorOpening, ...]:
    """Return the recent openings whose whole support is among the evidence read now.

    An opening comes back only when every proof it rests on is present at the
    same version and from the same source account, so old wording never reaches
    a model on a support that changed or was withdrawn; an opening an SMS
    informed never comes back at all (ADR-357).

    Args:
        db: The session to read with.
        owner: The account.
        evidence: The evidence this run may read, at its current versions.

    Returns:
        Up to ``DISCUSSION_HISTORY_OPENINGS`` prior openings, newest first, with their
        state and feedback.
    """
    known = {item.reference: item for item in evidence}
    candidates = (
        await db.execute(
            select(
                DiscussionOpeningRecord.message_id,
                DiscussionOpeningRecord.state,
                DiscussionOpeningRecord.created_at,
                ConversationMessage.message_metadata,
            )
            .join(ConversationMessage, ConversationMessage.id == DiscussionOpeningRecord.message_id)
            .where(
                DiscussionOpeningRecord.user_id == owner,
                ConversationMessage.conversation_id == DiscussionOpeningRecord.conversation_id,
                ConversationMessage.hidden.is_(False),
                ConversationMessage.role == "assistant",
                # ADR-357: an SMS-informed opening never reaches a later decision window.
                func.coalesce(
                    ConversationMessage.message_metadata[DISCUSSION_SMS_CONTEXT_FIELD].as_boolean(),
                    False,
                ).is_(False),
            )
            .order_by(DiscussionOpeningRecord.created_at.desc(), DiscussionOpeningRecord.id.desc())
            .limit(settings.discussion_history_openings)
        )
    ).all()
    selected = []
    for identifier, state, created, metadata in candidates:
        proofs = _PROOFS.validate_python((metadata or {}).get("discussion_proofs", ()))
        if proofs and all(
            proof.reference in known
            and proof.version == known[proof.reference].version
            and proof.source_account == known[proof.reference].source_account
            for proof in proofs
        ):
            selected.append(
                (identifier, state, created, (metadata or {}).get("discussion_feedback"))
            )
    messages = dict(
        (
            await db.execute(
                select(ConversationMessage.id, ConversationMessage.content).where(
                    ConversationMessage.id.in_([row[0] for row in selected]),
                    ConversationMessage.hidden.is_(False),
                )
            )
        )
        .tuples()
        .all()
    )
    return tuple(
        PriorOpening(
            created_at=created, content=messages[identifier], state=state, feedback=feedback
        )
        for identifier, state, created, feedback in selected
        if identifier in messages
    )
