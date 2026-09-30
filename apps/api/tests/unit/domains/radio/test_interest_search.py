"""The listener's own searches for their interests (ADR-324 decision 40): their Brave key
first, else their Perplexity key, else none — and what a search found remembered as fresh."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.connectors.models import ConnectorType
from src.domains.radio import interest_search as module
from src.domains.radio.interest_search import (
    BraveInterestSearch,
    PerplexityInterestSearch,
    RedisSearchMarks,
    listener_interest_search,
    refresh_listener_interests,
)
from src.domains.radio.interests import InterestStory, interest_story
from tests.unit.domains.radio.fakes import FakeRedis

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
USER = uuid4()


class FakeBrave:
    made: list[FakeBrave] = []
    answer: dict[str, Any] | None = None

    def __init__(self, api_key: str, language: str | None = None, user_id: Any = None) -> None:
        self.api_key, self.language, self.user_id = api_key, language, user_id
        self.asked: list[dict[str, Any]] = []
        self.closed = False
        FakeBrave.made.append(self)

    async def search(self, **kwargs: Any) -> dict[str, Any] | None:
        self.asked.append(kwargs)
        return FakeBrave.answer

    async def close(self) -> None:
        self.closed = True


class FakePerplexity:
    made: list[FakePerplexity] = []
    answer: dict[str, Any] = {}

    def __init__(self, api_key: str, user_id: Any = None) -> None:
        self.api_key, self.user_id = api_key, user_id
        self.asked: list[dict[str, Any]] = []
        self.closed = False
        FakePerplexity.made.append(self)

    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        self.asked.append({"query": query, **kwargs})
        return FakePerplexity.answer

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def fake_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeBrave.made, FakePerplexity.made = [], []
    monkeypatch.setattr(module, "BraveSearchClient", FakeBrave)
    monkeypatch.setattr(module, "PerplexityClient", FakePerplexity)


class TestBrave:
    async def test_the_news_it_found_within_the_desk_s_days_become_stories(self) -> None:
        FakeBrave.answer = {
            "results": [
                {
                    "title": "A <strong>match</strong>",
                    "url": "https://www.outlet.example/a",
                    "description": "What happened.",
                    "page_age": "2026-09-28T06:30:00",
                    "profile": {"name": "The Outlet"},
                },
                {
                    "title": "B",
                    "url": "https://site.example/b",
                    "meta_url": {"hostname": "site.example"},
                },
                {"title": "", "url": "https://empty.example/c"},
                "not an object",
            ]
        }
        search = BraveInterestSearch("key", USER, stories_max=4)
        stories = await search.search("chess", language="fr", found_at=NOW)
        [client] = FakeBrave.made
        assert (client.api_key, client.language, client.user_id) == ("key", "fr", USER)
        # The days the desk may still air (48 hours), never the week: a result older than
        # any programme may air is dropped unfiled, so buying it bought nothing.
        assert client.asked == [
            {
                "query": "chess",
                "endpoint": "news",
                "count": 4,
                "freshness": "2026-09-26to2026-09-28",
            }
        ]
        assert client.closed
        assert [(s.title, s.outlet, s.summary) for s in stories] == [
            ("A match", "The Outlet", "What happened."),
            ("B", "site.example", ""),
        ]
        assert stories[0].published_at == datetime(2026, 9, 28, 6, 30, tzinfo=UTC)
        assert stories[1].published_at == NOW  # no date: when it was found
        assert search.section == "brave"

    async def test_a_search_brave_could_not_answer_is_a_failure_never_nothing_found(
        self,
    ) -> None:
        FakeBrave.answer = None  # the client answers None on every error
        with pytest.raises(ConnectionError):
            await BraveInterestSearch("key", USER, stories_max=4).search(
                "chess", language="fr", found_at=NOW
            )
        assert FakeBrave.made[0].closed

    async def test_a_search_that_found_nothing_is_an_empty_success(self) -> None:
        FakeBrave.answer = {"results": []}
        assert (
            await BraveInterestSearch("key", USER, stories_max=4).search(
                "chess", language="fr", found_at=NOW
            )
            == []
        )


class TestPerplexity:
    async def test_the_articles_it_listed_this_week_become_stories(self) -> None:
        FakePerplexity.answer = {
            "answer": "…",
            "search_results": [
                {"title": "A", "url": "https://a.example/x", "date": "2026-09-27"},
                {"title": "B", "url": "https://b.example/y", "snippet": "What B says."},
                {"title": "C", "url": "https://c.example/z", "date": "not a date"},
            ],
        }
        search = PerplexityInterestSearch("key", USER, stories_max=2)
        stories = await search.search("chess", language="fr", found_at=NOW)
        [client] = FakePerplexity.made
        assert client.asked == [
            {"query": "chess", "search_recency_filter": "week", "return_citations": True}
        ]
        assert client.closed
        assert [(s.title, s.outlet, s.summary) for s in stories] == [
            ("A", "a.example", ""),
            ("B", "b.example", "What B says."),
        ]
        assert stories[0].published_at == datetime(2026, 9, 27, tzinfo=UTC)
        assert search.section == "perplexity"


class TestTheListenersOwnKey:
    async def test_brave_first_then_perplexity_then_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        keys: dict[ConnectorType, str | None] = {
            ConnectorType.BRAVE_SEARCH: "b",
            ConnectorType.PERPLEXITY: "p",
        }

        async def key_of(user_id: str, connector_type: ConnectorType) -> str | None:
            assert user_id == str(USER)
            return keys.get(connector_type)

        monkeypatch.setattr(module, "get_connector_api_key", key_of)
        assert isinstance(await listener_interest_search(USER, stories_max=3), BraveInterestSearch)
        keys[ConnectorType.BRAVE_SEARCH] = None
        assert isinstance(
            await listener_interest_search(USER, stories_max=3), PerplexityInterestSearch
        )
        keys[ConnectorType.PERPLEXITY] = None
        assert await listener_interest_search(USER, stories_max=3) is None


class TestMarks:
    async def test_a_topic_searched_is_fresh_for_the_window_and_per_listener(self) -> None:
        redis = FakeRedis()
        mine = RedisSearchMarks(redis, USER, fresh_s=3600)
        theirs = RedisSearchMarks(redis, uuid4(), fresh_s=3600)
        assert not await mine.fresh("Chess")
        await mine.mark("Chess")
        assert await mine.fresh("chess")  # the same interest, whatever its case
        assert not await theirs.fresh("chess")
        [key] = redis.strings
        assert key.startswith(f"radio:interests:{USER}:")  # the ``radio`` family (ADR-260)
        assert redis.ttls[key] == 3600


def test_a_brave_news_date_without_a_zone_is_utc() -> None:
    assert module._brave_date("2026-09-28T06:30:00") == datetime(2026, 9, 28, 6, 30, tzinfo=UTC)
    assert module._brave_date("2026-09-28T06:30:00+02:00") == datetime(
        2026, 9, 28, 4, 30, tzinfo=UTC
    )
    assert module._brave_date("yesterday") is None
    assert module._brave_date(None) is None


class TestASessionsStart:
    """A session searches its listener's interests once, with their own key, in a
    collector of its run — and a refresh that fails never touches the session."""

    @pytest.fixture
    def filed(self, monkeypatch: pytest.MonkeyPatch) -> list[InterestStory]:
        stored: list[InterestStory] = []

        async def file(user_id: object, stories: list[InterestStory], *, now: datetime) -> int:
            assert user_id == USER and now == NOW
            stored.extend(stories)
            return len(stories)

        monkeypatch.setattr(module, "file_interest_stories", file)
        return stored

    @pytest.fixture
    def recorded(self, monkeypatch: pytest.MonkeyPatch) -> list[frozenset[str]]:
        reads: list[frozenset[str]] = []

        def recorder_for(user_id: object, run_id: str) -> object:
            assert user_id == USER and run_id == "radio_run"

            def record(*, opened: frozenset[str], failed: frozenset[str], duration_ms: int) -> None:
                reads.append(opened | failed)

            return record

        monkeypatch.setattr(module, "recorder_for", recorder_for)
        return reads

    def search_of(self, monkeypatch: pytest.MonkeyPatch, search: object) -> list[int]:
        asked: list[int] = []

        async def listener_search(user_id: object, *, stories_max: int) -> object:
            asked.append(stories_max)
            return search

        monkeypatch.setattr(module, "listener_interest_search", listener_search)
        return asked

    async def test_it_files_what_the_listener_s_key_found(
        self,
        monkeypatch: pytest.MonkeyPatch,
        filed: list[InterestStory],
        recorded: list[frozenset[str]],
    ) -> None:
        class Found:
            section = "brave"

            async def search(
                self, topic: str, *, language: str, found_at: datetime
            ) -> list[InterestStory]:
                story = interest_story(
                    url=f"https://o.example/{topic}",
                    title=topic,
                    summary="",
                    outlet="O",
                    published_at=None,
                    found_at=found_at,
                )
                assert story is not None
                return [story]

        asked = self.search_of(monkeypatch, Found())
        redis = FakeRedis()
        count = await refresh_listener_interests(
            USER, run_id="radio_run", topics=("jazz", "chess"), language="fr", redis=redis, now=NOW
        )
        assert count == 2 and [story.title for story in filed] == ["jazz", "chess"]
        assert recorded == [frozenset({"brave"})] * 2
        assert asked == [settings.radio_interest_stories_max]
        assert len(redis.strings) == 2  # both topics fresh now

    async def test_no_topic_or_no_key_searches_nothing(
        self, monkeypatch: pytest.MonkeyPatch, filed: list[InterestStory]
    ) -> None:
        asked = self.search_of(monkeypatch, None)
        assert (
            await refresh_listener_interests(
                USER, run_id="radio_run", topics=(), language="fr", redis=FakeRedis(), now=NOW
            )
            == 0
        )
        assert asked == []  # in company, or no interest: nobody's key is even looked up
        assert (
            await refresh_listener_interests(
                USER,
                run_id="radio_run",
                topics=("jazz",),
                language="fr",
                redis=FakeRedis(),
                now=NOW,
            )
            == 0
        )
        assert filed == []

    async def test_a_refresh_that_breaks_never_reaches_the_session(
        self, monkeypatch: pytest.MonkeyPatch, recorded: list[frozenset[str]]
    ) -> None:
        class Found:
            section = "brave"

            async def search(
                self, topic: str, *, language: str, found_at: datetime
            ) -> list[InterestStory]:
                return []

        async def broken(user_id: object, stories: object, *, now: datetime) -> int:
            raise RuntimeError("database down")

        self.search_of(monkeypatch, Found())
        monkeypatch.setattr(module, "file_interest_stories", broken)
        assert (
            await refresh_listener_interests(
                USER,
                run_id="radio_run",
                topics=("jazz",),
                language="fr",
                redis=FakeRedis(),
                now=NOW,
            )
            == 0
        )
