"""The news desk's reading: every news format's shortlist, decided without a model.

One pure function over copies — the antenna calls it off the event loop, because the
meanings are a matrix product and the desk reads hundreds of stories against two days
of headlines. It composes the editorial rules (:mod:`~src.domains.radio.editorial`):
which stories are fresh, new and varied for each format, which heard story an angle
comes back to (ADR-324 decision 39), whether the listener heard every story left
(decision 38), and from which material a format draws — the sources, or what a search
found for the listener's interests (decision 40).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from src.domains.radio.editorial import (
    NO_SUBJECTS,
    NewsCandidate,
    Subjects,
    everything_heard,
    heard_among,
    news_formats,
    shortlist,
)
from src.domains.radio.formats import FORMAT_SPECS, RadioFormat
from src.domains.radio.meanings import HeadlineMeanings, Vector


@dataclass(frozen=True, slots=True)
class NewsDeskReading:
    """What the news desk read: every format's shortlist, the stories each one comes back
    to, and whether the listener heard every story."""

    shortlists: dict[RadioFormat, list[NewsCandidate]]
    returning: dict[RadioFormat, frozenset[str]]
    exhausted: bool


def read_news_desk(
    candidates: Sequence[NewsCandidate],
    *,
    keys: frozenset[str],
    stories: frozenset[str],
    headlines: Sequence[str],
    vectors: Mapping[str, Vector] | None,
    threshold: float,
    now: datetime,
    excluded: Mapping[RadioFormat, Subjects],
    interests_first: frozenset[RadioFormat] = frozenset(),
) -> NewsDeskReading:
    """Every news format's shortlist, the heard stories an angle comes back to, and
    whether the listener heard every story.

    A shortlist draws from ONE material: the sources, or what a search found for the
    listener's interests (ADR-324 decision 40) — the one whose turn it is, else the
    other when that one has nothing.

    Pure, on copies: the antenna reads it off the event loop.

    Args:
        candidates: The stories gathered.
        keys: What the listener heard (keys).
        stories: The fingerprints of the stories heard.
        headlines: The headlines heard.
        vectors: The headlines' meanings read, or None when none is read.
        threshold: How close two meanings tell one event.
        now: The listener's local instant.
        excluded: What each format must leave out (an angle: the programme
            before's subjects and its own former ones).
        interests_first: The formats whose turn it is to draw from the interests.

    Returns:
        The desk's reading.
    """
    meanings = HeadlineMeanings.of(vectors, threshold) if vectors is not None else None
    sources = [candidate for candidate in candidates if not candidate.from_interests]
    found = [candidate for candidate in candidates if candidate.from_interests]

    def drawn_from(fmt: RadioFormat) -> list[NewsCandidate]:
        first, then = (found, sources) if fmt in interests_first else (sources, found)
        for pool in (first, then):
            picked = shortlist(
                pool,
                fmt,
                aired_keys=keys,
                now=now,
                aired_stories=stories,
                aired_headlines=headlines,
                meanings=meanings,
                excluded=excluded.get(fmt, NO_SUBJECTS),
            )
            if picked:
                return picked
        return []

    shortlists = {fmt: drawn_from(fmt) for fmt in news_formats()}
    returning = {
        fmt: heard_among(
            chosen,
            aired_keys=keys,
            aired_stories=stories,
            aired_headlines=headlines,
            meanings=meanings,
        )
        for fmt, chosen in shortlists.items()
        if not FORMAT_SPECS[fmt].renews_subjects
    }
    exhausted = everything_heard(
        candidates,
        aired_keys=keys,
        now=now,
        aired_stories=stories,
        aired_headlines=headlines,
        meanings=meanings,
    )
    return NewsDeskReading(shortlists=shortlists, returning=returning, exhausted=exhausted)


__all__ = ["NewsDeskReading", "read_news_desk"]
