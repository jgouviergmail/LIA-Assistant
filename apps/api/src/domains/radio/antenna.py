"""The antenna: one slot's segment, from the editor's desk to the mixed audio.

The orchestrator asks for a slot; the antenna gathers what the segment may say —
the listener's clock, their day, the format's shortlist and, for an analysis,
the analyst's reading of its story — has it written, checked, voiced and mixed
(:func:`~src.domains.radio.production.produce_segment`), and remembers what it
said, so the session never says it twice. What the NEXT sessions must not say
again is what the listener heard: each produced segment carries, line by line,
what its lines tell (:func:`heard_lines`), and the session's loop files a line in
the aired ledger once the player has passed it (ADR-324 decision 35).

The day and the news are read at most once per ``desk_ttl_s`` — the grid asks
what is available at every planning, and a production every twenty seconds must
not re-read the briefing each time — and always through ports: the caller's
adapters read the briefing's sections and the newsroom's store, the ledger lives
in Redis, and every model call is already bound to the session's slots and
tracker. A source that fails reads as empty (its formats become unavailable and
the grid plays something else); a ledger that cannot be read is logged, and this
session's own memory still keeps it from repeating itself.

The start produces two slots at once: the gathering is serialised, so they share
ONE reading of the sources — two would open the listener's sources twice, and
file two consultations for one act.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable, Coroutine, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any, Final, Protocol
from uuid import UUID

import structlog

from src.domains.radio.aired import HeardLine
from src.domains.radio.cast import Cast
from src.domains.radio.editorial import (
    NO_SUBJECTS,
    NewsCandidate,
    Subjects,
    news_facts,
    news_formats,
)
from src.domains.radio.facts import FactKind, FactPack, RadioFact, clock_fact, notification_key
from src.domains.radio.flash import FlashNote, flash_pack, is_flash_seq
from src.domains.radio.formats import (
    FORMAT_SPECS,
    JournalEdition,
    Material,
    RadioFormat,
    journal_edition,
)
from src.domains.radio.meanings import Vector, headline_key
from src.domains.radio.media import prepare, segment_path
from src.domains.radio.news_desk import read_news_desk
from src.domains.radio.packs import (
    LEDGER_EXEMPT_KINDS,
    SAID_ONCE_KINDS,
    STORY_KINDS,
    Desk,
    available_formats,
    pack_for,
)
from src.domains.radio.personal import PersonalFacts
from src.domains.radio.production import (
    LineChecker,
    NothingAired,
    ProducedSegment,
    ProductionLimits,
    ProductionOutcome,
    ScriptWriter,
    TtsLedger,
    VoicedLine,
    VoiceEngine,
    WritingRequest,
    produce_segment,
)
from src.domains.radio.programme import Slot
from src.domains.radio.prompting import (
    HEADLINE_SHOWN_MAX_CHARS,
    ON_AIR_SHOWN_MAX,
    AnalysisRequest,
)
from src.infrastructure.observability.metrics_radio import (
    radio_segment_production_seconds,
    radio_segments_total,
)

logger = structlog.get_logger(__name__)

#: A slot whose format found nothing on the desk to talk about (a metric outcome).
NOTHING_TO_SAY: Final[str] = "nothing_to_say"
#: A production that broke on a defect (a metric outcome; the loop reads it as none).
PRODUCTION_ERROR: Final[str] = "error"
#: The outcomes where the station chose not to air — never a failure (decision 33).
NOTHING_AIRED_OUTCOMES: Final[frozenset[str]] = frozenset(
    {NOTHING_TO_SAY, ProductionOutcome.SCRIPT_REFUSED.value}
)


class DaySource(Protocol):
    """The listener's own material: their day (and the weather) and their personal corner."""

    async def day(self) -> PersonalFacts:
        """The day's and the corner's facts."""
        ...


#: How many programmes back a programme's subjects are kept, by place: an angle needs
#: the one just before (a flash has a place of its own, so a little more).
TOLD_KEPT_SLOTS: Final[int] = 4


class NewsSource(Protocol):
    """The stored stories of the listener's feeds."""

    async def candidates(
        self, *, heard_keys: frozenset[str], heard_stories: frozenset[str]
    ) -> list[NewsCandidate]:
        """The stories the shortlists choose from, the ones never heard first — every
        language fills a bound, which must keep what can still air."""
        ...


class AiredLedger(Protocol):
    """What the listener already heard — across sessions (the session's loop files it)."""

    async def heard(self) -> tuple[frozenset[str], frozenset[str]]:
        """The fact keys and the story fingerprints already aired."""
        ...

    async def headlines(self) -> tuple[str, ...]:
        """The headlines of the stories heard recently, oldest first."""
        ...

    async def treated(self) -> dict[RadioFormat, Subjects]:
        """What each angle programme took, still remembered (decision 39)."""
        ...


class HeadlineVectors(Protocol):
    """The headlines' meanings, shared across sessions (``meanings.RedisHeadlineVectors``)."""

    async def vectors(self, titles: Sequence[str]) -> Mapping[str, Vector]:
        """A vector for each headline; raises when they cannot be read."""
        ...


class Analyst(Protocol):
    """Reads one story's full text (the radio's analyst slot)."""

    async def analyse(
        self,
        request: AnalysisRequest,
        *,
        story_key: str,
        min_points: int,
        max_points: int,
    ) -> tuple[RadioFact, ...]:
        """The analysis facts, or none."""
        ...


@dataclass(frozen=True, slots=True)
class AntennaSetup:
    """What the antenna knows for the whole session.

    Attributes:
        session_id: The session (names its audio directory).
        media_root: Where the sessions' audio lies.
        timezone: The listener's timezone.
        language: The listener's language (backend-canonical code).
        station_name: The station's name (any line may say it — the editor reads
            a mention of it as no claim, digits included).
        listener_name: Their first name, offered to the host's formats.
        checked: The formats the model verifier reads (the listener's setting).
        analysis_min_points: The fewest points the analyst is asked for.
        analysis_max_points: The most points kept.
        desk_ttl_s: How long the day and the news are reused.
        same_event_similarity: Two headlines this close in meaning tell one
            event (0: the words alone judge, and no meaning is read).
        limits: A production's bounds.
    """

    session_id: UUID
    media_root: Path
    timezone: tzinfo
    language: str
    station_name: str
    listener_name: str | None
    checked: frozenset[RadioFormat]
    analysis_min_points: int
    analysis_max_points: int
    desk_ttl_s: float
    same_event_similarity: float
    limits: ProductionLimits


@dataclass(frozen=True, slots=True)
class AntennaCrew:
    """Who makes a segment: the writer, the analyst, the checker, the voices.

    Attributes:
        writer: Writes the script.
        analyst: Reads an analysis's story.
        checker: The model verifier (used on ``AntennaSetup.checked`` formats).
        engine: The voice engine.
        cast: The voice of every role.
        tts_ledger: Where every paid synthesis is billed.
    """

    writer: ScriptWriter
    analyst: Analyst
    checker: LineChecker | None
    engine: VoiceEngine
    cast: Cast
    tts_ledger: TtsLedger


@dataclass(frozen=True, slots=True)
class _Gathered:
    at: datetime
    personal: PersonalFacts
    candidates: tuple[NewsCandidate, ...]


def heard_facts(pack: FactPack, aired: Sequence[str]) -> list[RadioFact]:
    """What the listener heard of a pack: the facts its voiced lines cite.

    A story the writer left out (a brief tells one of the stories it is offered)
    stays on the desk for a later programme. An analysis that aired told its
    story, whether or not a line cited the article itself.

    Args:
        pack: The segment's facts.
        aired: The ids its voiced lines cite.

    Returns:
        The facts heard, the analysed story included.
    """
    facts = pack.by_id()
    heard = [facts[fid] for fid in aired if fid in facts]
    if any(fact.kind is FactKind.ANALYSIS for fact in heard):
        heard += [fact for fact in pack.facts if fact.kind is FactKind.NEWS and fact not in heard]
    return heard


def heard_lines(
    pack: FactPack, lines: Sequence[VoicedLine], candidates: Iterable[NewsCandidate]
) -> tuple[HeardLine, ...]:
    """What each voiced line tells the listener, in air order — filed as they hear it.

    A fact is told by the first line citing it; the first line citing an analysis
    point tells the analysed story too, cited or not (:func:`heard_facts`); a
    story's headline goes with the line that first tells it. A line that tells
    nothing to remember (a transition, the clock) is left out.

    Args:
        pack: The segment's facts.
        lines: Its voiced lines.
        candidates: The stories it could have told.

    Returns:
        One entry per line that tells something.
    """
    facts = pack.by_id()
    offered = {candidate.key: candidate for candidate in candidates}
    angle = None if FORMAT_SPECS[pack.format].renews_subjects else pack.format
    told: set[str] = set()
    titles: set[str] = set()
    memory: list[HeardLine] = []
    for line in lines:
        heard = [facts[ref] for ref in line.refs if ref in facts and ref not in told]
        if any(fact.kind is FactKind.ANALYSIS for fact in heard):
            heard += [f for f in pack.facts if f.kind is FactKind.NEWS and f.id not in told]
        told.update(fact.id for fact in heard)
        keys = {fact.key for fact in heard if fact.kind not in LEDGER_EXEMPT_KINDS}
        news = {fact.key for fact in heard if fact.kind in STORY_KINDS}
        headlines = [t for t in aired_headlines(heard, offered.values()) if t not in titles]
        titles.update(headlines)
        if not keys:
            continue
        memory.append(
            HeardLine(
                offset_s=line.offset_s,
                personal=frozenset(keys - news),
                news=frozenset(news),
                stories=frozenset(
                    offered[key].fingerprint
                    for key in keys
                    if key in offered and offered[key].fingerprint
                ),
                headlines=tuple(headlines),
                angle=angle,
            )
        )
    return tuple(memory)


def aired_headlines(facts: Sequence[RadioFact], candidates: Iterable[NewsCandidate]) -> list[str]:
    """The headlines of the stories a programme told, in the order it told them, each once.

    A programme's own title names one or two of its stories; the next news writer
    needs every one it told to leave them out — measured on dev 2026-09-27, the
    headlines retold a match the bulletin before them had told, from another
    article.

    Args:
        facts: What the listener heard of the programme.
        candidates: The stories it could have told.

    Returns:
        Their headlines, as their outlets wrote them.
    """
    by_key = {
        candidate.key: candidate.title.strip()[:HEADLINE_SHOWN_MAX_CHARS]
        for candidate in candidates
    }
    told = [by_key[fact.key] for fact in facts if by_key.get(fact.key)]
    return list(dict.fromkeys(told))


class Antenna:
    """One session's producer: what is available, and one slot's segment."""

    def __init__(
        self,
        *,
        setup: AntennaSetup,
        crew: AntennaCrew,
        day: DaySource,
        news: NewsSource,
        aired: AiredLedger,
        headlines: HeadlineVectors,
        clock: Callable[[], datetime],
    ) -> None:
        """Bind the antenna to a session.

        Args:
            setup: What it knows for the whole session.
            crew: Who makes a segment.
            day: The listener's day.
            news: The stored stories.
            aired: What the listener already heard.
            headlines: The headlines' meanings.
            clock: The current instant (timezone-aware).
        """
        self._setup = setup
        self._crew = crew
        self._day = day
        self._news = news
        self._aired = aired
        self._headlines = headlines
        self._clock = clock
        self._gathered: _Gathered | None = None
        self._gathering = asyncio.Lock()
        self._heard_keys: set[str] | None = None
        self._heard_stories: set[str] = set()
        # What THIS session said: its own keys (the evening journal goes over the
        # earlier sessions' alone) and the moment's kinds (the weather is said once).
        self._aired_here: set[str] = set()
        self._said: set[FactKind] = set()
        # The moments a production IN FLIGHT carries: the start produces two slots at
        # once, and both desks read ``_said`` before either had aired — the weather
        # reached the opening and the listener's day alike (cold review, 2026-09-27).
        self._in_flight: set[FactKind] = set()
        #: The notes a news flash is telling while it is produced: held from the corner.
        self._flash_keys: set[str] = set()
        # One reading per story a session: a production that failed after the
        # analyst ran does not buy the same reading twice.
        self._analyses: dict[str, tuple[RadioFact, ...]] = {}
        # The headlines of the NEWS stories heard — never a title of the listener's
        # own day, which would carry their life into a prompt whose voices may never
        # speak of it.
        self._on_air: deque[str] = deque(maxlen=ON_AIR_SHOWN_MAX)
        # Every headline heard over the ledger's horizon (not only the ones shown): the
        # shortlists leave out another article of a story under a near-identical one.
        self._heard_headlines: list[str] = []
        # What each angle programme took (seeded from the ledger with what was heard),
        # and what each programme produced told, by its place: an angle never takes the
        # subject of the programme just before (decision 39).
        self._taken: dict[RadioFormat, Subjects] = {}
        self._told_at: dict[int, Subjects] = {}
        # Whose turn it is, per format: the interests after a programme drawn from the
        # sources, the sources after one drawn from the interests (decision 40).
        self._interests_next: dict[RadioFormat, bool] = {}
        # The meanings read this session, and until when a blind reading rests.
        self._vectors: dict[str, Vector] = {}
        self._blind_until: datetime | None = None
        self._reading = asyncio.Lock()
        self._prepared = False

    async def available(self) -> frozenset[RadioFormat]:
        """The formats that have something to say now (the grid's ``available``)."""
        desk, _ = await self._desk(self._local_now())
        return available_formats(desk)

    async def produce(
        self, slot: Slot, *, previous: RadioFormat | None, following: RadioFormat | None
    ) -> ProducedSegment | NothingAired | None:
        """Produce one slot's segment, or say why there is none.

        Args:
            slot: The slot.
            previous: The format before it (its writer hands over from it).
            following: The format after it (its writer announces it).

        Returns:
            The segment; ``NothingAired`` when there was nothing to say or
            the editor refused the script; ``None`` when the production
            failed (every outcome is logged and counted).
        """
        return await self._counted(
            slot.format, self._produce(slot, previous=previous, following=following)
        )

    async def produce_flash(
        self,
        notes: Sequence[FlashNote],
        *,
        seq: int,
        cuts: RadioFormat | None,
        resumes: RadioFormat | None,
    ) -> ProducedSegment | NothingAired | None:
        """Produce a news flash for ``notes`` (ADR-324 decision 32), or say why not.

        Args:
            notes: What LIA just wrote to the listener, oldest first.
            seq: The flash's place (its audio's name).
            cuts: The programme the flash interrupts, if one is on air.
            resumes: The programme the station goes back to after it.

        Returns:
            The segment; ``NothingAired`` when the editor refused its script;
            ``None`` when the production failed (logged and counted).
        """
        slot = Slot(
            seq=seq,
            format=RadioFormat.FLASH,
            station_id=False,
            air_at=self._clock(),
            duration_s=float(FORMAT_SPECS[RadioFormat.FLASH].target_seconds),
        )
        return await self._counted(
            RadioFormat.FLASH, self._flash(slot, notes, cuts=cuts, resumes=resumes)
        )

    async def _flash(
        self,
        slot: Slot,
        notes: Sequence[FlashNote],
        *,
        cuts: RadioFormat | None,
        resumes: RadioFormat | None,
    ) -> tuple[ProducedSegment | None, str]:
        """A flash of the notes the listener has not heard — the corner may have told one.

        The notes it tells are held from the corner while it is produced: the
        corner reads the same notifications, newest first.
        """
        heard = await self._keys()
        told = [note for note in notes if notification_key(note.id) not in heard]
        if not told:
            logger.info("radio_segment_nothing_to_say", format=slot.format.value)
            return None, NOTHING_TO_SAY
        keys = {notification_key(note.id) for note in told}
        self._flash_keys |= keys
        try:
            return await self._voice(
                slot, flash_pack(told), {}, self._local_now(), None, cuts, resumes, edition=None
            )
        finally:
            self._flash_keys -= keys

    async def _counted(
        self,
        fmt: RadioFormat,
        production: Coroutine[Any, Any, tuple[ProducedSegment | None, str]],
    ) -> ProducedSegment | NothingAired | None:
        """Run a production and count how it went — the one place that sees every outcome.

        It is also where the station's silence is told apart from a failure:
        the loop reads only what comes back.
        """
        started = time.perf_counter()
        label = fmt.value
        try:
            segment, outcome = await production
        except Exception:
            radio_segments_total.labels(format=label, outcome=PRODUCTION_ERROR).inc()
            raise
        radio_segments_total.labels(format=label, outcome=outcome).inc()
        if segment is not None:
            radio_segment_production_seconds.labels(format=label).observe(
                time.perf_counter() - started
            )
            return segment
        return NothingAired(outcome) if outcome in NOTHING_AIRED_OUTCOMES else None

    async def _produce(
        self, slot: Slot, *, previous: RadioFormat | None, following: RadioFormat | None
    ) -> tuple[ProducedSegment | None, str]:
        """The segment (or none) and the outcome that names how it went."""
        local_now = self._local_now()
        desk, shortlists = await self._desk(local_now, before=slot.seq - 1)
        if FORMAT_SPECS[slot.format].needs_analysis:
            desk = await self._with_analysis(desk, shortlists.get(slot.format, []))
        tz = self._setup.timezone
        mark = slot.clock_mark.astimezone(tz) if slot.clock_mark else None
        # The journal's edition is the one its AIR time falls in (a programme is produced
        # ahead of it), decided once here for the desk and the writer (decision 41).
        edition = journal_edition(slot.air_at.astimezone(tz))
        # No await from here to the reservation: a sibling cannot slip in between.
        desk = replace(desk, said=desk.said | self._in_flight, edition=edition)
        pack = pack_for(slot.format, desk, clock_mark=mark)
        if pack is None:
            logger.info("radio_segment_nothing_to_say", format=slot.format.value)
            return None, NOTHING_TO_SAY
        moments = {fact.kind for fact in pack.facts if fact.kind in SAID_ONCE_KINDS}
        self._in_flight |= moments
        try:
            return await self._voice(
                slot,
                pack,
                shortlists,
                local_now,
                mark,
                previous,
                following,
                edition=edition if slot.format is RadioFormat.JOURNAL else None,
            )
        finally:
            # Given back whatever happened: what aired is in ``_said`` by now.
            self._in_flight -= moments

    async def _voice(
        self,
        slot: Slot,
        pack: FactPack,
        shortlists: dict[RadioFormat, list[NewsCandidate]],
        local_now: datetime,
        mark: datetime | None,
        previous: RadioFormat | None,
        following: RadioFormat | None,
        *,
        edition: JournalEdition | None,
    ) -> tuple[ProducedSegment | None, str]:
        """Write, check and voice one pack, and remember what the listener heard."""
        request = WritingRequest(
            format=slot.format,
            pack=pack,
            language=self._setup.language,
            local_now=local_now,
            station_id=slot.station_id,
            station_name=self._setup.station_name,
            clock_mark=mark,
            previous=previous,
            following=following,
            listener_name=self._setup.listener_name,
            on_air=tuple(self._on_air),
            roles=self._crew.cast.voiced_roles(FORMAT_SPECS[slot.format].roles),
            edition=edition,
        )
        if not self._prepared:
            await prepare(self._setup.media_root, self._setup.session_id)
            self._prepared = True
        result = await produce_segment(
            request,
            segment_path(self._setup.media_root, self._setup.session_id, slot.seq),
            writer=self._crew.writer,
            engine=self._crew.engine,
            cast=self._crew.cast,
            ledger=self._crew.tts_ledger,
            limits=self._setup.limits,
            checker=self._crew.checker if slot.format in self._setup.checked else None,
        )
        if result.segment is None:
            logger.info(
                "radio_segment_not_produced",
                format=slot.format.value,
                outcome=result.outcome.value,
                refusal=result.refusal.value if result.refusal else None,
                dropped=[violation.value for violation in result.dropped],
                error_code=result.error_code,
            )
            return None, result.outcome.value
        heard = heard_facts(pack, result.aired)
        offered = [candidate for chosen in shortlists.values() for candidate in chosen]
        titles = aired_headlines(heard, offered)
        if FORMAT_SPECS[slot.format].material is Material.NEWS:
            told = [title for title in titles if title not in self._on_air]
            self._on_air.extend(told)
            self._heard_headlines.extend(told)
            # A programme that aired hands the format's next turn to the other material.
            drawn = shortlists.get(slot.format, [])
            if drawn:
                self._interests_next[slot.format] = not drawn[0].from_interests
        subjects = await self._remember(heard, shortlists, titles)
        self._note_told(slot, subjects)
        memory = heard_lines(pack, result.lines, offered)
        return replace(result.segment, memory=memory), result.outcome.value

    def _local_now(self) -> datetime:
        return self._clock().astimezone(self._setup.timezone)

    def _note_told(self, slot: Slot, subjects: Subjects) -> None:
        """Remember what a programme told: by its place, and as taken by an angle.

        A flash tells what LIA wrote, never a news subject, and interrupts rather than
        precedes: its place (``FLASH_SEQ_BASE`` onward) is not the programmes'.
        """
        if is_flash_seq(slot.seq):
            return
        self._told_at = {
            seq: told for seq, told in self._told_at.items() if seq >= slot.seq - TOLD_KEPT_SLOTS
        }
        self._told_at[slot.seq] = subjects
        if not FORMAT_SPECS[slot.format].renews_subjects:
            self._taken[slot.format] = self._taken.get(slot.format, NO_SUBJECTS) | subjects

    def _excluded(self, before: int | None) -> dict[RadioFormat, Subjects]:
        """What each angle leaves out: its own former subjects, the programme before's."""
        previous = self._told_at.get(before, NO_SUBJECTS) if before is not None else NO_SUBJECTS
        return {
            fmt: self._taken.get(fmt, NO_SUBJECTS) | previous
            for fmt in news_formats()
            if not FORMAT_SPECS[fmt].renews_subjects
        }

    async def _desk(
        self, local_now: datetime, *, before: int | None = None
    ) -> tuple[Desk, dict[RadioFormat, list[NewsCandidate]]]:
        keys = frozenset(await self._keys())
        stories = frozenset(self._heard_stories)
        gathered = await self._gather(local_now, heard_keys=keys, heard_stories=stories)
        headlines = tuple(self._heard_headlines)
        titles = [candidate.title for candidate in gathered.candidates]
        vectors = await self._read_vectors([*titles, *headlines], local_now)
        # Off the event loop: the meanings are a matrix product, and the desk reads
        # hundreds of stories against two days of headlines. Every input is a copy.
        reading = await asyncio.to_thread(
            read_news_desk,
            gathered.candidates,
            keys=keys,
            stories=stories,
            headlines=headlines,
            vectors=vectors,
            threshold=self._setup.same_event_similarity,
            now=local_now,
            excluded=self._excluded(before),
            interests_first=frozenset(fmt for fmt, turn in self._interests_next.items() if turn),
        )
        shortlists = reading.shortlists
        desk = Desk(
            clock=clock_fact(local_now),
            day=gathered.personal.day,
            corner=gathered.personal.corner,
            done=gathered.personal.done,
            ahead=gathered.personal.ahead,
            # What the grid is offered is the moment's edition; a production reads its slot's.
            edition=journal_edition(local_now),
            news={
                fmt: news_facts(chosen, returning=reading.returning.get(fmt, frozenset()))
                for fmt, chosen in shortlists.items()
            },
            aired=keys | self._flash_keys,
            heard_this_session=frozenset(self._aired_here),
            said=frozenset(self._said),
            news_exhausted=reading.exhausted,
        )
        return desk, shortlists

    async def _read_vectors(self, titles: Iterable[str], now: datetime) -> dict[str, Vector] | None:
        """The meanings of the headlines read this session — None when the listener's
        instance reads none; a copy, so a desk read off the loop never meets a write.

        A headline's meaning is asked for once a session (the port shares it across
        sessions); a blind reading leaves the words to judge and is not asked again
        before the desk is read again — a provider down must not slow every segment.
        """
        threshold = self._setup.same_event_similarity
        if threshold <= 0:
            return None
        # The start builds two desks at once: one reading, the other desk waits for it.
        async with self._reading:
            wanted = sorted({headline_key(title) for title in titles} - {""} - self._vectors.keys())
            blind = self._blind_until is not None and now < self._blind_until
            if wanted and not blind:
                try:
                    self._vectors.update(await self._headlines.vectors(wanted))
                except Exception as exc:  # noqa: BLE001 — the words still judge
                    self._blind_until = now + timedelta(seconds=self._setup.desk_ttl_s)
                    logger.warning(
                        "radio_headline_meanings_unavailable", error_type=type(exc).__name__
                    )
            return dict(self._vectors)

    async def _gather(
        self, now: datetime, *, heard_keys: frozenset[str], heard_stories: frozenset[str]
    ) -> _Gathered:
        async with self._gathering:
            cached = self._gathered
            if cached is not None and (now - cached.at).total_seconds() < self._setup.desk_ttl_s:
                return cached
            personal = await self._read_day()
            candidates = await self._read_news(heard_keys, heard_stories)
            self._gathered = _Gathered(at=now, personal=personal, candidates=tuple(candidates))
            return self._gathered

    async def _read_day(self) -> PersonalFacts:
        try:
            return await self._day.day()
        except Exception as exc:  # noqa: BLE001 — a blind source reads as nothing to say
            logger.warning("radio_day_unavailable", error_type=type(exc).__name__)
            return PersonalFacts()

    async def _read_news(
        self, heard_keys: frozenset[str], heard_stories: frozenset[str]
    ) -> list[NewsCandidate]:
        try:
            return await self._news.candidates(heard_keys=heard_keys, heard_stories=heard_stories)
        except Exception as exc:  # noqa: BLE001 — a blind source reads as nothing to say
            logger.warning("radio_news_unavailable", error_type=type(exc).__name__)
            return []

    async def _keys(self) -> set[str]:
        """This session's memory of what aired, seeded once from the ledger."""
        async with self._gathering:
            if self._heard_keys is None:
                try:
                    keys, stories = await self._aired.heard()
                    headlines = await self._aired.headlines()
                    taken = await self._aired.treated()
                except Exception as exc:  # noqa: BLE001 — the session's own memory still holds
                    logger.warning("radio_aired_ledger_unavailable", error_type=type(exc).__name__)
                    keys, stories, headlines, taken = frozenset(), frozenset(), (), {}
                for fmt, subjects in taken.items():
                    self._taken[fmt] = subjects | self._taken.get(fmt, NO_SUBJECTS)
                self._heard_keys = set(keys)
                self._heard_stories |= stories
                self._heard_headlines = [*headlines, *self._heard_headlines]
                # What the listener heard before this session comes first, oldest first;
                # the bound keeps the most recent (a deque built whole drops from the left).
                earlier = [title for title in headlines if title not in self._on_air]
                self._on_air = deque([*earlier, *self._on_air], maxlen=ON_AIR_SHOWN_MAX)
            return self._heard_keys

    async def _with_analysis(self, desk: Desk, stories: Sequence[NewsCandidate]) -> Desk:
        """The desk with the analyst's reading of the analysis's story (the freshest).

        A reading is paid once per story a session: kept, it serves the story
        again when the production it fed failed after it (a check, a voice) —
        measured 2026-09-26, the same reading was bought six times in twenty
        minutes. A reading that came back empty is asked for again.
        """
        if not stories or not stories[0].full_text:
            return desk
        story = stories[0]
        kept = self._analyses.get(story.key)
        if kept is not None:
            return replace(desk, analysis=kept)
        facts = await self._crew.analyst.analyse(
            AnalysisRequest(
                title=story.title,
                outlet=story.outlet,
                url=story.url,
                published_at=story.published_at,
                article=story.full_text or "",
            ),
            story_key=story.key,
            min_points=self._setup.analysis_min_points,
            max_points=self._setup.analysis_max_points,
        )
        if facts:
            self._analyses[story.key] = facts
        return replace(desk, analysis=facts)

    async def _remember(
        self,
        facts: Sequence[RadioFact],
        shortlists: dict[RadioFormat, list[NewsCandidate]],
        headlines: Sequence[str],
    ) -> Subjects:
        """This session's memory of what a segment will air: it never says it again.

        Returns:
            The stories it told — keys, fingerprints and headlines.
        """
        keys = frozenset(fact.key for fact in facts if fact.kind not in LEDGER_EXEMPT_KINDS)
        self._aired_here |= keys
        self._said |= {fact.kind for fact in facts if fact.kind in LEDGER_EXEMPT_KINDS}
        stories = frozenset(
            candidate.fingerprint
            for chosen in shortlists.values()
            for candidate in chosen
            if candidate.key in keys and candidate.fingerprint
        )
        (await self._keys()).update(keys)
        self._heard_stories |= stories
        news = frozenset(fact.key for fact in facts if fact.kind in STORY_KINDS)
        return Subjects(keys=news, stories=stories, headlines=tuple(headlines))


__all__ = [
    "AiredLedger",
    "Analyst",
    "Antenna",
    "AntennaCrew",
    "AntennaSetup",
    "DaySource",
    "HeadlineVectors",
    "NewsSource",
    "aired_headlines",
    "heard_facts",
    "heard_lines",
]
