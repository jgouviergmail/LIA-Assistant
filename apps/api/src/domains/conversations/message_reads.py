"""What a message read retains, and what a token summary says (ADR-276).

Visibility, ordering, search and billing are composed here; the repository
executes the resulting statement. Each rule decides something a reader can be
wrong about, independently of connection management.

**Visibility is the one that carries a decision.** An out-of-turn run — a
workboard ticket LIA executes — archives its two rows exactly like any turn.
That is deliberate: archive-first (ADR-117) persists the question before the
graph runs, and the decision register (ADR-263, lot 6) points at the request
and the answer with ``SET NULL`` tombstones, so a run that archived nothing
would leave a register row indistinguishable from a deleted conversation. The
record therefore stays whole, and this predicate is what keeps the chat quiet.

``include_hidden=True`` belongs to the readers that must see everything: the
account export, the three registers, and the retention sweep. A guard
(``tests/unit/domains/conversations/test_message_reads.py``) refuses any
new message read in the repository that names neither.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict, TypeVar
from uuid import UUID

from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select
from sqlalchemy.sql.selectable import Exists

from src.core.constants import LIVE_TURN_MESSAGE_TYPE, UNICODE_WHITESPACE
from src.core.conversation_target import ConversationKind
from src.core.field_names import FIELD_RUN_ID
from src.core.sql_search import LIKE_ESCAPE, escape_like
from src.domains.chat.models import MessageTokenSummary
from src.domains.conversations.models import Conversation, ConversationMessage
from src.infrastructure.database.keyset import Keyset
from src.infrastructure.database.keyset import older_than as before_keyset

_SelectT = TypeVar("_SelectT", bound=Select)


def visible_only(stmt: _SelectT, *, include_hidden: bool) -> _SelectT:
    """Narrow a message read to what a chat reader may see.

    Args:
        stmt: The statement to narrow.
        include_hidden: True for the export, the registers and the retention
            sweep, which read the whole record.

    Returns:
        The statement, narrowed unless the caller asked for everything.
    """
    if include_hidden:
        return stmt
    return stmt.where(ConversationMessage.hidden.is_(False))


def out_of_graph_rows(stmt: _SelectT) -> _SelectT:
    """Narrow a read to the rows the GRAPH never wrote, injected before the next turn.

    Two families: a proactive notification (an ``assistant`` row of type
    ``proactive_*``) and, since ADR-299, a voice-only exchange of a live
    session (type ``live_turn``, EITHER role). One predicate, so a third
    family joins here rather than in a second copy of the query.

    Args:
        stmt: The statement to narrow.

    Returns:
        The same statement, narrowed.
    """
    kind = ConversationMessage.message_metadata["type"].astext
    return stmt.where(
        or_(
            and_(ConversationMessage.role == "assistant", kind.like("proactive_%")),
            kind == LIVE_TURN_MESSAGE_TYPE,
        )
    )


def matching_content(stmt: _SelectT, search: str | None) -> _SelectT:
    """Narrow to messages whose content contains ``search``.

    Case-insensitive AND accent-insensitive: ``unaccent()`` on both sides, the
    approach the admin user search already uses (the extension is installed by
    migration ``add_unaccent_ext_001``). LIKE wildcards in the reader's term are
    escaped through the shared helper, so ``50%`` matches the literal text
    rather than everything — the board's title search reads the same way, and
    a second copy of the escaping is how the two come to disagree.

    Args:
        stmt: The statement to narrow.
        search: What the reader typed, or None to keep everything.

    Returns:
        The statement, narrowed when a term was given.
    """
    if not search:
        return stmt
    escaped = escape_like(search)
    return stmt.where(
        func.unaccent(ConversationMessage.content).ilike(
            func.unaccent(f"%{escaped}%"), escape=LIKE_ESCAPE
        )
    )


def shown_history_only(stmt: _SelectT) -> _SelectT:
    """Filter ephemeral blank assistant rows BEFORE pagination, using Python's strip alphabet."""
    return stmt.where(
        or_(
            ConversationMessage.role != "assistant",
            func.btrim(ConversationMessage.content, UNICODE_WHITESPACE) != "",
        )
    )


def discussion_transcript(
    conversation_id: UUID, until: datetime
) -> Select[tuple[ConversationMessage]]:
    """Every message the chat shows in one discussion, up to an instant.

    For a reader of the WHOLE discussion — its export: the rows the history
    shows (nothing hidden, no blank progress row), with no page and no limit.
    The upper bound closes the read at the instant the reader chose, so a
    message that lands while the document streams is in the next export, not
    half in this one.

    Args:
        conversation_id: The discussion.
        until: Inclusive upper bound on ``created_at`` (UTC).

    Returns:
        The filtered statement, unordered: its reader orders it with
        :data:`TRANSCRIPT_ORDER`.
    """
    return shown_history_only(
        visible_only(
            select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.created_at <= until,
            ),
            include_hidden=False,
        )
    )


#: A transcript reads forward; the id breaks the tie of two rows sharing an
#: instant, so every export of the same discussion reads in the same order.
TRANSCRIPT_ORDER = (ConversationMessage.created_at.asc(), ConversationMessage.id.asc())


def older_than(
    stmt: _SelectT, before_created_at: datetime | None, before_message_id: UUID | None = None
) -> _SelectT:
    """Keyset pagination: keep what precedes the cursor.

    Strict ``<`` matches the « older than » semantics the scroll-up caller
    uses — the cursor is the ``created_at`` of the oldest message on the page
    the client already holds.

    A message id breaks equal-timestamp ties. Timestamp-only cuts retain the
    legacy semantics for clients which have not adopted the composite cursor.

    Args:
        stmt: The statement to narrow.
        before_created_at: The cursor, or None for the first page.
        before_message_id: The primary key completing a composite cursor.

    Returns:
        The statement, narrowed when a cursor was given.
    """
    if before_created_at is None:
        return stmt
    return stmt.where(
        before_keyset(
            ConversationMessage.created_at,
            ConversationMessage.id,
            Keyset(at=before_created_at, id=before_message_id),
        )
    )


def newer_shown_answer_exists() -> Exists:
    """Whether this run has a later readable answer, independently of the page.

    The conversation/run/time/id index bounds this correlated lookup. Hidden
    and blank progress rows never take the billing display away from an answer.
    """
    newer = aliased(ConversationMessage)
    return (
        select(newer.id)
        .where(
            newer.conversation_id == ConversationMessage.conversation_id,
            newer.message_metadata[FIELD_RUN_ID].astext
            == ConversationMessage.message_metadata[FIELD_RUN_ID].astext,
            newer.role == "assistant",
            newer.hidden.is_(False),
            func.btrim(newer.content, UNICODE_WHITESPACE) != "",
            tuple_(newer.created_at, newer.id)
            > tuple_(ConversationMessage.created_at, ConversationMessage.id),
        )
        .correlate(ConversationMessage)
        .exists()
    )


def history_with_tokens(
    conversation_id: UUID,
    *,
    limit: int,
    include_hidden: bool,
    before_created_at: datetime | None,
    before_message_id: UUID | None,
) -> Select[tuple[ConversationMessage, MessageTokenSummary]]:
    """Compose one owned billing/history page, before executing any query.

    Billing identity is the account plus discussion and run. A legacy summary
    without a discussion belongs to Main alone. The latest readable answer of
    a run carries its total, independently of the requested page.
    """
    billing_match = and_(
        ConversationMessage.message_metadata[FIELD_RUN_ID].astext == MessageTokenSummary.run_id,
        MessageTokenSummary.user_id == Conversation.user_id,
        or_(
            MessageTokenSummary.conversation_id == Conversation.id,
            and_(
                Conversation.kind == ConversationKind.MAIN,
                MessageTokenSummary.conversation_id.is_(None),
            ),
        ),
    )
    if not include_hidden:
        billing_match = and_(
            billing_match,
            or_(
                ConversationMessage.role != "assistant",
                ~newer_shown_answer_exists(),
            ),
        )
    stmt = (
        select(ConversationMessage, MessageTokenSummary)
        .join(Conversation, ConversationMessage.conversation_id == Conversation.id)
        .outerjoin(MessageTokenSummary, billing_match)
        .where(ConversationMessage.conversation_id == conversation_id)
    )
    stmt = visible_only(stmt, include_hidden=include_hidden)
    if not include_hidden:
        stmt = shown_history_only(stmt)
    stmt = older_than(stmt, before_created_at, before_message_id)
    return stmt.order_by(
        ConversationMessage.created_at.desc(), ConversationMessage.id.desc()
    ).limit(limit)


class TokenSummaryPayload(TypedDict):
    """Persisted run accounting projected into a history row."""

    run_id: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_eur: float | None
    google_api_requests: int


def token_summary_payload(token_summary: MessageTokenSummary | None) -> TokenSummaryPayload | None:
    """Render one message's token summary for the API.

    The cost is the row's billed total (model, Maps Platform, generated
    images, paid speech): what the reader is shown is what the turn actually
    cost, not the model half of it.

    Args:
        token_summary: The joined ``MessageTokenSummary`` row, or None when the
            message has none (every message archived before token tracking, and
            every one the LEFT JOIN found nothing for).

    Returns:
        The payload, or None when there is no summary to render.
    """
    if not token_summary:
        return None
    total_cost = float(token_summary.billed_cost_eur)
    return TokenSummaryPayload(
        run_id=token_summary.run_id,
        total_tokens=token_summary.total_prompt_tokens + token_summary.total_completion_tokens,
        prompt_tokens=token_summary.total_prompt_tokens,
        completion_tokens=token_summary.total_completion_tokens,
        cached_tokens=token_summary.total_cached_tokens,
        cost_eur=total_cost if total_cost > 0 else None,
        google_api_requests=token_summary.google_api_requests,
    )
