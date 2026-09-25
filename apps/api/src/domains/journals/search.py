"""Turning a LOOKUP into journal entries — the one door of the journal tool (ADR-318).

The operational injection (``context_builder.build_journal_context``) ranks
LIA's journal on the person's MESSAGE and serves the behavioural directives
their words evoke. A subject the turn discovers on the way — a project named in
an e-mail just read, « what did you notice about my week » — reaches no entry
that way. The journal tool looks such a subject up through this door, which
holds the memory door's rules (``memories/search``, ADR-313):

- the subject is embedded with the JOURNAL's own model, the one its entries
  were indexed with — never the shared message vector of another store;
- the vector is computed BEFORE a session opens, and the session serves one
  query (ADR-304: no transaction held across a network call);
- no vector means « could not look » (``None``), never « nothing matched ».

Two rules are this door's own:

- the raw L0 feedstock is left out — a lookup reads what LIA concluded
  (directives, patterns, portrait facets), never its unripe observations;
- the relevance floor is the CONFIGURED one (``JOURNAL_CONTEXT_MIN_SCORE``),
  passed by the caller — never the floor the adaptive controller learns for the
  injection, and never fed to it. That controller throttles per-MESSAGE
  injection toward a target rate, a different question from « does this entry
  match this subject »: measured on 17 real entries (2026-09-25), its learned
  0.70 kept one of the six entries scoring 0.68-0.705 for « style des
  réponses », where the configured 0.63 kept them all.

The embedding's cost is recorded by the embeddings wrapper into whatever
``TrackingContext`` is active — the chat turn, the routine run, the phone call.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from sqlalchemy import select

from src.core.constants import USER_MESSAGE_EMBEDDING_TRUNCATION_LENGTH
from src.domains.journals.embedding import get_journal_embeddings
from src.domains.journals.models import JournalEntry, JournalEntryLevel
from src.domains.journals.repository import JournalEntryRepository
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: What a lookup never reads: the raw observations consolidation has not ripened.
JOURNAL_LOOKUP_EXCLUDE_LEVELS: Final[list[str]] = [JournalEntryLevel.L0.value]


async def embed_journal_lookup(query: str) -> list[float] | None:
    """The vector of a lookup subject, in the journal's own embedding space.

    Args:
        query: What is looked up — a subject, a person, a project.

    Returns:
        The vector, or None when none could be computed (blank subject,
        provider failure) — which means « could not look ».
    """
    text = query.strip()[:USER_MESSAGE_EMBEDDING_TRUNCATION_LENGTH]
    if not text:
        return None
    try:
        vector: list[float] = await get_journal_embeddings().aembed_query(text)
    except Exception as error:  # noqa: BLE001 — could not look, never « nothing matched »
        logger.warning("journal_lookup_embedding_failed", error_type=type(error).__name__)
        return None
    return vector or None


async def journal_enabled_for(user_id: UUID) -> bool:
    """Whether the person keeps a journal with LIA, read from their own row.

    Read here, never from a run's context: a voice lookup runs on a synthetic
    runtime that carries no preference (ADR-300 wave 4), and reading its
    default would tell the person their journal is off when it is not. The
    operational injection reads the same row for the same reason.

    Args:
        user_id: Whose preference.

    Returns:
        True when the account exists and has its journal on.
    """
    async with get_db_context() as db:
        enabled = (
            await db.execute(select(User.journals_enabled).where(User.id == user_id))
        ).scalar_one_or_none()
    return bool(enabled)


async def search_journal(
    user_id: UUID,
    query: str,
    *,
    limit: int,
    min_score: float,
) -> list[tuple[JournalEntry, float]] | None:
    """The owner's active journal entries most relevant to a lookup.

    Args:
        user_id: Whose journal.
        query: What is looked up.
        limit: Most entries returned.
        min_score: Similarity floor (0.0-1.0).

    Returns:
        ``(entry, similarity)`` pairs, best first — an empty list when the
        search ran and nothing matched, None when it could not run.
    """
    embedding = await embed_journal_lookup(query)
    if not embedding:
        return None
    async with get_db_context() as db:
        return await JournalEntryRepository(db).search_by_relevance(
            user_id=user_id,
            query_embedding=embedding,
            limit=limit,
            min_score=min_score,
            exclude_levels=JOURNAL_LOOKUP_EXCLUDE_LEVELS,
        )


__all__ = [
    "JOURNAL_LOOKUP_EXCLUDE_LEVELS",
    "embed_journal_lookup",
    "journal_enabled_for",
    "search_journal",
]
