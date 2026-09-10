"""What a message read retains, and what a token summary says (ADR-276).

Three narrowings and one rendering, all of them pure, extracted from
``ConversationRepository`` because that file sits at a frozen size cap and the
visibility rule this lot adds does not fit inside it. The cap is the occasion,
not the argument: each of these decides something a reader can be wrong about,
and none of them needs a session to be tested.

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
from typing import Any, TypeVar

from sqlalchemy import func
from sqlalchemy.sql import Select

from src.core.field_names import FIELD_GOOGLE_API_REQUESTS, FIELD_RUN_ID
from src.core.sql_search import LIKE_ESCAPE, escape_like
from src.domains.conversations.models import ConversationMessage

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


def older_than(stmt: _SelectT, before_created_at: datetime | None) -> _SelectT:
    """Keyset pagination: keep what precedes the cursor.

    Strict ``<`` matches the « older than » semantics the scroll-up caller
    uses — the cursor is the ``created_at`` of the oldest message on the page
    the client already holds.

    NOTE: a collision on identical microsecond-precision ``created_at`` could
    skip a message. Negligible in practice; upgrade to a composite
    ``(created_at, id)`` cursor if collisions are ever observed.

    Args:
        stmt: The statement to narrow.
        before_created_at: The cursor, or None for the first page.

    Returns:
        The statement, narrowed when a cursor was given.
    """
    if before_created_at is None:
        return stmt
    return stmt.where(ConversationMessage.created_at < before_created_at)


def token_summary_payload(token_summary: Any | None) -> dict[str, Any] | None:
    """Render one message's token summary for the API.

    Google API costs are added to the LLM cost: what the reader is shown is
    what the turn actually cost, not the model half of it.

    Args:
        token_summary: The joined ``MessageTokenSummary`` row, or None when the
            message has none (every message archived before token tracking, and
            every one the LEFT JOIN found nothing for).

    Returns:
        The payload, or None when there is no summary to render.
    """
    if not token_summary:
        return None
    llm_cost = float(token_summary.total_cost_eur or 0)
    google_cost = float(token_summary.google_api_cost_eur or 0)
    total_cost = llm_cost + google_cost
    return {
        FIELD_RUN_ID: token_summary.run_id,
        "total_tokens": (token_summary.total_prompt_tokens + token_summary.total_completion_tokens),
        "prompt_tokens": token_summary.total_prompt_tokens,
        "completion_tokens": token_summary.total_completion_tokens,
        "cached_tokens": token_summary.total_cached_tokens,
        "cost_eur": total_cost if total_cost > 0 else None,
        FIELD_GOOGLE_API_REQUESTS: token_summary.google_api_requests,
    }
