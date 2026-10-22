"""Owner-scoped opening history and explicit reversible conversational feedback."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, TypeAdapter
from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.core.field_names import FIELD_DISCUSSION_PAUSE_HOURS
from src.domains.conversations.models import ConversationMessage
from src.domains.proactive_discussions.context_store.admission import reference_key
from src.domains.proactive_discussions.context_store.models import (
    ContextItemRecord,
    ContextObservationRecord,
)
from src.domains.proactive_discussions.context_store.repository import ContextRepository
from src.domains.proactive_discussions.context_store.schemas import ContextEvidenceLink
from src.domains.proactive_discussions.models import DiscussionOpeningRecord
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.proactive_discussions.schemas import DiscussionFeedback
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch
from src.domains.shared.discussion_sources import DiscussionValue, SourceKey
from src.domains.shared.discussion_sql import native_discussion_page


class OpeningEvidence(DiscussionValue):
    """One source an opening rested on, as recorded when it was published."""

    source: SourceKey = Field(description="The source the evidence came from.")
    observed_at: AwareDatetime = Field(description="When LIA read it.")
    occurred_at: AwareDatetime | None = Field(
        default=None, description="When the fact itself happened, when known."
    )
    assertion: Literal["planned", "reported", "observed", "inferred", "unknown"] = Field(
        description="How the source stated the fact."
    )


class OpeningView(DiscussionValue):
    """One opening as the person sees it; details add its reason and its evidence."""

    id: UUID = Field(description="The opening.")
    message_id: UUID = Field(description="Its archived message in the conversation.")
    created_at: AwareDatetime = Field(description="When it was published.")
    content: str = Field(description="Its words, as archived.")
    state: Literal["pending", "engaged", "dismissed", "expired"] = Field(
        description="Open until answered, set aside or lapsed."
    )
    feedback: DiscussionFeedback | None = Field(
        default=None, description="The person's reaction, if any."
    )
    reason: Annotated[
        str | None, Field(max_length=400, description="Why LIA opened it (details only).")
    ] = None
    evidence: tuple[OpeningEvidence, ...] = Field(
        default=(), description="The sources it rested on (details only)."
    )


class OpeningPage(DiscussionValue):
    """One page of openings with the exact total of the same filter (ADR-185)."""

    items: tuple[OpeningView, ...] = Field(description="The page, newest first.")
    total: int = Field(description="Every visible opening, not only this page.")
    next_cursor: UUID | None = Field(
        default=None, description="The after_id of the next page, if there is one."
    )


class FeedbackRequest(DiscussionValue):
    """The person's reaction to an opening, against the reaction they last saw."""

    feedback: DiscussionFeedback = Field(description="The reaction.")
    expected_feedback: DiscussionFeedback | None = Field(
        default=None, description="The reaction the person last saw, or none."
    )


# MODEL-FACING (discussions.list tool): the page size and the cursor. A docstring or
# a field description would become schema text the planner reads.
class OpeningPageRequest(DiscussionValue):
    limit: Annotated[int, Field(ge=1, le=50)] = 30
    after_id: UUID | None = None


def opening_view(row: DiscussionOpeningRecord, message: ConversationMessage) -> OpeningView:
    """Project an opening and its message into the person's view, without details.

    Args:
        row: The opening record.
        message: Its archived message.

    Returns:
        The opening's view.
    """
    return OpeningView.model_validate(
        {
            "id": row.id,
            "message_id": message.id,
            "created_at": row.created_at,
            "content": message.content,
            "state": row.state,
            "feedback": (message.message_metadata or {}).get("discussion_feedback"),
        }
    )


async def _owned_opening(
    db: AsyncSession, owner: UUID, opening_id: UUID
) -> tuple[DiscussionOpeningRecord, ConversationMessage]:
    row = (
        await db.execute(
            select(DiscussionOpeningRecord, ConversationMessage)
            .join(
                ConversationMessage,
                ConversationMessage.id == DiscussionOpeningRecord.message_id,
            )
            .where(
                DiscussionOpeningRecord.user_id == owner,
                DiscussionOpeningRecord.id == opening_id,
                ConversationMessage.conversation_id == DiscussionOpeningRecord.conversation_id,
                ConversationMessage.role == "assistant",
                ConversationMessage.hidden.is_(False),
            )
        )
    ).one_or_none()
    if row is None:
        raise ResourceNotFoundError("discussion")
    return row[0], row[1]


async def get_opening(db: AsyncSession, owner: UUID, opening_id: UUID) -> OpeningView:
    """Return one visible opening with its recorded reason and evidence.

    Args:
        db: The session to read with.
        owner: The account.
        opening_id: The opening.

    Returns:
        The opening's view, with its details.

    Raises:
        ResourceNotFoundError: The account is inactive, or the opening is not one
            of its visible openings.
    """
    await DiscussionRepository(db)._owner(owner)
    row, message = await _owned_opening(db, owner, opening_id)
    view = opening_view(row, message)
    metadata = message.message_metadata or {}
    proofs = TypeAdapter(tuple[ContextEvidenceLink, ...]).validate_python(
        metadata.get("discussion_proofs", [])
    )
    reason = metadata.get("discussion_reason")
    return view.model_copy(
        update={
            "reason": reason if isinstance(reason, str) else None,
            "evidence": tuple(
                OpeningEvidence(
                    source=proof.source,
                    observed_at=proof.observed_at,
                    occurred_at=proof.occurred_at,
                    assertion=proof.assertion,
                )
                for proof in proofs
            ),
        }
    )


def _visible_openings(*columns: Any, owner: UUID) -> Select[Any]:
    """The openings a person can see: theirs, still archived and shown in their conversation.

    The ONE filter of the history page and of the notifications hub's badge,
    so the two can never report different sets (ADR-185).
    """
    return (
        select(*columns)
        .select_from(DiscussionOpeningRecord)
        .join(ConversationMessage, ConversationMessage.id == DiscussionOpeningRecord.message_id)
        .where(
            DiscussionOpeningRecord.user_id == owner,
            ConversationMessage.conversation_id == DiscussionOpeningRecord.conversation_id,
            ConversationMessage.role == "assistant",
            ConversationMessage.hidden.is_(False),
        )
    )


async def count_openings(db: AsyncSession, owner: UUID) -> int:
    """The exact number of visible openings, without reading a page of them."""
    return int(await db.scalar(_visible_openings(func.count(), owner=owner)) or 0)


async def list_openings(db: AsyncSession, owner: UUID, request: OpeningPageRequest) -> OpeningPage:
    """Return one page of the person's visible openings, newest first, with their total.

    Args:
        db: The session to read with.
        owner: The account.
        request: The page size and the cursor.

    Returns:
        The page and the exact total of every visible opening.

    Raises:
        ResourceNotFoundError: The account is inactive or deleted.
    """
    await DiscussionRepository(db)._owner(owner)
    page = await native_discussion_page(
        db,
        owner,
        _visible_openings(
            DiscussionOpeningRecord.id,
            DiscussionOpeningRecord.message_id,
            DiscussionOpeningRecord.created_at.label("recorded_at"),
            DiscussionOpeningRecord.state,
            ConversationMessage.content,
            ConversationMessage.message_metadata["discussion_feedback"].astext.label("feedback"),
            owner=owner,
        ),
        limit=request.limit,
        after_id=request.after_id,
    )
    items = tuple(
        OpeningView.model_validate({**row, "created_at": row["recorded_at"]}, extra="ignore")
        for row in page.rows[: request.limit]
    )
    return OpeningPage(
        items=items,
        total=page.total,
        next_cursor=items[-1].id if len(page.rows) > request.limit else None,
    )


async def apply_feedback(
    db: AsyncSession,
    owner: UUID,
    opening_id: UUID,
    feedback: DiscussionFeedback,
    *,
    expected: DiscussionFeedback | None,
) -> OpeningView:
    """Record the person's reaction to an opening, and act on it.

    ``not_now`` pauses discussions for the hours the opening's label promised
    (``promised_pause_hours``), ``avoid_topic`` adds the opening's topic to the
    topics to avoid, ``incorrect`` forgets the context it rested on and requests a
    rebuild. ``useful`` marks the opening engaged; every other
    reaction dismisses it. The same reaction twice changes nothing.

    Args:
        db: The session to write with.
        owner: The account.
        opening_id: The opening.
        feedback: The reaction.
        expected: The reaction the person last saw.

    Returns:
        The opening's view after the change.

    Raises:
        ResourceConflictError: The reaction changed since ``expected``.
        ResourceNotFoundError: The opening is not one of the account's visible
            openings.
    """
    checked = FeedbackRequest(feedback=feedback, expected_feedback=expected)
    feedback, expected = checked.feedback, checked.expected_feedback
    repo = DiscussionRepository(db)
    await repo._owner(owner)
    pref = await repo._preference(owner, lock=True)
    row, message = await _owned_opening(db, owner, opening_id)
    current = (message.message_metadata or {}).get("discussion_feedback")
    if current == feedback:
        return opening_view(row, message)
    if current != expected:
        raise ResourceConflictError("discussion", detail={"error_code": "STALE_STATE"})
    if feedback == "avoid_topic":
        policy = await repo.get_policy(owner)
        topics = policy.forbidden_topics
        if row.topic.strip().casefold() not in {value.strip().casefold() for value in topics}:
            await repo.update_policy(
                owner,
                DiscussionPolicyPatch(forbidden_topics=(*topics, row.topic)),
                expected_revision=pref.revision,
            )
    elif feedback == "not_now":
        await repo.update_policy(
            owner,
            DiscussionPolicyPatch(
                paused_until=datetime.now(UTC) + timedelta(hours=promised_pause_hours(message))
            ),
            expected_revision=pref.revision,
        )
    elif feedback == "incorrect":
        await invalidate_incorrect_context(db, owner, row)
    row.state = "engaged" if feedback == "useful" else "dismissed"
    message.message_metadata = {**(message.message_metadata or {}), "discussion_feedback": feedback}
    await db.flush()
    return opening_view(row, message)


def promised_pause_hours(message: ConversationMessage) -> int:
    """The pause the opening's "not now" label promised when it was published.

    Args:
        message: The opening's archived message.

    Returns:
        The hours written at publication, else the configured pause.
    """
    value = (message.message_metadata or {}).get(FIELD_DISCUSSION_PAUSE_HOURS)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return settings.discussion_pause_hours


async def invalidate_incorrect_context(
    db: AsyncSession, owner: UUID, opening: DiscussionOpeningRecord
) -> None:
    """Forget the context an opening the person called incorrect rested on.

    The context items rooted in its references and their observations are deleted,
    the ready context is cleared, a rebuild is requested and the context epoch
    moves, so nothing built on that context is published.

    Args:
        db: The session to write with.
        owner: The account.
        opening: The opening called incorrect.
    """
    repo = ContextRepository(db)
    pref = await repo._preference(owner, lock=True)
    state = await repo._state(owner, lock=True)
    await db.execute(
        delete(ContextItemRecord).where(
            ContextItemRecord.user_id == owner,
            ContextItemRecord.root_keys.overlap([reference_key(ref) for ref in opening.references]),
        )
    )
    await db.execute(
        delete(ContextObservationRecord).where(
            ContextObservationRecord.user_id == owner,
            ContextObservationRecord.data["reference"].astext.in_(opening.references),
        )
    )
    state.generation += 1
    state.ready_context = None
    state.refresh_requested = True
    await repo._invalidate_context(pref, datetime.now(UTC))
