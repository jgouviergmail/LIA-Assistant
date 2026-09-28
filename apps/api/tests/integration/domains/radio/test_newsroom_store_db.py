"""Integration: the newsroom's store against a real PostgreSQL (ADR-324).

What only a server proves: the catalogue is synchronised through its PARTIAL
unique index (a listener's site at the same address is another row, never
touched), a failure count grows by column arithmetic, a story is kept once by
its unique key, and a removed feed takes its stories by FK cascade.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.radio.constants import INTEREST_FEED_URL
from src.domains.radio.models import (
    FeedKind,
    RadioFeed,
    RadioNewsItem,
    RadioPreferencesRow,
    TextState,
)
from src.domains.radio.newsroom import store as module
from src.domains.radio.newsroom.catalogue import CatalogueFeed
from src.domains.radio.newsroom.collector import FeedReading
from src.domains.radio.newsroom.parse import ParsedItem
from src.domains.radio.newsroom.store import NewsroomDatabase
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 26, 7, 0, tzinfo=UTC)
#: A window every listener of these tests listened within.
LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)
WIRE = CatalogueFeed(
    outlet="Wire",
    url="https://wire.example/feed",
    language="en",
    full_text=True,
)
DIGEST = CatalogueFeed(
    outlet="Digest",
    url="https://digest.example/rss",
    language="fr",
    full_text=False,
)


@pytest.fixture
def store(async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> NewsroomDatabase:
    @contextlib.asynccontextmanager
    async def _ctx() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(module, "get_db_context", _ctx)
    return NewsroomDatabase()


def item(key: str, minutes_ago: int) -> ParsedItem:
    return ParsedItem(
        item_key=key,
        url=f"https://wire.example/{key}",
        title=f"Story {key}",
        summary="A summary.",
        published_at=NOW - timedelta(minutes=minutes_ago),
        fingerprint=f"story {key}",
    )


async def feed_id(session: AsyncSession, url: str) -> uuid.UUID:
    found: uuid.UUID = (
        await session.execute(
            select(RadioFeed.id).where(RadioFeed.url == url, RadioFeed.owner_id.is_(None))
        )
    ).scalar_one()
    return found


async def someone_listens(session: AsyncSession) -> None:
    """A listener within every window of these tests: the catalogue is read for them."""
    user = User(email=f"radio_store_{uuid.uuid4().hex[:8]}@test.local", hashed_password="x")
    session.add(user)
    await session.flush()
    session.add(RadioPreferencesRow(user_id=user.id, last_listened_at=NOW))
    await session.flush()


async def test_the_catalogue_follows_the_shipped_one_and_never_touches_a_listeners_site(
    store: NewsroomDatabase, async_session: AsyncSession
) -> None:
    listener = User(email="radio_store_site@test.local", hashed_password="x", is_active=True)
    async_session.add(listener)
    await async_session.flush()
    async_session.add(
        RadioFeed(owner_id=listener.id, url=DIGEST.url, outlet="My digest", full_text=True)
    )
    await async_session.flush()

    await store.sync_catalogue([WIRE, DIGEST])
    first_write = (
        await async_session.execute(select(RadioFeed.updated_at).where(RadioFeed.url == WIRE.url))
    ).scalar_one()
    await store.sync_catalogue(
        [WIRE, DIGEST]
    )  # every pass syncs: nothing changed, nothing rewritten
    assert (
        await async_session.execute(select(RadioFeed.updated_at).where(RadioFeed.url == WIRE.url))
    ).scalar_one() == first_write
    await store.sync_catalogue([replace(WIRE, outlet="Wire (renamed)")])

    catalogue = (
        await async_session.execute(
            select(RadioFeed.url, RadioFeed.outlet).where(RadioFeed.owner_id.is_(None))
        )
    ).all()
    assert [(row.url, row.outlet) for row in catalogue] == [(WIRE.url, "Wire (renamed)")]
    own = (
        await async_session.execute(
            select(RadioFeed.outlet).where(RadioFeed.owner_id == listener.id)
        )
    ).scalar_one()
    assert own == "My digest"  # same address as a dropped catalogue feed: another row


async def test_a_reading_files_its_validators_and_failures_grow_by_arithmetic(
    store: NewsroomDatabase, async_session: AsyncSession
) -> None:
    await store.sync_catalogue([WIRE])
    await someone_listens(async_session)
    wire = await feed_id(async_session, WIRE.url)
    for _ in range(2):
        await store.record_reading(wire, FeedReading("unreachable", False, None, None), now=NOW)
    (state,) = await store.feed_states(listened_since=LONG_AGO)
    assert (state.failures, state.last_read_at) == (2, NOW)
    await store.record_reading(
        wire, FeedReading("ok", True, '"v2"', "Sat, 26 Sep 2026 06:00:00 GMT"), now=NOW
    )
    (state,) = await store.feed_states(listened_since=LONG_AGO)
    assert (state.failures, state.etag, state.last_modified) == (
        0,
        '"v2"',
        "Sat, 26 Sep 2026 06:00:00 GMT",
    )


async def test_a_story_is_kept_once_and_its_text_is_filed_through_its_states(
    store: NewsroomDatabase, async_session: AsyncSession
) -> None:
    await store.sync_catalogue([WIRE, DIGEST])
    wire = await feed_id(async_session, WIRE.url)
    digest = await feed_id(async_session, DIGEST.url)

    assert await store.add_items(wire, [item("a", 30), item("b", 10)], full_text=True) == 2
    assert await store.add_items(wire, [item("a", 30), item("c", 5)], full_text=True) == 1
    assert await store.add_items(digest, [item("a", 20)], full_text=False) == 1

    jobs = await store.text_jobs(limit=10)
    assert [job.url.rsplit("/", 1)[1] for job in jobs] == [
        "c",
        "b",
        "a",
    ]  # newest first, digest none
    c, b, a = jobs
    await store.record_text(c.item_id, "The whole article.", final=True)
    await store.record_text(b.item_id, None, final=False)  # try again later
    await store.record_text(a.item_id, None, final=True)
    states = dict(
        (
            await async_session.execute(
                select(RadioNewsItem.id, RadioNewsItem.text_state).where(
                    RadioNewsItem.feed_id == wire
                )
            )
        ).all()
    )
    assert states == {
        c.item_id: TextState.READY.value,
        b.item_id: TextState.PENDING.value,
        a.item_id: TextState.UNAVAILABLE.value,
    }
    assert [job.attempts for job in await store.text_jobs(limit=10)] == [1]


async def test_a_large_feed_is_inserted_in_batches_without_duplicates(
    store: NewsroomDatabase, async_session: AsyncSession
) -> None:
    await store.sync_catalogue([WIRE])
    wire = await feed_id(async_session, WIRE.url)
    stories = [item(f"large-{n}", 5) for n in range(1_001)]

    assert await store.add_items(wire, stories, full_text=False) == 1_001
    assert await store.add_items(wire, stories, full_text=False) == 0
    count = (
        await async_session.execute(
            select(func.count()).select_from(RadioNewsItem).where(RadioNewsItem.feed_id == wire)
        )
    ).scalar_one()
    assert count == 1_001


async def test_the_purge_removes_the_old_stories_and_a_dropped_feed_takes_its_own(
    store: NewsroomDatabase, async_session: AsyncSession
) -> None:
    await store.sync_catalogue([WIRE, DIGEST])
    wire = await feed_id(async_session, WIRE.url)
    digest = await feed_id(async_session, DIGEST.url)
    await store.add_items(wire, [item("old", 60 * 50), item("new", 10)], full_text=True)
    await store.add_items(digest, [item("d", 10)], full_text=False)

    assert await store.purge(published_before=NOW - timedelta(hours=48)) == 1
    await store.sync_catalogue([WIRE])  # the digest is no longer shipped
    left = (
        await async_session.execute(select(func.count()).select_from(RadioNewsItem))
    ).scalar_one()
    assert left == 1


async def test_the_newsroom_reads_only_for_recent_listeners(
    store: NewsroomDatabase, async_session: AsyncSession
) -> None:
    """The catalogue while anyone listened within the window, a listener's own
    sites while THEY did — an instance nobody listens to reads nothing."""
    await store.sync_catalogue([WIRE])
    recent, gone = (
        User(email=f"radio_store_{name}@test.local", hashed_password="x", is_active=True)
        for name in ("recent", "gone")
    )
    async_session.add_all([recent, gone])
    await async_session.flush()
    for user in (recent, gone):
        async_session.add(
            RadioFeed(owner_id=user.id, url=f"https://{user.id.hex}.example/feed", outlet="Site")
        )
    await async_session.flush()
    window_start = NOW - timedelta(days=7)

    assert await store.feed_states(listened_since=window_start) == []  # nobody ever listened

    async_session.add_all(
        [
            RadioPreferencesRow(user_id=recent.id, last_listened_at=NOW - timedelta(days=1)),
            RadioPreferencesRow(user_id=gone.id, last_listened_at=NOW - timedelta(days=30)),
        ]
    )
    await async_session.flush()
    urls = {state.url for state in await store.feed_states(listened_since=window_start)}
    assert urls == {WIRE.url, f"https://{recent.id.hex}.example/feed"}

    # A site its listener paused is not read, however recently they listened.
    paused = RadioFeed(
        owner_id=recent.id, url="https://paused.example/feed", outlet="Paused", paused=True
    )
    async_session.add(paused)
    await async_session.flush()
    urls = {state.url for state in await store.feed_states(listened_since=window_start)}
    assert paused.url not in urls

    # Nor the row of the stories a search found for their interests: nothing to read
    # there (ADR-324 decision 40).
    interests = RadioFeed(
        owner_id=recent.id, url=INTEREST_FEED_URL, outlet="", kind=FeedKind.INTEREST.value
    )
    async_session.add(interests)
    await async_session.flush()
    urls = {state.url for state in await store.feed_states(listened_since=window_start)}
    assert INTEREST_FEED_URL not in urls
