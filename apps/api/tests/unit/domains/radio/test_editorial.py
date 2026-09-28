"""The shortlist: fresh, new to the listener, one telling per story, many outlets."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from src.domains.radio import editorial
from src.domains.radio.editorial import (
    NO_SUBJECTS,
    NewsCandidate,
    SameEvent,
    Subjects,
    everything_heard,
    headline_words,
    heard_among,
    news_facts,
    news_formats,
    same_headline,
    shortlist,
)
from src.domains.radio.formats import FORMAT_SPECS, Material, RadioFormat
from src.domains.radio.meanings import HeadlineMeanings

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)


def story(
    key: str,
    outlet: str = "Outlet A",
    hours_ago: float = 1.0,
    *,
    title: str | None = None,
    summary: str | None = None,
    fingerprint: str | None = None,
) -> NewsCandidate:
    return NewsCandidate(
        key=key,
        outlet=outlet,
        url=f"https://news.example.org/{key}",
        title=f"Headline {key}" if title is None else title,
        summary=f"Summary {key}" if summary is None else summary,
        published_at=NOW - timedelta(hours=hours_ago),
        fingerprint=f"story {key}" if fingerprint is None else fingerprint,
    )


def test_every_news_format_has_a_shortlist_rule() -> None:
    voiced = {fmt for fmt, spec in FORMAT_SPECS.items() if spec.material is Material.NEWS}
    assert news_formats() == voiced


def test_the_freshest_new_stories_come_first() -> None:
    stories = [story("a", "A", 5), story("b", "B", 1), story("c", "C", 3)]
    chosen = shortlist(stories, RadioFormat.BRIEF, aired_keys=frozenset(), now=NOW)
    assert [c.key for c in chosen] == ["b", "c", "a"]


def test_a_story_already_heard_is_never_offered_again() -> None:
    chosen = shortlist(
        [story("a", "A"), story("b", "B")], RadioFormat.BRIEF, aired_keys=frozenset({"b"}), now=NOW
    )
    assert [c.key for c in chosen] == ["a"]


def test_a_story_heard_from_one_outlet_is_not_news_from_the_next() -> None:
    same = [story("b", "B", 1, fingerprint="budget adopted"), story("c", "C", 2)]
    chosen = shortlist(
        same,
        RadioFormat.BRIEF,
        aired_keys=frozenset({"a"}),
        aired_stories=frozenset({"budget adopted"}),
        now=NOW,
    )
    assert [c.key for c in chosen] == ["c"]


# Headlines measured on dev 2026-09-27 (France 24): the second article of the mass came
# back in the next session as the figure of the day, under another key and fingerprint.
MASS = "Près de 600 000 fidèles attendus pour la messe géante de Léon XIV à Paris"
MASS_AGAIN = "Près de 600 000 fidèles attendus à la messe de Léon XIV à Paris"
BABIES = "Le pape Léon XIV bénit des bébés sur les Champs-Élysées"


def test_an_article_telling_a_story_heard_under_a_near_identical_headline_is_not_offered() -> None:
    chosen = shortlist(
        [
            story("again", title=MASS_AGAIN),
            story("other", title="Le Liban abolit la peine de mort"),
        ],
        RadioFormat.BRIEF,
        aired_keys=frozenset(),
        aired_headlines=(MASS,),
        now=NOW,
    )
    assert [c.key for c in chosen] == ["other"]


def test_two_articles_of_one_story_are_offered_once() -> None:
    chosen = shortlist(
        [story("first", "A", 1, title=MASS), story("second", "A", 2, title=MASS_AGAIN)],
        RadioFormat.HEADLINES,
        aired_keys=frozenset(),
        now=NOW,
    )
    assert [c.key for c in chosen] == ["first"]


def test_another_angle_of_an_event_is_left_to_the_writer() -> None:
    """A word match cannot tell an angle from an event: the writer is shown what was heard."""
    chosen = shortlist(
        [story("babies", title=BABIES)],
        RadioFormat.BRIEF,
        aired_keys=frozenset(),
        aired_headlines=(MASS,),
        now=NOW,
    )
    assert [c.key for c in chosen] == ["babies"]


# One match, two France 24 articles (dev, 2026-09-27): two words in common, no word rule
# joins them — their meanings, 0.916 apart, do.
SPAIN = "Ligue des nations : l'Espagne renverse l'Angleterre à Wembley grâce à ses remplaçants"
SPAIN_AGAIN = "L'Espagne continue sur sa lancée en renversant l'Angleterre à Londres"


def at(degrees: float) -> tuple[float, float]:
    return (math.cos(math.radians(degrees)), math.sin(math.radians(degrees)))


MEANINGS = HeadlineMeanings.of(
    {SPAIN: at(0), SPAIN_AGAIN: at(20), MASS: at(90), BABIES: at(130)}, threshold=0.9
)


class TestMeanings:
    def test_a_story_heard_in_other_words_is_not_offered_again(self) -> None:
        assert not same_headline(headline_words(SPAIN), headline_words(SPAIN_AGAIN))
        chosen = shortlist(
            [story("again", title=SPAIN_AGAIN), story("other", title="Le Liban vote")],
            RadioFormat.BRIEF,
            aired_keys=frozenset(),
            aired_headlines=(SPAIN,),
            now=NOW,
            meanings=MEANINGS,
        )
        assert [c.key for c in chosen] == ["other"]

    def test_two_articles_of_one_event_in_other_words_are_offered_once(self) -> None:
        chosen = shortlist(
            [story("older", "A", 3, title=SPAIN_AGAIN), story("fresh", "B", 1, title=SPAIN)],
            RadioFormat.HEADLINES,
            aired_keys=frozenset(),
            now=NOW,
            meanings=MEANINGS,
        )
        assert [c.key for c in chosen] == ["fresh"]

    def test_another_moment_of_an_event_is_still_news(self) -> None:
        chosen = shortlist(
            [story("babies", title=BABIES)],
            RadioFormat.BRIEF,
            aired_keys=frozenset(),
            aired_headlines=(MASS,),
            now=NOW,
            meanings=MEANINGS,
        )
        assert [c.key for c in chosen] == ["babies"]

    def test_without_meanings_the_words_alone_judge(self) -> None:
        chosen = shortlist(
            [story("again", title=SPAIN_AGAIN)],
            RadioFormat.BRIEF,
            aired_keys=frozenset(),
            aired_headlines=(SPAIN,),
            now=NOW,
        )
        assert [c.key for c in chosen] == ["again"]


def test_a_headline_is_compared_by_its_words_not_its_articles() -> None:
    """« le », « de », « à » would make any two French headlines half the same."""
    assert headline_words("Le vote de la loi à Paris") == {"vote", "loi", "paris"}


@pytest.mark.parametrize(
    ("first", "second", "same"),
    [
        (MASS, MASS_AGAIN, True),
        (MASS, BABIES, False),
        ("Spain beat England at Wembley", "Spain beat England at Wembley", True),
        ("Spain beat England at Wembley", "Kenya and Eritrea draw", False),
        # Written without spaces: one word each, left to the fingerprint (equal titles).
        ("台风登陆广东", "台风登陆广东", False),
        ("Ukraine", "Ukraine", False),  # one word: a live page, not a story
        ("", "", False),  # nothing to compare is never the same story
    ],
)
def test_one_story_under_two_headlines(first: str, second: str, same: bool) -> None:
    assert same_headline(headline_words(first), headline_words(second)) is same


def test_a_naive_publication_date_is_refused() -> None:
    with pytest.raises(ValueError):
        NewsCandidate(
            key="k",
            outlet="O",
            url="https://news.example.org/k",
            title="T",
            summary="",
            published_at=datetime(2026, 9, 26, 8, 0),
            fingerprint="t",
        )


def test_a_story_too_old_for_the_format_is_left_out() -> None:
    stale = story("old", hours_ago=20)
    assert shortlist([stale], RadioFormat.BULLETIN, aired_keys=frozenset(), now=NOW) == []
    assert shortlist([stale], RadioFormat.ANALYSIS, aired_keys=frozenset(), now=NOW) == []
    with_text = replace(stale, full_text="The whole article.")
    assert shortlist([with_text], RadioFormat.ANALYSIS, aired_keys=frozenset(), now=NOW)


def test_two_tellings_of_one_story_are_one_candidate() -> None:
    same = [
        story("a", "A", 2, fingerprint="budget adopted"),
        story("b", "B", 1, fingerprint="budget adopted"),
    ]
    chosen = shortlist(same, RadioFormat.HEADLINES, aired_keys=frozenset(), now=NOW)
    assert [c.key for c in chosen] == ["b"]


def test_one_prolific_outlet_does_not_take_the_bulletin() -> None:
    flood = [story(f"a{i}", "Prolific", 0.1 * (i + 1)) for i in range(10)]
    others = [story("b", "B", 5), story("c", "C", 6)]
    chosen = shortlist(flood + others, RadioFormat.BULLETIN, aired_keys=frozenset(), now=NOW)
    assert {c.key for c in chosen} >= {"b", "c"}
    assert len(chosen) == 10  # the cap relaxes to fill, it never empties


def test_a_single_outlet_still_fills_its_headlines() -> None:
    only = [story(f"a{i}", "Only", 0.1 * (i + 1)) for i in range(8)]
    chosen = shortlist(only, RadioFormat.HEADLINES, aired_keys=frozenset(), now=NOW)
    assert len(chosen) == 8


def test_an_analysis_needs_the_article_and_a_number_needs_a_figure() -> None:
    plain = story("a")
    assert shortlist([plain], RadioFormat.ANALYSIS, aired_keys=frozenset(), now=NOW) == []
    assert shortlist([plain], RadioFormat.NUMBER, aired_keys=frozenset(), now=NOW) == []
    figure = replace(plain, key="f", title="Unemployment falls to 7.1%")
    assert shortlist([figure], RadioFormat.NUMBER, aired_keys=frozenset(), now=NOW)


def test_the_facts_carry_their_source_and_join_headline_and_summary() -> None:
    chosen = [
        story("a", title="Budget adopted", summary="By 312 votes."),
        story("b", title="Is it over?", summary="Not yet."),
        story("c", summary=""),
    ]
    facts = news_facts(chosen)
    assert [f.id for f in facts] == ["n1", "n2", "n3"]
    assert facts[0].text == "Budget adopted. By 312 votes."
    assert facts[1].text == "Is it over? Not yet."
    assert facts[2].text == "Headline c"
    assert facts[0].source is not None and facts[0].source.url == "https://news.example.org/a"
    assert facts[0].key == "a"
    # The source names the story: the radio page opens its article from it.
    assert [f.source.story_key if f.source else None for f in facts] == ["a", "b", "c"]


class TestEverythingHeard:
    """ADR-324 decision 38: the station says so when the listener heard it all."""

    def test_a_desk_whose_every_airable_story_was_heard_is_exhausted(self) -> None:
        stories = [story("a", "A"), story("b", "B", fingerprint="the vote"), story("old", "C", 60)]
        # « a » by its key, « b » by its fingerprint from another outlet; « old » is past
        # every format's age and says nothing about what is left to hear.
        assert everything_heard(
            stories, aired_keys=frozenset({"a"}), aired_stories=frozenset({"the vote"}), now=NOW
        )

    def test_one_story_never_heard_is_news_left(self) -> None:
        assert not everything_heard(
            [story("a", "A"), story("b", "B")], aired_keys=frozenset({"a"}), now=NOW
        )

    def test_an_empty_newsroom_is_not_a_listener_who_heard_it_all(self) -> None:
        assert not everything_heard([], aired_keys=frozenset(), now=NOW)
        assert not everything_heard([story("old", "C", 60)], aired_keys=frozenset(), now=NOW)

    def test_a_story_told_under_a_heard_headline_counts_as_heard(self) -> None:
        told = story("c", "C", title="Budget adopted after a night of debate")
        assert everything_heard(
            [told],
            aired_keys=frozenset(),
            aired_headlines=("Budget adopted after a night of debate",),
            now=NOW,
        )


def told_pair_by_pair(
    candidate: NewsCandidate, headlines: Sequence[str], meanings: SameEvent | None
) -> bool:
    """The definition the desk implements, one pair at a time (the oracle)."""
    words = headline_words(candidate.title)
    return any(
        same_headline(words, headline_words(title))
        or (meanings is not None and meanings.same_event(candidate.title, title))
        for title in headlines
        if title.strip()
    )


class TestAtTheScaleOfEveryLanguage:
    """Every language fills the desk: hundreds of stories against the headlines of two
    days heard. What was told is read once per story — by the heard headlines it shares
    words with, and one slice of the meanings — never pair by pair (measured 2026-09-27:
    300 stories against 300 headlines held the event loop two seconds per desk)."""

    WORDS = [f"{syllable}{index}" for syllable in ("vote", "storm", "match") for index in range(9)]

    def corpus(self, seed: int) -> tuple[list[NewsCandidate], list[str], HeadlineMeanings]:
        rng = random.Random(seed)

        def headline() -> str:
            return " ".join(rng.sample(self.WORDS, rng.randint(4, 7)))

        heard = [headline() for _ in range(60)] + ["   "]
        stories = [
            story(f"s{index}", f"Outlet {index % 7}", rng.uniform(0.1, 11.0), title=headline())
            for index in range(150)
        ]
        # Some stories retell a heard headline word for word, others in other words.
        stories += [
            story(f"r{index}", "Outlet R", 2.0, title=heard[index]) for index in range(0, 20, 4)
        ]
        vectors = {title: at(rng.uniform(0, 360)) for title in heard if title.strip()}
        vectors.update({candidate.title: at(rng.uniform(0, 360)) for candidate in stories})
        return stories, heard, HeadlineMeanings.of(vectors, threshold=0.999)

    @pytest.mark.parametrize("seed", [1, 2, 3])
    def test_the_desk_decides_exactly_what_every_pair_decides(self, seed: int) -> None:
        stories, heard, meanings = self.corpus(seed)
        aired = frozenset({"s3", "s8"})
        prints = frozenset({"story s5"})
        told = [c for c in stories if told_pair_by_pair(c, heard, meanings)]
        assert told, "the corpus must exercise the relation"
        untold = [c for c in stories if c not in told]
        for fmt in news_formats():
            decided = shortlist(
                stories,
                fmt,
                aired_keys=aired,
                aired_stories=prints,
                aired_headlines=heard,
                now=NOW,
                meanings=meanings,
            )
            if FORMAT_SPECS[fmt].renews_subjects:
                expected = shortlist(
                    untold, fmt, aired_keys=aired, aired_stories=prints, now=NOW, meanings=meanings
                )
            else:  # an angle may come back to what was heard: it is not left out
                expected = shortlist(
                    stories, fmt, aired_keys=frozenset(), now=NOW, meanings=meanings
                )
            assert decided == expected, fmt
        assert not everything_heard(
            stories, aired_keys=aired, aired_headlines=heard, now=NOW, meanings=meanings
        )
        assert everything_heard(
            told, aired_keys=aired, aired_headlines=heard, now=NOW, meanings=meanings
        )

    def test_a_story_is_compared_only_with_the_headlines_it_shares_words_with(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        compared = {"words": 0, "meanings": 0}
        real = editorial.same_headline

        def counted(first: frozenset[str], second: frozenset[str]) -> bool:
            compared["words"] += 1
            return real(first, second)

        class Counted:
            def __init__(self, inner: HeadlineMeanings) -> None:
                self.inner = inner

            def same_event(self, first: str, second: str) -> bool:
                compared["meanings"] += 1
                return self.inner.same_event(first, second)

            def told_among(self, titles: Sequence[str], told: Sequence[str]) -> frozenset[str]:
                return self.inner.told_among(titles, told)

        monkeypatch.setattr(editorial, "same_headline", counted)
        stories = [
            story(f"s{i}", f"Outlet {i}", 1.0, title=f"a{i} b{i} c{i} d{i}") for i in range(300)
        ]
        heard = [f"w{i} x{i} y{i} z{i}" for i in range(300)]
        vectors = {title: at(index) for index, title in enumerate(heard)}
        vectors.update(
            {candidate.title: at(index + 0.5) for index, candidate in enumerate(stories)}
        )
        meanings = Counted(HeadlineMeanings.of(vectors, threshold=0.99999))

        chosen = shortlist(
            stories,
            RadioFormat.BULLETIN,
            aired_keys=frozenset(),
            aired_headlines=heard,
            now=NOW,
            meanings=meanings,
        )

        assert len(chosen) == 10
        # Pair by pair: 90 000 comparisons of each kind. Now only the list being filled
        # compares its stories with each other.
        assert compared["words"] < 100
        assert compared["meanings"] < 100


class TestAngles:
    """ADR-324 decision 39: an angle programme may come back to a story heard — never the
    story the programme just before told, never one the same programme already took."""

    def test_an_angle_may_come_back_to_a_story_heard(self) -> None:
        stories = [story("a", "A", 2), story("b", "B", 3, fingerprint="the vote")]
        chosen = shortlist(
            stories,
            RadioFormat.COLUMN,
            aired_keys=frozenset({"a"}),
            aired_stories=frozenset({"the vote"}),
            aired_headlines=("Headline a",),
            now=NOW,
        )
        assert [c.key for c in chosen] == ["a", "b"]

    def test_a_fresh_programme_never_does(self) -> None:
        chosen = shortlist(
            [story("a", "A", 2), story("b", "B", 3)],
            RadioFormat.BRIEF,
            aired_keys=frozenset({"a"}),
            now=NOW,
        )
        assert [c.key for c in chosen] == ["b"]

    def test_never_a_subject_it_must_leave_out_by_key_story_or_headline(self) -> None:
        excluded = Subjects(
            keys=frozenset({"a"}), stories=frozenset({"the vote"}), headlines=(MASS,)
        )
        stories = [
            story("a", "A", 1),
            story("b", "B", 2, fingerprint="the vote"),
            story("again", "C", 3, title=MASS_AGAIN),
            story("new", "D", 4),
        ]
        for fmt in (RadioFormat.COLUMN, RadioFormat.DISCUSSION, RadioFormat.BRIEF):
            chosen = shortlist(stories, fmt, aired_keys=frozenset(), now=NOW, excluded=excluded)
            assert [c.key for c in chosen] == ["new"], fmt

    def test_nor_one_telling_it_in_other_words(self) -> None:
        chosen = shortlist(
            [story("again", title=SPAIN_AGAIN), story("other", "B", title="Le Liban vote")],
            RadioFormat.COLUMN,
            aired_keys=frozenset(),
            now=NOW,
            meanings=MEANINGS,
            excluded=Subjects(headlines=(SPAIN,)),
        )
        assert [c.key for c in chosen] == ["other"]

    def test_nothing_to_leave_out_is_the_default(self) -> None:
        assert NO_SUBJECTS == Subjects()
        assert shortlist([story("a")], RadioFormat.COLUMN, aired_keys=frozenset(), now=NOW)

    def test_a_dossier_and_a_debate_need_the_whole_article(self) -> None:
        bare, whole = story("bare", "A", 1), replace(story("whole", "B", 2), full_text="Text.")
        for fmt in (RadioFormat.DOSSIER, RadioFormat.DEBATE):
            chosen = shortlist([bare, whole], fmt, aired_keys=frozenset(), now=NOW)
            assert [c.key for c in chosen] == ["whole"], fmt
        chosen = shortlist([bare, whole], RadioFormat.DISCUSSION, aired_keys=frozenset(), now=NOW)
        assert [c.key for c in chosen] == ["bare", "whole"]

    def test_the_stories_heard_among_a_list_by_key_story_headline_or_meaning(self) -> None:
        chosen = [
            story("a"),
            story("b", "B", fingerprint="the vote"),
            story("c", "C", title=MASS_AGAIN),
            story("d", "D", title=SPAIN_AGAIN),
            story("new", "E"),
        ]
        heard = heard_among(
            chosen,
            aired_keys=frozenset({"a"}),
            aired_stories=frozenset({"the vote"}),
            aired_headlines=(MASS, SPAIN),
            meanings=MEANINGS,
        )
        assert heard == frozenset({"a", "b", "c", "d"})
        assert heard_among(chosen, aired_keys=frozenset(), meanings=None) == frozenset()
