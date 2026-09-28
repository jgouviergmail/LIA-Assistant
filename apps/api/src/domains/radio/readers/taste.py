"""What the listener cares about and has said they like, for the writer (ADR-324).

Writer CONTEXT, never facts: the writer reads it to choose which stories come
first and how a column is angled, and no line may state it
(:class:`~src.domains.radio.prompting.ListenerTaste`).

- Interests: the active ones, strongest first over the whole set — the order the
  portrait reads them in.
- Stated tastes: the live memories of the ``preference`` category (likes,
  dislikes, tastes), newest first — a taste changes, and the latest word stands.

What may be read is the CALLER's decision: the start knows whether the listener
is in company, whether they let LIA use their memories (``users.memory_enabled``,
the gate the chat's own memory injection reads) and whether the operator left
interests on. This module reads exactly that — as many items as the writer is
shown, each part on a short session of its own (ADR-304) — and records what it
opened: a part that fails is empty and recorded ``failed``, never a silent
success.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Final
from uuid import UUID

import structlog

from src.domains.interests.repository import InterestRepository
from src.domains.memories.models import MemoryCategory
from src.domains.memories.repository import MemoryRepository
from src.domains.radio.prompting import (
    INTERESTS_SHOWN_MAX,
    STATED_TASTES_SHOWN_MAX,
    ListenerTaste,
)
from src.domains.radio.readers import ConsultationRecorder
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

#: The consultation sections the taste is read under.
INTERESTS_SECTION: Final[str] = "interests"
MEMORIES_SECTION: Final[str] = "memories"


async def _interests(user_id: UUID) -> tuple[str, ...]:
    async with get_db_context() as db:
        rows = await InterestRepository(db).list_active_by_signals(
            user_id, limit=INTERESTS_SHOWN_MAX
        )
        return tuple(row.topic for row in rows if row.topic and row.topic.strip())


async def _stated(user_id: UUID) -> tuple[str, ...]:
    async with get_db_context() as db:
        rows = await MemoryRepository(db).get_by_category(
            user_id, MemoryCategory.PREFERENCE.value, limit=STATED_TASTES_SHOWN_MAX
        )
        return tuple(row.content for row in rows if row.content and row.content.strip())


async def _part(
    section: str, read: Callable[[], Awaitable[tuple[str, ...]]], failed: set[str]
) -> tuple[str, ...]:
    try:
        return await read()
    except Exception as exc:  # noqa: BLE001 — a blind part is empty, never the whole start
        failed.add(section)
        logger.warning(
            "radio_taste_unavailable",
            section=section,
            error_type=type(exc).__name__,
            exc_info=True,
        )
        return ()


async def read_taste(
    user_id: UUID,
    *,
    interests_allowed: bool,
    stated_allowed: bool,
    record: ConsultationRecorder,
) -> ListenerTaste:
    """The listener's taste, as far as the start may read it.

    Args:
        user_id: The listener.
        interests_allowed: Whether their interests may be read.
        stated_allowed: Whether their remembered preferences may be read.
        record: Records what was opened.

    Returns:
        The taste; a part not allowed, or not readable, is empty.
    """
    allowed = {INTERESTS_SECTION: interests_allowed, MEMORIES_SECTION: stated_allowed}
    opened = frozenset(section for section, may in allowed.items() if may)
    if not opened:
        return ListenerTaste()
    failed: set[str] = set()
    started = perf_counter()
    taste = ListenerTaste(
        interests=(
            await _part(INTERESTS_SECTION, lambda: _interests(user_id), failed)
            if interests_allowed
            else ()
        ),
        stated=(
            await _part(MEMORIES_SECTION, lambda: _stated(user_id), failed)
            if stated_allowed
            else ()
        ),
    )
    record(
        opened=opened,
        failed=frozenset(failed),
        duration_ms=int((perf_counter() - started) * 1000),
    )
    return taste


__all__ = ["INTERESTS_SECTION", "MEMORIES_SECTION", "read_taste"]
