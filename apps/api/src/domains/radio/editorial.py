"""The newsroom's shortlist: which stories a news segment may choose from.

The writer is a model; it reads a SHORTLIST, never the newsroom. The shortlist is
decided here, without a model, from what the collector stored:

- only stories the listener has not heard yet — neither the item itself (its key)
  nor the same story told by another outlet (its fingerprint): a story heard from
  one outlet is not news from the next — for a programme that renews its stories
  (the headlines, the bulletin, a brief, the figure); an ANGLE (the analysis, the
  editorial, the dossier, the debate, the discussion) may come back to a story heard,
  from its own angle, but never to the SUBJECTS it must leave out: the story the
  programme just before told and the ones the same programme already took
  (decision 39) — a subject being the story, its fingerprint across outlets, or a
  headline telling the same event;
- only stories young enough for the format (a bulletin is today's news);
- one story per STORY: two outlets covering the same event share a fingerprint,
  and the freshest telling stays (the others would make the writer say it twice);
  an article under a near-identical headline tells it too — and, when the desk
  reads the headlines' meanings (``SameEvent``, decision 34), so does an article
  telling the same event in other words;
- no outlet more than a bounded share of the list, so a prolific feed does not
  become the station's only voice — relaxed only to fill the list when too few
  outlets have something new (one outlet is better than a half-empty bulletin);
- what the format needs: an analysis needs the article's full text, a « number »
  needs a figure to stand on.

Relevance to the listener's interests is NOT scored here: interests are free text
in the listener's language, stories arrive in many languages, and a word match
across the two is noise. The writer sees the interests and the shortlist and
chooses — the shortlist only makes sure it chooses among what is fresh, new and
varied.

The facts built from the chosen candidates carry their outlet and URL, so every
sentence the station says about the world can show where it comes from.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Protocol

from src.domains.radio.constants import FACT_TEXT_MAX_CHARS, SOURCE_LABEL_MAX_CHARS
from src.domains.radio.facts import FactKind, RadioFact, Sensitivity, SourceRef
from src.domains.radio.formats import FORMAT_SPECS, Material, RadioFormat


@dataclass(frozen=True, slots=True)
class _Need:
    """What one news format asks of its shortlist."""

    count: int
    max_age_s: int
    needs_text: bool = False
    needs_figure: bool = False


_NEWS_NEEDS: Final[dict[RadioFormat, _Need]] = {
    RadioFormat.HEADLINES: _Need(count=8, max_age_s=18 * 3600),
    RadioFormat.BULLETIN: _Need(count=10, max_age_s=18 * 3600),
    RadioFormat.BRIEF: _Need(count=5, max_age_s=12 * 3600),
    RadioFormat.ANALYSIS: _Need(count=3, max_age_s=48 * 3600, needs_text=True),
    RadioFormat.DOSSIER: _Need(count=3, max_age_s=48 * 3600, needs_text=True),
    RadioFormat.COLUMN: _Need(count=4, max_age_s=48 * 3600),
    RadioFormat.DEBATE: _Need(count=3, max_age_s=48 * 3600, needs_text=True),
    RadioFormat.DISCUSSION: _Need(count=4, max_age_s=48 * 3600),
    RadioFormat.NUMBER: _Need(count=5, max_age_s=24 * 3600, needs_figure=True),
}

#: The oldest story any news format may air: a desk reads nothing older.
NEWS_MAX_AGE_S: Final[int] = max(need.max_age_s for need in _NEWS_NEEDS.values())

#: The largest share of one shortlist a single outlet may take.
_OUTLET_SHARE_MAX: Final[float] = 0.4

_DIGIT_RE: Final[re.Pattern[str]] = re.compile(r"\d")


@dataclass(frozen=True, slots=True)
class NewsCandidate:
    """A stored story the station may voice.

    Attributes:
        key: Its identity for the aired ledger (never said twice).
        outlet: The outlet's name.
        url: The article.
        title: The headline.
        summary: The feed's summary (may be empty).
        published_at: When it was published (timezone-aware).
        fingerprint: The same story across outlets.
        full_text: The article's text, when the collector could read it.
        from_interests: Whether a search found it for the listener's interests
            rather than a source publishing it (ADR-324 decision 40).
    """

    key: str
    outlet: str
    url: str
    title: str
    summary: str
    published_at: datetime
    fingerprint: str
    full_text: str | None = None
    from_interests: bool = False

    def __post_init__(self) -> None:
        if self.published_at.tzinfo is None:
            raise ValueError("published_at must be timezone-aware")


def news_formats() -> frozenset[RadioFormat]:
    """The formats that voice the newsroom."""
    return frozenset(_NEWS_NEEDS)


def assert_news_needs_complete() -> None:
    """Refuse to import with a news format the shortlist does not know (ADR-085).

    Raises:
        RuntimeError: When the table and the formats' material disagree.
    """
    voiced = {fmt for fmt, spec in FORMAT_SPECS.items() if spec.material is Material.NEWS}
    if set(_NEWS_NEEDS) != voiced:
        raise RuntimeError(
            f"news shortlist needs {sorted(_NEWS_NEEDS)} != news formats {sorted(voiced)}"
        )


#: Two articles of one story under near-identical headlines share most of their words:
#: « … attendus pour la messe géante de Léon XIV à Paris » and « … attendus à la messe de
#: Léon XIV à Paris » share nine of ten (measured on dev 2026-09-27 — the second came back
#: in the next session as the figure of the day, under another key and fingerprint). Two
#: different stories rarely share half; another ANGLE of one event (« the Pope blesses
#: babies ») shares a name or two and is left to the writer, who is shown what was heard.
HEADLINE_OVERLAP_MIN: Final[float] = 0.6
#: And at least this many words shared: a headline of one or two words (a live page named
#: after a country, a language written without spaces) is matched by its fingerprint alone.
HEADLINE_SHARED_MIN: Final[int] = 3

_WORD_RE: Final = re.compile(r"\w+")


def headline_words(title: str) -> frozenset[str]:
    """A headline's words, case folded, the shortest (articles, prepositions) left out.

    A language written without spaces reads as one word per run, so its headlines
    are never matched by words — their fingerprints still are.
    """
    return frozenset(word for word in _WORD_RE.findall(title.casefold()) if len(word) > 2)


def same_headline(first: frozenset[str], second: frozenset[str]) -> bool:
    """Whether two headlines tell one story: most of their words shared (Jaccard), and several."""
    shared = len(first & second)
    if shared < HEADLINE_SHARED_MIN:
        return False
    return shared / len(first | second) >= HEADLINE_OVERLAP_MIN


@dataclass(frozen=True, slots=True)
class Subjects:
    """Stories a programme must leave out: by key, by fingerprint across outlets, and by
    headline (another article telling the same event, by its words or its meaning).

    Attributes:
        keys: The stories' keys.
        stories: Their fingerprints.
        headlines: Their headlines.
    """

    keys: frozenset[str] = frozenset()
    stories: frozenset[str] = frozenset()
    headlines: tuple[str, ...] = ()

    def __or__(self, other: Subjects) -> Subjects:
        return Subjects(
            keys=self.keys | other.keys,
            stories=self.stories | other.stories,
            headlines=(*self.headlines, *other.headlines),
        )


#: Nothing to leave out.
NO_SUBJECTS: Final[Subjects] = Subjects()


class SameEvent(Protocol):
    """Which headlines tell one event, by meaning — read outside this module."""

    def same_event(self, first: str, second: str) -> bool:
        """Whether two headlines tell one event."""
        ...

    def told_among(self, titles: Sequence[str], told: Sequence[str]) -> frozenset[str]:
        """The headlines of ``titles`` that tell the event of one of ``told``, read at once."""
        ...


class _Told:
    """The headlines the listener heard, read against a desk's stories once each.

    A story is compared with a heard headline only when they share at least the
    words :func:`same_headline` requires — an index, never every pair — and its
    meaning with all of them in one slice of the relation: every language fills a
    desk, and pair by pair 300 stories against 300 headlines heard held the event
    loop two seconds (measured 2026-09-27).
    """

    def __init__(
        self, headlines: Sequence[str], titles: Sequence[str], meanings: SameEvent | None
    ) -> None:
        told = [title for title in headlines if title.strip()]
        self._words = [headline_words(title) for title in told]
        self._by_word: dict[str, list[int]] = {}
        for index, words in enumerate(self._words):
            for word in words:
                self._by_word.setdefault(word, []).append(index)
        self._meant = (
            meanings.told_among(titles, told) if meanings is not None and told else frozenset()
        )

    def tells(self, candidate: NewsCandidate) -> bool:
        """Whether a story heard already tells the candidate's: by its words or its meaning."""
        if candidate.title in self._meant:
            return True
        words = headline_words(candidate.title)
        shared = Counter(index for word in words for index in self._by_word.get(word, ()))
        return any(
            count >= HEADLINE_SHARED_MIN and same_headline(words, self._words[index])
            for index, count in shared.items()
        )


def _fits(candidate: NewsCandidate, need: _Need, now: datetime) -> bool:
    age_s = (now - candidate.published_at.astimezone(UTC)).total_seconds()
    if age_s > need.max_age_s:
        return False
    if need.needs_text and not candidate.full_text:
        return False
    text = f"{candidate.title} {candidate.summary}"
    return not need.needs_figure or bool(_DIGIT_RE.search(text))


def everything_heard(
    candidates: Iterable[NewsCandidate],
    *,
    aired_keys: frozenset[str],
    now: datetime,
    aired_stories: frozenset[str] = frozenset(),
    aired_headlines: Sequence[str] = (),
    meanings: SameEvent | None = None,
) -> bool:
    """Whether the newsroom holds stories a programme could air, and every one was heard.

    A story no programme may air any more (past every format's age, say) says nothing
    about what is left: an empty newsroom is not a listener who heard it all.

    Args:
        candidates: The stored stories of the listener's feeds.
        aired_keys: The keys the listener has already heard.
        now: The current instant (timezone-aware).
        aired_stories: The fingerprints of the stories already heard.
        aired_headlines: The headlines of the stories already heard.
        meanings: Which headlines tell one event, when the desk reads them.

    Returns:
        True when the station has no new story to tell.
    """
    now_utc = now.astimezone(UTC)
    airable = [
        candidate
        for candidate in candidates
        if any(_fits(candidate, need, now_utc) for need in _NEWS_NEEDS.values())
    ]
    unheard = [c for c in airable if not _heard(c, aired_keys, aired_stories)]
    told = _Told(aired_headlines, [candidate.title for candidate in unheard], meanings)
    return bool(airable) and all(told.tells(candidate) for candidate in unheard)


def shortlist(
    candidates: Iterable[NewsCandidate],
    fmt: RadioFormat,
    *,
    aired_keys: frozenset[str],
    now: datetime,
    aired_stories: frozenset[str] = frozenset(),
    aired_headlines: Sequence[str] = (),
    meanings: SameEvent | None = None,
    excluded: Subjects = NO_SUBJECTS,
) -> list[NewsCandidate]:
    """The stories a news segment of ``fmt`` may choose from, freshest first.

    Args:
        candidates: The stored stories of the listener's feeds.
        fmt: A news format (see :func:`news_formats`).
        aired_keys: The keys the listener has already heard.
        now: The current instant (timezone-aware).
        aired_stories: The fingerprints of the stories already heard, from
            whichever outlet.
        aired_headlines: The headlines of the stories already heard: an article
            under a near-identical one tells the same story (:func:`same_headline`).
        meanings: Which headlines tell one event, when the desk reads them: an
            article telling a heard or a chosen one in other words is left out.
        excluded: The subjects this programme must leave out, whatever it may
            come back to (an angle: the programme before's, its own former ones).

    Returns:
        At most the format's count, one per story, outlets bounded. What was heard
        is left out only of a programme that renews its stories.

    Raises:
        KeyError: When ``fmt`` does not voice the newsroom.
    """
    need = _NEWS_NEEDS[fmt]
    renews = FORMAT_SPECS[fmt].renews_subjects
    now_utc = now.astimezone(UTC)
    pool = [
        candidate
        for candidate in candidates
        if _fits(candidate, need, now_utc)
        and not _heard(candidate, excluded.keys, excluded.stories)
        and not (renews and _heard(candidate, aired_keys, aired_stories))
    ]
    headlines = (*excluded.headlines, *(aired_headlines if renews else ()))
    told = _Told(headlines, [candidate.title for candidate in pool], meanings)
    fresh = sorted(
        (candidate for candidate in pool if not told.tells(candidate)),
        key=_freshness,
        reverse=True,
    )
    return _pick(fresh, need.count, meanings)


def heard_among(
    candidates: Sequence[NewsCandidate],
    *,
    aired_keys: frozenset[str],
    aired_stories: frozenset[str] = frozenset(),
    aired_headlines: Sequence[str] = (),
    meanings: SameEvent | None = None,
) -> frozenset[str]:
    """The keys of the stories among ``candidates`` the listener already heard — the
    article itself, another outlet's telling, or a headline heard telling it.

    An angle programme comes back to them, and says so (decision 39).
    """
    told = _Told(aired_headlines, [candidate.title for candidate in candidates], meanings)
    return frozenset(
        candidate.key
        for candidate in candidates
        if _heard(candidate, aired_keys, aired_stories) or told.tells(candidate)
    )


def _heard(
    candidate: NewsCandidate, aired_keys: frozenset[str], aired_stories: frozenset[str]
) -> bool:
    return candidate.key in aired_keys or bool(
        candidate.fingerprint and candidate.fingerprint in aired_stories
    )


def _told(
    candidate: NewsCandidate,
    heard: Sequence[tuple[str, frozenset[str]]],
    meanings: SameEvent | None,
) -> bool:
    """Whether one of a few stories tells the candidate's, pair by pair (the list being
    filled; what the listener heard is read by :class:`_Told`)."""
    words = headline_words(candidate.title)
    return any(
        same_headline(words, told_words)
        or (meanings is not None and meanings.same_event(candidate.title, title))
        for title, told_words in heard
    )


def _freshness(candidate: NewsCandidate) -> tuple[datetime, str]:
    return candidate.published_at.astimezone(UTC), candidate.key


def _pick(
    fresh: Sequence[NewsCandidate], limit: int, meanings: SameEvent | None
) -> list[NewsCandidate]:
    """One per story, outlets bounded — relaxed only to fill the list."""
    per_outlet_max = max(1, int(limit * _OUTLET_SHARE_MAX))
    chosen: list[NewsCandidate] = []
    stories: set[str] = set()
    per_outlet: dict[str, int] = {}
    for bounded in (True, False):
        for candidate in fresh:
            story = candidate.fingerprint or candidate.key
            if len(chosen) == limit or story in stories:
                continue
            if bounded and per_outlet.get(candidate.outlet, 0) >= per_outlet_max:
                continue
            told = [(taken.title, headline_words(taken.title)) for taken in chosen]
            if _told(candidate, told, meanings):
                continue  # two articles of one story: the freshest is kept
            chosen.append(candidate)
            stories.add(story)
            per_outlet[candidate.outlet] = per_outlet.get(candidate.outlet, 0) + 1
    return sorted(chosen, key=_freshness, reverse=True)


def _story_text(candidate: NewsCandidate) -> str:
    title = candidate.title.strip()
    if not candidate.summary:
        return title
    joint = " " if title.endswith((".", "!", "?", "…", "。", "！", "？")) else ". "
    return f"{title}{joint}{candidate.summary.strip()}"


def _bounded(text: str) -> str:
    if len(text) <= FACT_TEXT_MAX_CHARS:
        return text
    return text[: FACT_TEXT_MAX_CHARS - 1].rsplit(" ", 1)[0] + "…"


def news_facts(
    chosen: Sequence[NewsCandidate], *, returning: frozenset[str] = frozenset()
) -> tuple[RadioFact, ...]:
    """The facts a segment voices from its shortlist, ``n1`` to ``nN``.

    Args:
        chosen: The shortlist, in its order.
        returning: The keys of the stories the listener already heard, which an
            angle programme comes back to (its writer says so).

    Returns:
        One public fact per story: its headline and summary, with its source.
    """
    return tuple(
        RadioFact(
            id=f"n{index}",
            kind=FactKind.NEWS,
            text=_bounded(_story_text(c)),
            key=c.key,
            sensitivity=Sensitivity.PUBLIC,
            source=SourceRef(
                label=c.outlet[:SOURCE_LABEL_MAX_CHARS],
                url=c.url,
                published_at=c.published_at,
                story_key=c.key,
            ),
            returning=c.key in returning,
        )
        for index, c in enumerate(chosen, start=1)
    )


assert_news_needs_complete()


__all__ = [
    "NEWS_MAX_AGE_S",
    "NO_SUBJECTS",
    "NewsCandidate",
    "SameEvent",
    "Subjects",
    "assert_news_needs_complete",
    "everything_heard",
    "heard_among",
    "news_facts",
    "news_formats",
    "shortlist",
]
