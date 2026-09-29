"""The listener's material, read for the antenna (ADR-324).

The antenna's ``DaySource``: what the listener's journal may say (decision 41), read
once per gathering and handed on as facts — the DAY and the personal CORNER, and,
for the editions that tell them, what was DONE today and what lies AHEAD this week.

- The sources the Today Briefing carries reuse ITS readers and cache. Cold or
  expired sections are fetched even if the listener never opened the dashboard.
  Only live reads are consultations, filed under the radio's run (ADR-263).
- The others are read by the radio's own readers, concurrently (each opens its
  own short session, ADR-304), and what they OPENED is recorded: a reader that
  raised as ``failed``, never as a silent success. A source read for two parts
  in one gathering is recorded once, ``failed`` when any of its reads was.
- What was done and what lies ahead are read for the editions the desk may be
  asked before it is read again: the edition of now and the one at the end of
  the horizon (the desk's time to live) — a journal produced two minutes before
  noon airs at noon, and it must hold what was done this morning.
- A source the listener switched off is never READ, not merely left unsaid: no
  row is opened and nothing is recorded as consulted.
- In company (public mode) only the neutral sources are read — the weather —
  and no personal reader runs at all.
- A source that fails is silent; the others still speak.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, tzinfo
from time import perf_counter
from uuid import UUID

import structlog

from src.domains.briefing.consultations import SelectedCardsReader
from src.domains.briefing.schemas import CardStatus
from src.domains.radio.formats import FORMAT_SPECS, Frequency, RadioFormat, journal_edition
from src.domains.radio.packs import EDITION_PARTS
from src.domains.radio.personal import (
    BRIEFING_SECTIONS,
    BRIEFING_SOURCES,
    NEUTRAL_SOURCES,
    JournalPart,
    PersonalDraft,
    PersonalFacts,
    PersonalSource,
    briefing_drafts,
    personal_facts,
)
from src.domains.radio.readers import ConsultationRecorder, SourceReader

logger = structlog.get_logger(__name__)


class ListenerDay:
    """The listener's material: shared briefing sources and the radio's own readers."""

    def __init__(
        self,
        *,
        user_id: UUID,
        tz: tzinfo,
        disabled_sources: frozenset[PersonalSource],
        public_mode: bool,
        cards: SelectedCardsReader,
        readers: Mapping[PersonalSource, SourceReader],
        done_readers: Mapping[PersonalSource, SourceReader],
        ahead_readers: Mapping[PersonalSource, SourceReader],
        horizon_s: float,
        record: ConsultationRecorder,
        clock: Callable[[], datetime],
        journal_frequency: Frequency = FORMAT_SPECS[RadioFormat.JOURNAL].default_frequency,
    ) -> None:
        """Bind the reading to one session.

        Args:
            user_id: The listener.
            tz: Their timezone.
            disabled_sources: The sources they switched off for the radio.
            public_mode: Whether they listen in company.
            journal_frequency: Off means no personal journal material is read.
            cards: Reads only the requested sections, fetching when their cache is absent.
            readers: The radio's own reader of each other source (the day and the corner).
            done_readers: The reader of what each source holds as done today.
            ahead_readers: The reader of what each source holds for the week ahead.
            horizon_s: How long a gathering is reused — the desk may be asked for any
                edition that starts within it.
            record: Records what the readers opened.
            clock: The current instant (timezone-aware).
        """
        personal_silent = public_mode or journal_frequency is Frequency.OFF
        excluded = frozenset(PersonalSource) - NEUTRAL_SOURCES if personal_silent else frozenset()
        self._silent = disabled_sources | excluded
        self._user_id = user_id
        self._tz = tz
        self._cards = cards
        self._readers = readers
        self._done_readers = done_readers
        self._ahead_readers = ahead_readers
        self._horizon = timedelta(seconds=horizon_s)
        self._record = record
        self._clock = clock

    async def day(self) -> PersonalFacts:
        """The listener's material, in its four parts (the antenna's ``DaySource``)."""
        started = perf_counter()
        opened: set[str] = set()
        failed: set[str] = set()
        try:
            drafts = await self._briefing(opened, failed)
            for source, more in (await self._own(self._clock(), opened, failed)).items():
                drafts.setdefault(source, []).extend(more)
        finally:
            if opened:
                self._record(
                    opened=frozenset(opened),
                    failed=frozenset(failed),
                    duration_ms=int((perf_counter() - started) * 1000),
                )
        return personal_facts(drafts, disabled=self._silent)

    def parts_due(self, now: datetime) -> frozenset[JournalPart]:
        """The parts an edition starting within the horizon may ask for.

        Args:
            now: The current instant (aware).

        Returns:
            The union of the parts of the edition of ``now`` and of the edition at the
            end of the horizon.
        """
        editions = {
            journal_edition(now.astimezone(self._tz)),
            journal_edition((now + self._horizon).astimezone(self._tz)),
        }
        return frozenset(part for edition in editions for part in EDITION_PARTS[edition])

    async def _briefing(
        self, opened: set[str], failed: set[str]
    ) -> dict[PersonalSource, list[PersonalDraft]]:
        sources = BRIEFING_SOURCES - self._silent
        if not sources:
            return {}
        source_by_section = {BRIEFING_SECTIONS[source]: source for source in sources}

        def on_read(section: str, status: CardStatus) -> None:
            source = source_by_section[section]
            opened.add(source.value)
            if status not in (CardStatus.OK, CardStatus.EMPTY):
                failed.add(source.value)

        try:
            cards = await self._cards(frozenset(source_by_section), on_read=on_read)
        except Exception as exc:  # noqa: BLE001 — the readers' sources still speak
            logger.warning("radio_briefing_unavailable", error_type=type(exc).__name__)
            return {}
        return briefing_drafts(cards)

    def _reads(self, now: datetime) -> list[tuple[PersonalSource, SourceReader]]:
        """Every read of this gathering: the day's and the corner's, then the parts due."""
        due = self.parts_due(now)
        tables = [self._readers]
        if JournalPart.DONE in due:
            tables.append(self._done_readers)
        if JournalPart.AHEAD in due:
            tables.append(self._ahead_readers)
        return [
            (source, reader)
            for table in tables
            for source, reader in table.items()
            if source not in self._silent
        ]

    async def _own(
        self, now: datetime, opened: set[str], failed: set[str]
    ) -> dict[PersonalSource, list[PersonalDraft]]:
        reads = self._reads(now)
        if not reads:
            return {}

        async def recorded_read(
            source: PersonalSource, reader: SourceReader
        ) -> list[PersonalDraft] | None:
            opened.add(source.value)
            succeeded = False
            try:
                drafts = await self._read(source, reader, now)
                succeeded = drafts is not None
                return drafts
            finally:
                if not succeeded:
                    failed.add(source.value)

        results = await asyncio.gather(*(recorded_read(source, reader) for source, reader in reads))
        outcomes = list(zip(reads, results, strict=True))
        merged: dict[PersonalSource, list[PersonalDraft]] = {}
        for (source, _), drafts in outcomes:
            if drafts is not None:
                merged.setdefault(source, []).extend(drafts)
        return merged

    async def _read(
        self, source: PersonalSource, reader: SourceReader, now: datetime
    ) -> list[PersonalDraft] | None:
        """One read's drafts, or ``None`` when it could not be read."""
        try:
            return await reader(self._user_id, now=now, tz=self._tz)
        except Exception as exc:  # noqa: BLE001 — a blind source is silent, never the whole day
            logger.warning(
                "radio_source_unavailable",
                source=source.value,
                error_type=type(exc).__name__,
                exc_info=True,
            )
            return None


__all__ = ["ListenerDay"]
