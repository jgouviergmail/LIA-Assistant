"""A listener's interests as stories (ADR-324 decision 40): searched, normalised like a feed
item, filed once while fresh, every search a consultation of the listener's own key."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from src.domains.radio.interests import (
    InterestStory,
    interest_story,
    refresh_interest_stories,
)
from src.domains.radio.newsroom.parse import SUMMARY_MAX_CHARS, TITLE_MAX_CHARS

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
MAX_AGE_S = 48 * 3600


class TestAStoryAsTheNewsroomWouldHaveFiledIt:
    def test_a_web_article_keeps_its_title_its_outlet_and_its_date(self) -> None:
        story = interest_story(
            url="https://www.Outlet.example/a?utm_source=x&id=7",
            title="  A <b>title</b>  ",
            summary="What it <i>reports</i> today.",
            outlet="The Outlet",
            published_at=NOW - timedelta(hours=3),
            found_at=NOW,
        )
        assert story is not None
        assert story.url == "https://www.outlet.example/a?id=7"  # the feed items' canonical form
        assert (story.title, story.summary, story.outlet) == (
            "A title",
            "What it reports today.",
            "The Outlet",
        )
        assert story.published_at == NOW - timedelta(hours=3)
        assert story.fingerprint == "a title"
        assert len(story.item_key) == 40

    def test_what_is_not_a_web_article_is_no_story(self) -> None:
        for url in ("ftp://outlet.example/a", "javascript:alert(1)", "", "https://"):
            assert (
                interest_story(
                    url=url, title="T", summary="", outlet="O", published_at=None, found_at=NOW
                )
                is None
            )
        assert (
            interest_story(
                url="https://outlet.example/a",
                title=" <p></p> ",
                summary="",
                outlet="O",
                published_at=None,
                found_at=NOW,
            )
            is None
        )

    def test_a_date_never_later_than_when_it_was_found_and_found_when_unknown(self) -> None:
        later = interest_story(
            url="https://o.example/a",
            title="T",
            summary="",
            outlet="O",
            published_at=NOW + timedelta(days=1),
            found_at=NOW,
        )
        unknown = interest_story(
            url="https://o.example/b",
            title="T",
            summary="",
            outlet="O",
            published_at=None,
            found_at=NOW,
        )
        assert later is not None and later.published_at == NOW
        assert unknown is not None and unknown.published_at == NOW

    def test_an_unnamed_outlet_is_its_site_and_the_text_is_bounded(self) -> None:
        story = interest_story(
            url="https://www.site.example/a",
            title="T" * (TITLE_MAX_CHARS + 50),
            summary="S" * (SUMMARY_MAX_CHARS + 50),
            outlet="   ",
            published_at=None,
            found_at=NOW,
        )
        assert story is not None
        assert story.outlet == "site.example"
        assert len(story.title) <= TITLE_MAX_CHARS and len(story.summary) <= SUMMARY_MAX_CHARS

    def test_a_summary_repeating_the_title_is_none(self) -> None:
        story = interest_story(
            url="https://o.example/a",
            title="Same",
            summary="Same",
            outlet="O",
            published_at=None,
            found_at=NOW,
        )
        assert story is not None and story.summary == ""


def found(title: str) -> InterestStory:
    story = interest_story(
        url=f"https://o.example/{title}",
        title=title,
        summary="",
        outlet="O",
        published_at=None,
        found_at=NOW,
    )
    assert story is not None
    return story


@dataclass
class Search:
    section: str = "brave"
    fails: set[str] = field(default_factory=set)
    asked: list[tuple[str, str]] = field(default_factory=list)

    async def search(self, topic: str, *, language: str, found_at: datetime) -> list[InterestStory]:
        self.asked.append((topic, language))
        if topic in self.fails:
            raise ConnectionError("down")
        return [found(f"{topic}-1"), found(f"{topic}-2")]


@dataclass
class Marks:
    fresh_topics: set[str] = field(default_factory=set)
    marked: list[str] = field(default_factory=list)

    async def fresh(self, topic: str) -> bool:
        return topic in self.fresh_topics

    async def mark(self, topic: str) -> None:
        self.marked.append(topic)


@dataclass
class Filed:
    stories: list[InterestStory] = field(default_factory=list)

    async def __call__(self, stories: Sequence[InterestStory]) -> int:
        self.stories.extend(stories)
        return len(stories)


@dataclass
class Recorded:
    reads: list[tuple[frozenset[str], frozenset[str]]] = field(default_factory=list)

    def __call__(self, *, opened: frozenset[str], failed: frozenset[str], duration_ms: int) -> None:
        assert duration_ms >= 0
        self.reads.append((opened, failed))


class TestRefreshing:
    async def test_the_strongest_topics_are_searched_and_their_stories_filed(self) -> None:
        search, marks, filed, recorded = Search(), Marks(), Filed(), Recorded()
        count = await refresh_interest_stories(
            ["jazz", "chess", "sailing", "cycling"],
            search=search,
            marks=marks,
            file=filed,
            record=recorded,
            language="fr",
            now=NOW,
            topics_max=3,
            max_age_s=MAX_AGE_S,
        )
        assert [topic for topic, _ in search.asked] == ["jazz", "chess", "sailing"]
        assert {language for _, language in search.asked} == {"fr"}
        assert count == 6 and len(filed.stories) == 6
        assert marks.marked == ["jazz", "chess", "sailing"]
        assert recorded.reads == [(frozenset({"brave"}), frozenset())] * 3

    async def test_a_fresh_search_is_reused(self) -> None:
        search, marks = Search(), Marks(fresh_topics={"jazz"})
        await refresh_interest_stories(
            ["jazz", "chess"],
            search=search,
            marks=marks,
            file=Filed(),
            record=Recorded(),
            language="fr",
            now=NOW,
            topics_max=3,
            max_age_s=MAX_AGE_S,
        )
        assert [topic for topic, _ in search.asked] == ["chess"]

    async def test_a_failed_search_is_recorded_failed_never_marked_and_the_others_go_on(
        self,
    ) -> None:
        search, marks, filed, recorded = Search(fails={"jazz"}), Marks(), Filed(), Recorded()
        count = await refresh_interest_stories(
            ["jazz", "chess"],
            search=search,
            marks=marks,
            file=filed,
            record=recorded,
            language="fr",
            now=NOW,
            topics_max=3,
            max_age_s=MAX_AGE_S,
        )
        assert count == 2
        assert marks.marked == ["chess"]  # tried again next time
        assert recorded.reads == [
            (frozenset(), frozenset({"brave"})),
            (frozenset({"brave"}), frozenset()),
        ]

    async def test_a_story_too_old_for_any_programme_is_never_filed(self) -> None:
        old = interest_story(
            url="https://o.example/old",
            title="Old",
            summary="",
            outlet="O",
            published_at=NOW - timedelta(seconds=MAX_AGE_S + 1),
            found_at=NOW,
        )
        fresh = interest_story(
            url="https://o.example/fresh",
            title="Fresh",
            summary="",
            outlet="O",
            published_at=NOW - timedelta(seconds=MAX_AGE_S - 60),
            found_at=NOW,
        )
        assert old is not None and fresh is not None

        class Mixed(Search):
            async def search(
                self, topic: str, *, language: str, found_at: datetime
            ) -> list[InterestStory]:
                return [old, fresh]

        filed = Filed()
        count = await refresh_interest_stories(
            ["jazz"],
            search=Mixed(),
            marks=Marks(),
            file=filed,
            record=Recorded(),
            language="fr",
            now=NOW,
            topics_max=3,
            max_age_s=MAX_AGE_S,
        )
        assert count == 1 and [story.title for story in filed.stories] == ["Fresh"]

    async def test_an_empty_or_blank_topic_is_never_searched(self) -> None:
        search = Search()
        await refresh_interest_stories(
            ["  ", "", "jazz"],
            search=search,
            marks=Marks(),
            file=Filed(),
            record=Recorded(),
            language="fr",
            now=NOW,
            topics_max=3,
            max_age_s=MAX_AGE_S,
        )
        assert [topic for topic, _ in search.asked] == ["jazz"]
