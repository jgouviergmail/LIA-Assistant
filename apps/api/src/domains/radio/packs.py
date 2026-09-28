"""The editor's desk: which facts each segment is given — decided without a model.

For one production the orchestrator gathers the clock, the listener's day and
personal corner (:mod:`~src.domains.radio.personal`), the news shortlist of the
format and, for an analysis, the analyst's points; this module composes the
segment's :class:`FactPack` — or says there is nothing to say, which is what the
grid's « available » set is made of.

- The time is said by the opening and by a programme announced for a clock mark
  (« the nine o'clock news », whose clock fact IS the mark) — and nowhere else: given
  to every programme, the date and the time were heard again and again (reported
  2026-09-26). Without the fact, a line that says them has nothing to cite, and
  the deterministic editor drops it.
- The opening and the sign-off are neutral: the opening the clock and the weather,
  the sign-off nothing at all — nothing about the person, nothing from the news.
- The weather belongs to the moment and never to the ledger, but a session says it
  ONCE: whichever programme said it first, the others are not given it again.
- The person's records speak only in the JOURNAL (ADR-324 decision 41), whose
  edition decides what it is made of, in the order it is told: the morning the day
  ahead and the corner's things to note; the noon what was done, then what is left
  of the day; the evening what was done, the day, the corner and the week ahead. A
  fact the listener has already heard (its key is in the aired ledger) is not
  offered again — except to the evening, whose whole point is to go over the day:
  it goes over what EARLIER sessions said, never over what this one just said.
- A news format is given its shortlist (already fresh, new and varied — see
  :mod:`~src.domains.radio.editorial`); a programme that reads the whole article
  first (the analysis, the dossier, the debate), its one story and the analyst's
  points.

Pure: every input is gathered by the caller.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from src.domains.radio.editorial import NEWS_MAX_AGE_S
from src.domains.radio.facts import (
    FactKind,
    FactPack,
    RadioFact,
    clock_fact,
    everything_heard_fact,
)
from src.domains.radio.formats import FORMAT_SPECS, JournalEdition, RadioFormat
from src.domains.radio.personal import JournalPart

#: Kinds that belong to the moment and never to the aired ledger — the station's
#: own word about the newsroom included.
LEDGER_EXEMPT_KINDS: Final[frozenset[FactKind]] = frozenset(
    {FactKind.CLOCK, FactKind.WEATHER, FactKind.NEWSROOM}
)
#: The moments said once a session and held for a production in flight — never the
#: clock, which goes to the programmes given one (the opening, a clock mark).
SAID_ONCE_KINDS: Final[frozenset[FactKind]] = frozenset({FactKind.WEATHER})
#: Kinds that tell a STORY: remembered as long as a shortlist may offer the story.
STORY_KINDS: Final[frozenset[FactKind]] = frozenset({FactKind.NEWS, FactKind.ANALYSIS})


@dataclass(frozen=True, slots=True)
class Desk:
    """What the orchestrator gathered for one production.

    Attributes:
        clock: The listener's local time, as a fact.
        day: The listener's day ahead (personal facts and the weather).
        corner: The listener's personal corner — the things to note (a meeting's
            decisions, someone to get back to, a kept answer…).
        done: What the listener did today (past appointments, tasks completed,
            reminders fired, tickets closed, LIA's own actions, mail sent) — the
            noon's and the evening's opening (decision 41).
        ahead: Tomorrow and the rest of the week — the evening's close.
        edition: The journal's edition the programme airs in; the antenna reads it
            from the programme's air time.
        news: The shortlist's facts per news format.
        analysis: The analyst's points, for an analysis (after the analyst ran).
        aired: The keys of the facts the listener has already heard (this session
            and the earlier ones the ledger remembers).
        heard_this_session: The keys this session itself aired.
        said: The moment's kinds (the weather) this session already said.
        news_exhausted: The newsroom holds stories a programme could air, and the
            listener heard every one of them (« nothing new », decision 38).
    """

    clock: RadioFact
    day: tuple[RadioFact, ...] = ()
    corner: tuple[RadioFact, ...] = ()
    done: tuple[RadioFact, ...] = ()
    ahead: tuple[RadioFact, ...] = ()
    edition: JournalEdition = JournalEdition.MORNING
    news: Mapping[RadioFormat, tuple[RadioFact, ...]] = field(default_factory=dict)
    analysis: tuple[RadioFact, ...] = ()
    aired: frozenset[str] = frozenset()
    heard_this_session: frozenset[str] = frozenset()
    said: frozenset[FactKind] = frozenset()
    news_exhausted: bool = False

    def of(self, part: JournalPart) -> tuple[RadioFact, ...]:
        """The listener's facts of one part of the journal."""
        return _DESK_PARTS[part](self)


_DESK_PARTS: Final[dict[JournalPart, Callable[[Desk], tuple[RadioFact, ...]]]] = {
    JournalPart.DAY: lambda desk: desk.day,
    JournalPart.CORNER: lambda desk: desk.corner,
    JournalPart.DONE: lambda desk: desk.done,
    JournalPart.AHEAD: lambda desk: desk.ahead,
}

#: What each edition of the journal is made of, in the order it is told (ADR-324 decision
#: 41): the morning the day ahead and the things to note; the noon what was done, then what
#: is left; the evening a look back — what was done, the day, the things to note — then the
#: week ahead. ONE table: the day source reads it to know which parts to read.
EDITION_PARTS: Final[dict[JournalEdition, tuple[JournalPart, ...]]] = {
    JournalEdition.MORNING: (JournalPart.DAY, JournalPart.CORNER),
    JournalEdition.NOON: (JournalPart.DONE, JournalPart.DAY),
    JournalEdition.EVENING: (
        JournalPart.DONE,
        JournalPart.DAY,
        JournalPart.CORNER,
        JournalPart.AHEAD,
    ),
}


def _unheard(
    facts: Sequence[RadioFact], aired: frozenset[str], said: frozenset[FactKind]
) -> list[RadioFact]:
    """The facts not heard yet: a ledger key never aired, a moment's kind never said."""
    return [
        fact
        for fact in facts
        if fact.kind not in said and (fact.kind in LEDGER_EXEMPT_KINDS or fact.key not in aired)
    ]


def _personal(facts: Sequence[RadioFact]) -> bool:
    return any(fact.kind not in LEDGER_EXEMPT_KINDS for fact in facts)


_Selector = Callable[[Desk], list[RadioFact] | None]


def _opening(desk: Desk) -> list[RadioFact] | None:
    day = _unheard(desk.day, desk.aired, desk.said)
    return [fact for fact in day if fact.kind is FactKind.WEATHER]


def _sign_off(_desk: Desk) -> list[RadioFact] | None:
    return []


def _nothing_new(desk: Desk) -> list[RadioFact] | None:
    return [everything_heard_fact(NEWS_MAX_AGE_S // 3600)] if desk.news_exhausted else None


def _flash(_desk: Desk) -> list[RadioFact] | None:
    # A flash brings its own facts — the notifications it breaks in for — and is
    # never offered by the desk, so the grid can never plan one.
    return None


def _journal(desk: Desk) -> list[RadioFact] | None:
    material = [fact for part in EDITION_PARTS[desk.edition] for fact in desk.of(part)]
    # The evening goes over the day: what EARLIER sessions said is told again, what this
    # one said is not; the other editions never repeat what the ledger holds.
    heard = desk.heard_this_session if desk.edition is JournalEdition.EVENING else desk.aired
    facts = _unheard(material, heard, desk.said)
    return facts if _personal(facts) else None


def _analysed(fmt: RadioFormat) -> _Selector:
    """One story and the analyst's points on it — the programme reads the article first."""

    def select(desk: Desk) -> list[RadioFact] | None:
        stories = desk.news.get(fmt, ())
        return [stories[0], *desk.analysis] if stories and desk.analysis else None

    return select


def _news(fmt: RadioFormat) -> _Selector:
    def select(desk: Desk) -> list[RadioFact] | None:
        return list(desk.news.get(fmt, ())) or None

    return select


#: What each format is given (a format without a selector refuses to import).
_SELECTORS: Final[dict[RadioFormat, _Selector]] = {
    RadioFormat.OPENING: _opening,
    RadioFormat.SIGN_OFF: _sign_off,
    RadioFormat.NOTHING_NEW: _nothing_new,
    RadioFormat.FLASH: _flash,
    RadioFormat.JOURNAL: _journal,
    RadioFormat.ANALYSIS: _analysed(RadioFormat.ANALYSIS),
    RadioFormat.DOSSIER: _analysed(RadioFormat.DOSSIER),
    RadioFormat.DEBATE: _analysed(RadioFormat.DEBATE),
    RadioFormat.HEADLINES: _news(RadioFormat.HEADLINES),
    RadioFormat.BULLETIN: _news(RadioFormat.BULLETIN),
    RadioFormat.BRIEF: _news(RadioFormat.BRIEF),
    RadioFormat.COLUMN: _news(RadioFormat.COLUMN),
    RadioFormat.DISCUSSION: _news(RadioFormat.DISCUSSION),
    RadioFormat.NUMBER: _news(RadioFormat.NUMBER),
}


def assert_selectors_complete() -> None:
    """Refuse to import with a format the desk cannot feed, or an edition it cannot fill
    (ADR-085).

    Raises:
        RuntimeError: When a format has no selector, or an edition no material.
    """
    missing = sorted(fmt.value for fmt in RadioFormat if fmt not in _SELECTORS)
    if missing:
        raise RuntimeError(f"the editor's desk has no selector for {missing}")
    editions = sorted(edition.value for edition in JournalEdition if edition not in EDITION_PARTS)
    if editions:
        raise RuntimeError(f"the editor's desk has no material for the journal's {editions}")


def _clock_for(fmt: RadioFormat, desk: Desk, clock_mark: datetime | None) -> list[RadioFact]:
    """The clock a programme may say: the opening's now, a marked programme's mark."""
    if clock_mark is not None:
        return [clock_fact(clock_mark)]
    return [desk.clock] if fmt is RadioFormat.OPENING else []


def pack_for(
    fmt: RadioFormat, desk: Desk, *, clock_mark: datetime | None = None
) -> FactPack | None:
    """The facts a segment of ``fmt`` is given, or ``None`` when it has nothing to say.

    Args:
        fmt: The format to produce.
        desk: What the orchestrator gathered.
        clock_mark: The local instant the programme is announced for, if any.

    Returns:
        The pack (the clock first where one is said), or ``None``.
    """
    facts = _SELECTORS[fmt](desk)
    if facts is None:
        return None
    return FactPack(format=fmt, facts=(*_clock_for(fmt, desk, clock_mark), *facts))


def available_formats(desk: Desk) -> frozenset[RadioFormat]:
    """The formats that have something to say — the grid's ``available`` set.

    A programme that reads the article first is judged on its story alone: the
    analyst runs only once the grid chose it (its points are paid for, the
    shortlist is not).
    """
    return frozenset(
        fmt
        for fmt, spec in FORMAT_SPECS.items()
        if (bool(desk.news.get(fmt)) if spec.needs_analysis else _SELECTORS[fmt](desk) is not None)
    )


assert_selectors_complete()


__all__ = [
    "EDITION_PARTS",
    "LEDGER_EXEMPT_KINDS",
    "SAID_ONCE_KINDS",
    "STORY_KINDS",
    "Desk",
    "assert_selectors_complete",
    "available_formats",
    "pack_for",
]
