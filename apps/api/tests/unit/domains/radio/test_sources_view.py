"""What each of a listener's sources holds for them — the settings' view (ADR-324)."""

from __future__ import annotations

import uuid

import pytest

from src.domains.radio.newsroom.catalogue import CatalogueFeed
from src.domains.radio.repository import RadioSource, SourceStory
from src.domains.radio.schemas import RadioSourcesResponse
from src.domains.radio.sources_view import sources_overview

pytestmark = pytest.mark.unit

BBC = CatalogueFeed("BBC News", "https://bbc.example/rss", "en", full_text=True)
DW = CatalogueFeed("DW", "https://dw.example/rss", "de", full_text=True)
MINE = RadioSource(
    id=uuid.UUID("00000000-0000-4000-8000-00000000c001"),
    feed_url="https://mine.example/feed",
    title="My blog",
    language="fr",
)
PAUSED = RadioSource(
    id=uuid.UUID("00000000-0000-4000-8000-00000000c002"),
    feed_url="https://paused.example/feed",
    title="Paused",
    language=None,
    paused=True,
    failing=True,
)


def base_story(feed: CatalogueFeed, key: str, fingerprint: str = "") -> SourceStory:
    return SourceStory(
        feed_id=uuid.uuid4(),
        feed_url=feed.url,
        own=False,
        key=key,
        fingerprint=fingerprint or f"fp-{key}",
    )


def own_story(site: RadioSource, key: str) -> SourceStory:
    return SourceStory(
        feed_id=site.id, feed_url=site.feed_url, own=True, key=key, fingerprint=f"fp-{key}"
    )


def overview(
    stories: list[SourceStory],
    *,
    heard_keys: frozenset[str] = frozenset(),
    heard_stories: frozenset[str] = frozenset(),
    disabled: frozenset[str] = frozenset(),
    failing: frozenset[str] = frozenset(),
) -> RadioSourcesResponse:
    return sources_overview(
        catalogue=(BBC, DW),
        failing_base=failing,
        own=(MINE, PAUSED),
        stories=stories,
        heard_keys=heard_keys,
        heard_stories=heard_stories,
        disabled_feeds=disabled,
        window_hours=48,
    )


def test_each_source_says_what_it_published_and_what_the_listener_never_heard() -> None:
    view = overview(
        [
            base_story(BBC, "b1"),
            base_story(BBC, "b2"),
            base_story(DW, "d1"),
            own_story(MINE, "m1"),
        ],
        heard_keys=frozenset({"b1"}),
    )
    counts = {source.url: (source.stories, source.unheard) for source in view.base}
    assert counts == {BBC.url: (2, 1), DW.url: (1, 1)}
    [mine, paused] = view.own
    assert (mine.stories, mine.unheard, paused.stories) == (1, 1, 0)
    assert (view.stories, view.unheard, view.window_hours) == (4, 3, 48)


def test_a_story_told_by_another_outlet_was_heard_all_the_same() -> None:
    """The same story across outlets shares its fingerprint: heard once, heard everywhere."""
    view = overview(
        [base_story(BBC, "b1", "the-vote"), base_story(DW, "d1", "the-vote")],
        heard_stories=frozenset({"the-vote"}),
    )
    assert [(source.stories, source.unheard) for source in view.base] == [(1, 0), (1, 0)]


def test_the_totals_count_only_what_the_station_reads() -> None:
    """An unticked base source and a paused site still say what they hold — the totals
    are what the radio can air."""
    view = overview(
        [base_story(BBC, "b1"), base_story(DW, "d1"), own_story(PAUSED, "p1")],
        disabled=frozenset({DW.url}),
    )
    [bbc, dw] = view.base
    assert (bbc.heard, dw.heard, dw.stories) == (True, False, 1)
    assert view.own[1].stories == 1  # a paused site's stories are still counted on its row
    assert (view.stories, view.unheard) == (1, 1)


def test_the_base_sources_keep_the_catalogue_s_order_and_say_which_fail() -> None:
    view = overview([], failing=frozenset({DW.url}))
    assert [(s.name, s.language, s.failing) for s in view.base] == [
        ("BBC News", "en", False),
        ("DW", "de", True),
    ]
    assert [(s.title, s.paused, s.failing) for s in view.own] == [
        ("My blog", False, False),
        ("Paused", True, True),
    ]
