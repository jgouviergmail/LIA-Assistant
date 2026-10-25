"""A relationship's records on one line of time, newest first (owner request 2026-10-24).

The 360° card shows each source in its own section; the timeline shows them
together, dated: open commitments, calls, memories, relayed messages, text
messages. Five sources, one order — ``(instant, kind, id)`` descending — and
one opaque cursor, the last record served. Each source is asked for at most
one page strictly after it (``infrastructure/database/keyset.py``), the pages
are merged, and the cursor moves to the last record kept: a record landing
between two pages neither repeats nor drops one, and a page costs five reads
whatever the depth.

The person is the card's (``RelationsService.scope``, the one resolution) and
every record reads as its section reads it (``relations/mappers.py``). No
count ships here: the card's sections state their exact totals (ADR-185) and
the page shows their sum, so a second count could only disagree with it.
Provider items (e-mails, agenda) are not here: they come from the person's
providers on the card's own windows, and the page merges them in place.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from src.core.config import settings
from src.core.exceptions import raise_invalid_input
from src.domains.memories.models import Memory
from src.domains.memories.repository import MemoryRepository
from src.domains.open_loops.models import OpenLoop
from src.domains.open_loops.repository import OpenLoopRepository
from src.domains.relations.identity_scope import RelationScope
from src.domains.relations.mappers import to_call, to_open_loop, to_peer_message
from src.domains.relations.peer_messages import PeerMessagePage, fetch_peer_messages_page
from src.domains.relations.schemas import (
    RelationMemory,
    RelationTimeline,
    RelationTimelineItem,
    TimelineKind,
)
from src.domains.relations.service import RelationsService
from src.domains.shared.relation_sms import RelationSmsPage, read_relation_sms
from src.domains.telephony.models import PhoneCall
from src.domains.telephony.repository import TelephonyRepository
from src.infrastructure.database.keyset import Keyset
from src.infrastructure.database.session import get_db_context

#: The kinds, in the order that breaks a tie at one instant (descending).
TIMELINE_KINDS: tuple[TimelineKind, ...] = ("call", "memory", "open_loop", "peer_message", "sms")


def encode_cursor(item: RelationTimelineItem) -> str:
    """The cursor after ``item``: opaque to the client, read back by :func:`decode_cursor`."""
    raw = json.dumps([item.at.isoformat(), item.kind, _item_id(item)])
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(token: str) -> tuple[datetime, str, UUID]:
    """Read a cursor back; a forged or damaged one is refused, never guessed.

    Raises:
        HTTPException: 400 when the cursor is not one this API wrote.
    """
    try:
        padded = token + "=" * (-len(token) % 4)
        at_text, kind, item_id = json.loads(base64.urlsafe_b64decode(padded.encode()))
        # Valid JSON is not a cursor: a number where a string belongs would
        # escape as a 500 from `UUID(5)`, so every field is typed first.
        if not (isinstance(at_text, str) and isinstance(item_id, str)):
            raise ValueError("cursor")
        at = datetime.fromisoformat(at_text)
        if at.tzinfo is None or kind not in TIMELINE_KINDS:
            raise ValueError("cursor")
        return at, kind, UUID(item_id)
    # A bad base64, a bad JSON, bad UTF-8 and a bad UUID all raise a ValueError.
    except ValueError, TypeError:
        raise_invalid_input("invalid timeline cursor")


def _item_id(item: RelationTimelineItem) -> str:
    record = item.open_loop or item.call or item.memory or item.peer_message or item.sms
    assert record is not None  # one record per item, by construction
    return str(record.id)


def _sort_key(item: RelationTimelineItem) -> tuple[datetime, str, str]:
    # PostgreSQL orders a uuid by its bytes, which is the order of its
    # canonical lowercase text: the in-memory merge agrees with each source.
    return item.at, item.kind, _item_id(item)


@dataclass(frozen=True, slots=True)
class _Pages:
    """One page of each source, after the same cursor."""

    loops: list[OpenLoop]
    calls: list[PhoneCall]
    memories: list[Memory]
    messages: PeerMessagePage
    sms: RelationSmsPage


async def _read_pages(
    user_id: UUID,
    name: str,
    scope: RelationScope,
    position: tuple[datetime, str, UUID] | None,
    *,
    limit: int,
    include_sms: bool,
) -> _Pages:
    def after(kind: str) -> Keyset | None:
        return None if position is None else Keyset.after(kind, *position)

    async with get_db_context() as db:
        loops = await OpenLoopRepository(db).list_open_for_counterparties_page(
            user_id, scope.loop_names, limit=limit, before=after("open_loop")
        )
        calls = await TelephonyRepository(db).list_calls_for_callees_page(
            user_id, scope.call_names, limit=limit, before=after("call")
        )
        memories = await MemoryRepository(db).list_mentioning_name_page(
            user_id, name, limit=limit, before=after("memory")
        )
    messages = await fetch_peer_messages_page(
        user_id,
        target_key=scope.target_key,
        identity_keys=scope.identity_keys,
        limit=limit,
        before=after("peer_message"),
    )
    sms = (
        await read_relation_sms(user_id, person=name, limit=limit, before=after("sms"))
        if include_sms
        else RelationSmsPage()
    )
    return _Pages(loops, calls, memories, messages, sms)


def _items(pages: _Pages, now: datetime) -> list[RelationTimelineItem]:
    """Every record of the pages, worded as its section words it."""
    return [
        *(
            RelationTimelineItem(
                kind="open_loop", at=loop.created_at, open_loop=to_open_loop(loop, now)
            )
            for loop in pages.loops
        ),
        *(
            RelationTimelineItem(kind="call", at=call.created_at, call=to_call(call))
            for call in pages.calls
        ),
        *(
            RelationTimelineItem(
                kind="memory",
                at=row.created_at,
                memory=RelationMemory(
                    id=str(row.id), content=row.content, created_at=row.created_at
                ),
            )
            for row in pages.memories
        ),
        *(
            RelationTimelineItem(
                kind="peer_message", at=signal.occurred_at, peer_message=to_peer_message(signal)
            )
            for signal in pages.messages.signals
        ),
        *(
            RelationTimelineItem(kind="sms", at=sms.received_at, sms=sms)
            for sms in pages.sms.messages
        ),
    ]


async def build_timeline(
    user_id: UUID, name: str, *, cursor: str | None, include_sms: bool = True
) -> RelationTimeline:
    """One page of the relationship's records, newest first.

    Args:
        user_id: The person whose card it is.
        name: The name the card was opened with.
        cursor: Where the page starts (``next_cursor`` of the previous one).
        include_sms: Whether the text messages are read (the card's rule).

    Returns:
        The page and the cursor of the next one.

    Raises:
        HTTPException: 400 when the cursor is not one this API wrote.
    """
    limit = settings.relations_max_items_per_section
    position = decode_cursor(cursor) if cursor else None
    async with get_db_context() as db:
        scope, _resolver = await RelationsService(user_id).scope(db, name)
    pages = await _read_pages(user_id, name, scope, position, limit=limit, include_sms=include_sms)
    merged = sorted(_items(pages, datetime.now(UTC)), key=_sort_key, reverse=True)
    page = merged[:limit]
    # A source that filled its page may hold more beyond it, even when the
    # merge fits: the next page asks every source again after the last kept.
    filled = (pages.loops, pages.calls, pages.memories, pages.messages.signals, pages.sms.messages)
    more = len(merged) > limit or any(len(rows) == limit for rows in filled)
    return RelationTimeline(
        items=page,
        next_cursor=encode_cursor(page[-1]) if more and page else None,
        page_size=limit,
    )


__all__ = ["TIMELINE_KINDS", "build_timeline", "decode_cursor", "encode_cursor"]
