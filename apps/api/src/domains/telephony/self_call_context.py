"""What an owner call knows about the person before it says hello (lot 4).

The third-party mandate receives a free/busy projection and nothing else — the
callee is a stranger. The owner mandate speaks to the account holder on a line
they verified, so it may carry what the chat would know: the memories relevant
to the purpose, the next day and a half of agenda, the pending reminders, the
open loops, and the last few exchanges of the conversation. Each section comes
from the reader the chat already uses; nothing here re-implements a query.

Three rules, each a test:

- **the switch decides everything**: ``phone_rich_context_enabled`` off renders
  nothing and opens nothing;
- **a budget, spent in priority order, with the cut stated**: sections are
  rendered under ``TELEPHONY_SELF_CONTEXT_MAX_TOKENS`` and every section that
  did not fit whole says how many lines were left out;
- **every section opened is filed** on the ``phone_call`` consultation surface
  (ADR-263): a section that could not be read files ``failed``, an empty one
  was still opened, a source the person does not have (no calendar) was
  never opened and files nothing, and the switch off files nothing.

A fetcher returns LINES. The default ones open their own session each — a
handful of indexed reads, sequential, never a shared ``AsyncSession`` across a
gather.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from src.core.config import settings
from src.core.i18n_telephony import get_context_headings
from src.core.time_utils import format_datetime_for_display
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.domains.telephony.budget import fit_lines, token_count

logger = structlog.get_logger(__name__)

#: A fetcher returns the section's lines, or None when the source does not
#: exist for this person (no calendar connector): not opened, so not filed.
SectionFetcher = Callable[[], Awaitable[list[str] | None]]
#: Turns a stored message (Markdown, or an HTML card) into the prose a voice
#: can read; handed in by the caller, like the memory fetcher, because the
#: flattening lives in ``agents``.
TextFlattener = Callable[[str], str]

#: The sections, in the order the budget is spent — what a voice needs first
#: when the person starts talking: who they are, then their day.
SECTION_ORDER: Final[tuple[str, ...]] = (
    "memories",
    "agenda",
    "reminders",
    "open_loops",
    "recent_exchanges",
)

_SURFACE: Final = "phone_call"
_AGENDA_LOOKAHEAD_HOURS: Final = 36
#: Lines a section may contribute before the budget even looks at it.
MEMORY_LINES_MAX: Final = 12
_MAX_LINES_PER_SECTION: Final = MEMORY_LINES_MAX
#: The last exchanges: a few turns, each cut to a spoken-size excerpt.
_RECENT_EXCHANGES_MAX: Final = 6
_RECENT_EXCHANGE_MAX_CHARS: Final = 240


@dataclass(frozen=True)
class ContextSection:
    """One rendered section.

    Attributes:
        key: Its key on the surface and in :data:`SECTION_ORDER`.
        lines: What it says, one fact per line.
        failed: True when the source could not be read.
        opened: False when the person has no such source — nothing to file.
    """

    key: str
    lines: list[str] = field(default_factory=list)
    failed: bool = False
    opened: bool = True


async def _fetch_agenda(user_id: UUID, *, timezone: str, language: str) -> list[str] | None:
    """The next day and a half, with titles: the owner's own agenda.

    Returns:
        The lines, or None when the person has no calendar to open.
    """
    from src.domains.briefing.formatters import format_agenda_event
    from src.domains.connectors.calendar_access import CalendarUnavailable, open_active_calendar

    now = datetime.now(UTC)
    async with open_active_calendar(user_id) as access:
        if isinstance(access, CalendarUnavailable):
            return None
        result = await access.client.list_events(
            time_min=now.isoformat(),
            time_max=(now + timedelta(hours=_AGENDA_LOOKAHEAD_HOURS)).isoformat(),
            max_results=_MAX_LINES_PER_SECTION,
            calendar_id=access.calendar_id,
            fields=["id", "summary", "start", "end", "location"],
        )
    tz = ZoneInfo(timezone)
    lines: list[str] = []
    for raw in result.get("items", []) or []:
        item = format_agenda_event(raw, tz, language)
        where = f" ({item.location})" if getattr(item, "location", None) else ""
        end = f"-{item.end_local}" if item.end_local else ""
        lines.append(f"{item.start_local}{end}: {item.title}{where}")
    return lines


async def _fetch_reminders(user_id: UUID, *, timezone: str, language: str) -> list[str]:
    """The pending reminders, soonest first."""
    from src.domains.reminders.service import ReminderService
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        reminders = await ReminderService(db).list_pending_for_user(user_id)
    lines: list[str] = []
    for reminder in reminders[:_MAX_LINES_PER_SECTION]:
        when = getattr(reminder, "trigger_at", None)
        stamp = format_datetime_for_display(when, timezone, language) if when else ""
        content = getattr(reminder, "content", "") or getattr(reminder, "original_message", "")
        lines.append(f"{stamp}: {content}".strip(": "))
    return lines


async def _fetch_open_loops(user_id: UUID) -> list[str]:
    """What the person is waiting on, or owes."""
    from src.domains.open_loops.repository import OpenLoopRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        loops = await OpenLoopRepository(db).list_open_for_user(
            user_id, limit=_MAX_LINES_PER_SECTION
        )
    lines: list[str] = []
    for loop in loops:
        who = f" ({loop.counterparty})" if getattr(loop, "counterparty", None) else ""
        lines.append(f"{loop.subject}{who}")
    return lines


async def _fetch_recent_exchanges(user_id: UUID, *, flatten: TextFlattener) -> list[str]:
    """The last few visible exchanges, oldest first, through the repository.

    An assistant answer is often an HTML card or Markdown: the voice reads its
    WORDS, flattened by the caller's own flattener, never its markup.
    """
    from src.domains.conversations.repository import ConversationRepository
    from src.infrastructure.cache.conversation_cache import get_conversation_id_cached
    from src.infrastructure.database.session import get_db_context

    conversation_id = await get_conversation_id_cached(user_id)
    if conversation_id is None:
        return []
    async with get_db_context() as db:
        rows = await ConversationRepository(db).get_messages_for_conversation(
            UUID(str(conversation_id)), limit=_RECENT_EXCHANGES_MAX, order_desc=True
        )
    lines: list[str] = []
    for row in reversed(list(rows)):
        content = " ".join(flatten(str(getattr(row, "content", "") or "")).split())
        if content:
            lines.append(f"{row.role}: {content[:_RECENT_EXCHANGE_MAX_CHARS]}")
    return lines


def default_fetchers(
    user_id: UUID,
    *,
    language: str,
    timezone: str,
    memory_fetcher: SectionFetcher,
    flatten: TextFlattener,
) -> dict[str, SectionFetcher]:
    """The real readers, one per section, each on a session of its own.

    The memories reader and the text flattener are HANDED IN: both live in
    the ``agents`` package, which ``telephony`` must not import (the T2
    cycle). They are required arguments rather than optional ones, so a
    caller cannot forget them and silently ship a voice that knows nothing,
    or one that reads HTML aloud.

    Args:
        user_id: Whose context.
        language: Backend-canonical language of the rendering.
        timezone: The person's IANA zone.
        memory_fetcher: The memories section, supplied by the caller.
        flatten: Turns a stored message into prose (an HTML card, Markdown).

    Returns:
        One fetcher per section of :data:`SECTION_ORDER`.
    """
    return {
        "memories": memory_fetcher,
        "agenda": lambda: _fetch_agenda(user_id, timezone=timezone, language=language),
        "reminders": lambda: _fetch_reminders(user_id, timezone=timezone, language=language),
        "open_loops": lambda: _fetch_open_loops(user_id),
        "recent_exchanges": lambda: _fetch_recent_exchanges(user_id, flatten=flatten),
    }


async def _read_sections(fetchers: Mapping[str, SectionFetcher]) -> list[ContextSection]:
    sections: list[ContextSection] = []
    for key in SECTION_ORDER:
        fetch = fetchers.get(key)
        if fetch is None:
            continue
        try:
            lines = await fetch()
            if lines is None:
                sections.append(ContextSection(key=key, opened=False))
            else:
                sections.append(ContextSection(key=key, lines=list(lines)))
        except Exception as exc:  # noqa: BLE001 — one blind section never costs the call
            logger.warning(
                "self_call_context_section_failed", section=key, error_type=type(exc).__name__
            )
            sections.append(ContextSection(key=key, failed=True))
    return sections


def _render(sections: list[ContextSection], *, language: str, budget_tokens: int) -> str:
    """Render the sections under the budget, priority order, cuts stated."""
    headings = get_context_headings(language)
    blocks: list[str] = []
    remaining = budget_tokens
    for section in sections:
        if not section.lines:
            continue
        heading = f"## {headings.get(section.key, section.key)}"
        heading_cost = token_count(heading) + 1
        if remaining - heading_cost <= 0:
            break
        text, cut = fit_lines(section.lines, budget_tokens=remaining - heading_cost)
        kept = len(text.splitlines())
        if cut:
            text += f"\n{headings['more_not_shown'].format(count=len(section.lines) - kept)}"
        block = f"{heading}\n{text}"
        blocks.append(block)
        remaining -= token_count(block) + 1
        if cut:
            break
    return "\n\n".join(blocks)


async def build_owner_context(
    user_id: UUID,
    *,
    language: str,
    rich_context_enabled: bool,
    fetchers: Mapping[str, SectionFetcher],
    surface: str = _SURFACE,
) -> str:
    """Assemble the context block of an owner call, and file what was opened.

    Args:
        user_id: Whose context.
        language: Backend-canonical language of the headings and dates.
        rich_context_enabled: The person's own switch; off renders nothing.
        fetchers: Section readers — :func:`default_fetchers` for the real ones.
        surface: The consultation surface the reads are filed on — the
            call's by default, a direct live session's when it is the caller
            (ADR-300 wave 4: the same block, filed where it was read).

    Returns:
        The rendered block, or "" when the switch is off.
    """
    if not rich_context_enabled:
        return ""
    started = time.monotonic()
    sections = await _read_sections(fetchers)
    text = _render(
        sections, language=language, budget_tokens=settings.telephony_self_context_max_tokens
    )
    record_surface_consultations(
        surface=surface,
        user_id=user_id,
        opened=[section.key for section in sections if section.opened],
        failed=[section.key for section in sections if section.failed],
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return text


__all__: list[str] = [
    "MEMORY_LINES_MAX",
    "SECTION_ORDER",
    "ContextSection",
    "SectionFetcher",
    "TextFlattener",
    "build_owner_context",
    "default_fetchers",
]
