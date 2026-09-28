"""The radio's own readers of the listener's material — the sources the Today Briefing does not read.

Three tables say which reader reads which source for which part of the journal
(ADR-324 decision 41), and the import refuses a source nobody reads: every source
is read from the briefing's sections (``personal.BRIEFING_SOURCES``) or by a reader
here — the day's and the corner's (``OWN_READERS``, exactly one per source, never a
briefing source), what was DONE today (``DONE_READERS``) and what lies AHEAD this
week (``AHEAD_READERS``) — or the import fails (ADR-085): a source added to the
vocabulary and read by nobody would stay silent for good.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, tzinfo
from types import MappingProxyType
from typing import Final, Protocol
from uuid import UUID

from src.domains.radio.personal import BRIEFING_SOURCES, PersonalDraft, PersonalSource
from src.domains.radio.readers.actions import read_actions
from src.domains.radio.readers.agenda import read_agenda_ahead, read_agenda_done
from src.domains.radio.readers.bookmarks import read_bookmarks
from src.domains.radio.readers.conversation import read_conversation
from src.domains.radio.readers.meetings import read_meetings
from src.domains.radio.readers.notifications import read_notifications
from src.domains.radio.readers.relations import read_relations
from src.domains.radio.readers.reminders import read_reminders_ahead, read_reminders_done
from src.domains.radio.readers.sent_mail import read_sent_mail
from src.domains.radio.readers.spaces import read_spaces
from src.domains.radio.readers.tasks import read_tasks_ahead, read_tasks_done
from src.domains.radio.readers.tickets import read_closed_tickets, read_tickets


class SourceReader(Protocol):
    """Reads one source of the listener's material (its own short session, ADR-304)."""

    async def __call__(self, user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
        """The source's drafts, bounded like every personal source.

        Args:
            user_id: The listener.
            now: The current instant (aware).
            tz: The listener's timezone.
        """
        ...


class ConsultationRecorder(Protocol):
    """Records what one read opened, under the radio's consultation surface (ADR-263)."""

    def __call__(self, *, opened: frozenset[str], failed: frozenset[str], duration_ms: int) -> None:
        """Record it.

        Args:
            opened: The sections actually read.
            failed: Those among them that could not be read.
            duration_ms: The read's wall-clock time (sections read together
                carry the same figure).
        """
        ...


async def _read_relations(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    del tz  # a silence is counted in whole days of elapsed time, not on the listener's clock
    return await read_relations(user_id, now=now)


#: Which reader reads each source the briefing does not carry — the day and the corner.
OWN_READERS: Final[Mapping[PersonalSource, SourceReader]] = MappingProxyType(
    {
        PersonalSource.TICKETS: read_tickets,
        PersonalSource.MEETINGS: read_meetings,
        PersonalSource.NOTIFICATIONS: read_notifications,
        PersonalSource.RELATIONS: _read_relations,
        PersonalSource.SPACES: read_spaces,
        PersonalSource.BOOKMARKS: read_bookmarks,
        PersonalSource.CONVERSATION: read_conversation,
    }
)

#: Which reader reads what each source holds as DONE today (the noon's and the evening's).
DONE_READERS: Final[Mapping[PersonalSource, SourceReader]] = MappingProxyType(
    {
        PersonalSource.AGENDA: read_agenda_done,
        PersonalSource.TASKS: read_tasks_done,
        PersonalSource.REMINDERS: read_reminders_done,
        PersonalSource.TICKETS: read_closed_tickets,
        PersonalSource.SENT_MAILS: read_sent_mail,
        PersonalSource.ACTIONS: read_actions,
    }
)

#: Which reader reads what each source holds for the week AHEAD (the evening's).
AHEAD_READERS: Final[Mapping[PersonalSource, SourceReader]] = MappingProxyType(
    {
        PersonalSource.AGENDA: read_agenda_ahead,
        PersonalSource.TASKS: read_tasks_ahead,
        PersonalSource.REMINDERS: read_reminders_ahead,
    }
)


def assert_every_source_read() -> None:
    """Refuse to import unless every source is read, and the day by exactly one (ADR-085).

    Raises:
        RuntimeError: When a source is read by nobody, or its day by both the briefing
            and a reader here.
    """
    readers = set(OWN_READERS) | set(DONE_READERS) | set(AHEAD_READERS)
    unread = sorted(set(PersonalSource) - BRIEFING_SOURCES - readers)
    twice = sorted(BRIEFING_SOURCES & set(OWN_READERS))
    if unread or twice:
        raise RuntimeError(f"personal sources read by nobody: {unread}; read twice: {twice}")


assert_every_source_read()


__all__ = [
    "AHEAD_READERS",
    "DONE_READERS",
    "OWN_READERS",
    "ConsultationRecorder",
    "SourceReader",
    "assert_every_source_read",
]
