"""Integration: a listener's radio against a real PostgreSQL (ADR-324).

What only a server proves: the stories offered are every base source the
listener did not untick, in every language, and their running sites (never
another listener's), the ones they never heard first under the bound; the
settings upsert on their named constraint and read back field by field, and the
ceiling on sites holds under the per-account lock.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domains.radio import repository as module
from src.domains.radio.constants import INTEREST_FEED_URL
from src.domains.radio.formats import RadioRole
from src.domains.radio.interests import interest_story
from src.domains.radio.models import (
    FeedKind,
    RadioFeed,
    RadioNewsItem,
    RadioPreferencesRow,
    TextState,
)
from src.domains.radio.preferences import VOICES_BY_ENGINE, RadioPreferences
from src.domains.radio.repository import (
    RadioSourceLimitReached,
    add_source,
    failing_base_sources,
    file_interest_stories,
    list_sources,
    mark_listened,
    news_candidates,
    read_preferences,
    read_story,
    remove_source,
    source_stories,
    update_source,
    write_preferences,
)
from src.domains.radio.setup import VerificationMode
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 26, 7, 0, tzinfo=UTC)
#: The voice engine a listener's voices are kept for in these tests.
ENGINE = "edge/standard"


@pytest.fixture(autouse=True)
def one_session(async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextlib.asynccontextmanager
    async def _ctx() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(module, "get_db_context", _ctx)


async def listener(session: AsyncSession, name: str) -> User:
    user = User(email=f"radio_repo_{name}@test.local", hashed_password="x", is_active=True)
    session.add(user)
    await session.flush()
    return user


def feed(
    url: str,
    *,
    owner: uuid.UUID | None = None,
    language: str | None = None,
    paused: bool = False,
    failures: int = 0,
) -> RadioFeed:
    return RadioFeed(
        id=uuid.uuid4(),
        owner_id=owner,
        url=url,
        outlet=url.split("//")[1].split("/")[0],
        language=language,
        full_text=True,
        paused=paused,
        failures=failures,
    )


def story(
    feed_row: RadioFeed, key: str, hours_ago: float, *, text: str | None = None
) -> RadioNewsItem:
    return RadioNewsItem(
        feed_id=feed_row.id,
        item_key=key,
        url=f"{feed_row.url}/{key}",
        title=f"Story {key}",
        summary="",
        published_at=NOW - timedelta(hours=hours_ago),
        fingerprint=f"story {key}",
        full_text=text,
        text_state=TextState.READY.value if text else TextState.PENDING.value,
    )


async def test_a_session_is_offered_every_ticked_base_source_and_its_running_sites(
    async_session: AsyncSession,
) -> None:
    """Every language (everything airs translated), minus the base sources the listener
    unticked and the sites they paused — and never another listener's site."""
    me = await listener(async_session, "me")
    other = await listener(async_session, "other")
    fr_base = feed("https://fr.example/rss", language="fr")
    zh_base = feed("https://zh.example/rss", language="zh-CN")
    unticked = feed("https://unticked.example/rss", language="en")
    mine = feed("https://mine.example/feed", owner=me.id)
    paused = feed("https://paused.example/feed", owner=me.id, paused=True)
    theirs = feed("https://theirs.example/feed", owner=other.id)
    async_session.add_all([fr_base, zh_base, unticked, mine, paused, theirs])
    await async_session.flush()
    async_session.add_all(
        [
            story(fr_base, "fr-new", 1, text="Whole article."),
            story(fr_base, "fr-old", 30),
            story(zh_base, "zh", 2),
            story(unticked, "unticked", 1),
            story(mine, "mine", 3),
            story(paused, "paused", 1),
            story(theirs, "theirs", 1),
        ]
    )
    await async_session.flush()

    offered = await news_candidates(
        me.id,
        disabled_feeds={unticked.url},
        since=NOW - timedelta(hours=24),
        limit=10,
        interests_limit=0,
    )

    assert [candidate.title for candidate in offered] == ["Story fr-new", "Story zh", "Story mine"]
    assert offered[0].full_text == "Whole article." and offered[2].full_text is None
    assert offered[2].outlet == "mine.example"


async def test_the_bound_keeps_the_stories_the_listener_never_heard(
    async_session: AsyncSession,
) -> None:
    """With every language on the desk the freshest stories fill any bound (measured on dev
    2026-09-27: 818 stories in 48 hours, the 300 freshest covering 17 of them), so the ones
    the listener heard — the article itself, or another outlet's telling by its
    fingerprint — come last: the bound keeps what can still air, and what was heard still
    says the newsroom is not empty."""
    me = await listener(async_session, "bound")
    base = feed("https://bound.example/rss", language="en")
    async_session.add(base)
    await async_session.flush()
    heard_itself = story(base, "heard-itself", 1)
    heard_elsewhere = story(base, "heard-elsewhere", 2)
    older = story(base, "older", 20)
    unprinted = story(base, "unprinted", 30)
    unprinted.fingerprint = ""  # a feed that names no story across outlets
    async_session.add_all([heard_itself, heard_elsewhere, older, unprinted])
    await async_session.flush()

    offered = await news_candidates(
        me.id,
        disabled_feeds=(),
        since=NOW - timedelta(hours=48),
        limit=3,
        interests_limit=0,
        heard_keys={str(heard_itself.id), "event:a fact of their day"},
        heard_stories={heard_elsewhere.fingerprint, ""},
    )

    assert [candidate.title for candidate in offered] == [
        "Story older",
        "Story unprinted",  # an empty fingerprint names no telling heard
        "Story heard-itself",
    ]


async def test_commercial_rows_do_not_fill_source_and_interest_limits(
    async_session: AsyncSession,
) -> None:
    """Real SQL pages refill both bounds and retain account visibility."""
    me = await listener(async_session, "editorial")
    other = await listener(async_session, "editorial_other")
    public = feed("https://editorial-base.example/rss")
    own = feed("https://editorial-own.example/rss", owner=me.id)
    interests = feed("https://editorial-interests.example/rss", owner=me.id)
    interests.kind = FeedKind.INTEREST.value
    foreign = feed("https://editorial-foreign.example/rss", owner=other.id)
    async_session.add_all([public, own, interests, foreign])
    await async_session.flush()

    commercials = []
    for source in (own, interests):
        for index in range(65):
            commercial = story(source, f"promo-{index}", 1)
            commercial.title = "Special offer: buy now"
            commercials.append(commercial)
    base_news = story(public, "base-news", 2)
    own_news = story(own, "own-news", 3)
    interest_news = story(interests, "interest-news", 4)
    async_session.add_all(
        commercials + [base_news, own_news, interest_news, story(foreign, "private", 0)]
    )
    await async_session.flush()

    offered = await news_candidates(
        me.id,
        disabled_feeds=(),
        since=NOW - timedelta(hours=24),
        limit=2,
        interests_limit=1,
    )

    assert [candidate.key for candidate in offered] == [
        str(base_news.id),
        str(own_news.id),
        str(interest_news.id),
    ]


async def test_what_the_sources_published_is_listed_for_the_listener_s_counters(
    async_session: AsyncSession,
) -> None:
    """Every base source's stories and the listener's own sites' — paused ones included, the
    counters say what each holds — within the window; never another listener's site."""
    me = await listener(async_session, "counter")
    other = await listener(async_session, "neighbour")
    base = feed("https://count-base.example/rss", language="en")
    mine = feed("https://count-mine.example/feed", owner=me.id, paused=True)
    theirs = feed("https://count-theirs.example/feed", owner=other.id)
    async_session.add_all([base, mine, theirs])
    await async_session.flush()
    kept = story(base, "b1", 1)
    async_session.add_all([kept, story(base, "b-old", 60), story(mine, "m1", 2)])
    async_session.add(story(theirs, "t1", 1))
    await async_session.flush()

    listed = await source_stories(me.id, since=NOW - timedelta(hours=48))

    assert sorted((s.feed_url, s.own, s.fingerprint) for s in listed) == [
        (base.url, False, "story b1"),
        (mine.url, True, "story m1"),
    ]
    assert str(kept.id) in {s.key for s in listed}  # the key the aired ledger files


async def test_a_listener_renames_and_pauses_only_their_own_site(
    async_session: AsyncSession,
) -> None:
    me = await listener(async_session, "owner")
    other = await listener(async_session, "intruder")
    mine = feed("https://rename-mine.example/feed", owner=me.id, failures=2)
    base = feed("https://rename-base.example/rss", language="en", failures=3)
    async_session.add_all([mine, base])
    await async_session.flush()

    assert await update_source(me.id, mine.id, title="My blog", paused=True)
    assert not await update_source(other.id, mine.id, title="Stolen", paused=None)
    assert not await update_source(me.id, base.id, title="A base source", paused=None)

    [listed] = await list_sources(me.id)
    assert (listed.title, listed.paused, listed.failing) == ("My blog", True, True)
    assert await update_source(me.id, mine.id, title=None, paused=False)
    [resumed] = await list_sources(me.id)
    assert (resumed.title, resumed.paused) == ("My blog", False)
    assert await failing_base_sources() >= {base.url}


async def test_a_story_is_opened_under_the_shortlists_own_visibility(
    async_session: AsyncSession,
) -> None:
    """The radio page opens the catalogue's stories and the listener's own sites'
    — another listener's site is unknown, never refused by name."""
    me = await listener(async_session, "reader")
    other = await listener(async_session, "stranger")
    world = feed("https://open-world.example/rss", language="en")
    mine = feed("https://open-mine.example/feed", owner=me.id)
    theirs = feed("https://open-theirs.example/feed", owner=other.id)
    async_session.add_all([world, mine, theirs])
    await async_session.flush()
    public = story(world, "public", 1, text="The whole article.")
    own = story(mine, "own", 2)
    foreign = story(theirs, "foreign", 1)
    async_session.add_all([public, own, foreign])
    await async_session.flush()

    opened = await read_story(me.id, public.id)
    assert opened is not None
    assert (opened.outlet, opened.language, opened.full_text) == (
        "open-world.example",
        "en",
        "The whole article.",
    )
    own_story = await read_story(me.id, own.id)
    assert own_story is not None and own_story.full_text is None  # not read yet: no text
    assert await read_story(me.id, foreign.id) is None
    assert await read_story(other.id, own.id) is None
    assert await read_story(me.id, uuid.uuid4()) is None


async def test_the_settings_read_back_field_by_field_with_their_personality(
    async_session: AsyncSession,
) -> None:
    me = await listener(async_session, "settings")
    assert await read_preferences(me.id, engine=ENGINE) == RadioPreferences()

    chosen = RadioPreferences(timer_minutes=45, verification=VerificationMode.ALL)
    await write_preferences(me.id, chosen, engine=ENGINE)
    await write_preferences(me.id, chosen.model_copy(update={"timer_minutes": 60}), engine=ENGINE)

    assert (await read_preferences(me.id, engine=ENGINE)).timer_minutes == 60
    rows = (
        await async_session.execute(
            select(func.count())
            .select_from(RadioPreferencesRow)
            .where(RadioPreferencesRow.user_id == me.id)
        )
    ).scalar_one()
    assert rows == 1  # one row per listener: the second write updated it
    # A field a later version dropped, or a value it no longer reads, is its default.
    row = (
        await async_session.execute(
            select(RadioPreferencesRow).where(RadioPreferencesRow.user_id == me.id)
        )
    ).scalar_one()
    row.preferences = {**row.preferences, "timer_minutes": "soon", "gone": True}
    await async_session.flush()
    read = await read_preferences(me.id, engine=ENGINE)
    assert read.timer_minutes is None and read.verification is VerificationMode.ALL


async def test_listening_is_filed_without_touching_the_settings(
    async_session: AsyncSession,
) -> None:
    me = await listener(async_session, "listening")

    await mark_listened(me.id, now=NOW)  # never saved a setting: the row is born empty
    assert await read_preferences(me.id, engine=ENGINE) == RadioPreferences()

    chosen = RadioPreferences(timer_minutes=45)
    await write_preferences(me.id, chosen, engine=ENGINE)
    later = NOW + timedelta(hours=2)
    await mark_listened(me.id, now=later)

    row = (
        await async_session.execute(
            select(RadioPreferencesRow).where(RadioPreferencesRow.user_id == me.id)
        )
    ).scalar_one()
    await async_session.refresh(row)
    assert row.last_listened_at == later
    assert (await read_preferences(me.id, engine=ENGINE)).timer_minutes == 45  # settings untouched
    await write_preferences(me.id, chosen.model_copy(update={"timer_minutes": 60}), engine=ENGINE)
    await async_session.refresh(row)
    assert row.last_listened_at == later  # and a settings write keeps it


async def test_sites_are_bounded_idempotent_and_only_their_owner_removes_them(
    async_session: AsyncSession,
) -> None:
    me = await listener(async_session, "sites")
    stranger = await listener(async_session, "stranger")
    first = await add_source(
        me.id, feed_url="https://a.example/feed", title="A", language="en", max_sources=2
    )
    again = await add_source(
        me.id, feed_url="https://a.example/feed", title="A again", language=None, max_sources=2
    )
    assert again == first  # the same site twice is the same source
    await add_source(
        me.id, feed_url="https://b.example/feed", title="B", language=None, max_sources=2
    )
    with pytest.raises(RadioSourceLimitReached):
        await add_source(
            me.id, feed_url="https://c.example/feed", title="C", language=None, max_sources=2
        )
    assert [source.title for source in await list_sources(me.id)] == ["A", "B"]

    site = await async_session.get(RadioFeed, first.id)
    assert site is not None
    async_session.add(story(site, "x", 1))
    await async_session.flush()
    assert await remove_source(stranger.id, first.id) is False
    assert await remove_source(me.id, first.id) is True
    left = (
        await async_session.execute(
            select(func.count()).select_from(RadioNewsItem).where(RadioNewsItem.feed_id == first.id)
        )
    ).scalar_one()
    assert left == 0  # the site's stories went with it
    assert [source.title for source in await list_sources(me.id)] == ["B"]


@pytest_asyncio.fixture
async def committed(test_database_url: str) -> AsyncIterator[tuple[Any, str]]:
    """Sessions whose writes really commit — a race needs two connections."""
    engine = create_async_engine(test_database_url, echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    marker = uuid.uuid4().hex
    yield maker, marker
    async with maker() as session:
        await session.execute(delete(User).where(User.email.like(f"%{marker}%")))
        await session.commit()
    await engine.dispose()


async def test_two_sites_racing_for_the_last_place_cannot_both_land(
    committed: tuple[Any, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    maker, marker = committed
    async with maker() as session:
        owner = User(email=f"radio_race_{marker}@test.local", hashed_password="x", is_active=True)
        session.add(owner)
        await session.commit()

    # Each transaction waits after its count until the other has counted too,
    # so the two overlap for certain. Under the lock the second cannot count
    # before the first commits — waiting for it would deadlock — so the wait
    # is bounded, and a barrier the first gave up on is broken for the second.
    barrier = asyncio.Barrier(2)

    @contextlib.asynccontextmanager
    async def _committing() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            execute = session.execute

            async def counted_then_wait(statement: Any, *args: Any, **kwargs: Any) -> Any:
                result = await execute(statement, *args, **kwargs)
                if "count(" in str(statement).lower():
                    with contextlib.suppress(TimeoutError, asyncio.BrokenBarrierError):
                        await asyncio.wait_for(barrier.wait(), timeout=1.0)
                return result

            monkeypatch.setattr(session, "execute", counted_then_wait)
            yield session
            await session.commit()

    monkeypatch.setattr(module, "get_db_context", _committing)

    async def _add(url: str) -> str:
        try:
            await add_source(owner.id, feed_url=url, title=url, language=None, max_sources=1)
        except RadioSourceLimitReached:
            return "refused"
        return "added"

    outcomes = await asyncio.gather(_add("https://a.example/feed"), _add("https://b.example/feed"))

    assert sorted(outcomes) == ["added", "refused"]
    assert len(await list_sources(owner.id)) == 1


async def test_each_voice_engine_keeps_the_voices_chosen_on_it(
    async_session: AsyncSession,
) -> None:
    """Owner request 2026-09-27: an engine switched back to finds the voices chosen on it."""
    me = await listener(async_session, "voices")
    await write_preferences(me.id, RadioPreferences(voices={RadioRole.HOST: "va"}), engine="a/1")
    await write_preferences(
        me.id, RadioPreferences(voices={RadioRole.HOST: "vb"}, timer_minutes=20), engine="b/2"
    )

    assert (await read_preferences(me.id, engine="a/1")).voices == {RadioRole.HOST: "va"}
    back_on_b = await read_preferences(me.id, engine="b/2")
    assert (back_on_b.voices, back_on_b.timer_minutes) == ({RadioRole.HOST: "vb"}, 20)
    assert (await read_preferences(me.id, engine="c/3")).voices == {}


async def test_the_flat_voices_of_an_older_row_are_offered_then_kept_per_engine(
    async_session: AsyncSession,
) -> None:
    me = await listener(async_session, "flat")
    row = RadioPreferencesRow(user_id=me.id, preferences={"voices": {"host": "old"}})
    async_session.add(row)
    await async_session.flush()

    assert (await read_preferences(me.id, engine="a/1")).voices == {RadioRole.HOST: "old"}
    await write_preferences(me.id, RadioPreferences(voices={RadioRole.HOST: "new"}), engine="a/1")

    await async_session.refresh(row)
    assert "voices" not in row.preferences
    assert row.preferences[VOICES_BY_ENGINE] == {"a/1": {"host": "new"}}


def interest_row(owner: uuid.UUID) -> RadioFeed:
    return RadioFeed(
        id=uuid.uuid4(),
        owner_id=owner,
        url=INTEREST_FEED_URL,
        outlet="",
        full_text=True,
        kind=FeedKind.INTEREST.value,
    )


async def test_a_listener_s_interests_are_no_site_of_theirs(async_session: AsyncSession) -> None:
    """ADR-324 decision 40: the row holding what a search found for the listener's
    interests is never listed, counted, renamed, paused or removed as a site, and its
    stories are no source's in the settings' counters."""
    me = await listener(async_session, "interests_row")
    site = feed("https://interest-site.example/feed", owner=me.id)
    found = interest_row(me.id)
    async_session.add_all([site, found])
    await async_session.flush()
    async_session.add_all([story(site, "s1", 1), story(found, "i1", 1)])
    await async_session.flush()

    assert [source.id for source in await list_sources(me.id)] == [site.id]
    assert not await update_source(me.id, found.id, title="Mine", paused=True)
    assert await remove_source(me.id, found.id) is False
    # The ceiling counts sites alone: one site and the interest row leave room for one.
    await add_source(
        me.id, feed_url="https://second.example/feed", title="Second", language=None, max_sources=2
    )
    listed = await source_stories(me.id, since=NOW - timedelta(hours=48))
    assert {entry.feed_url for entry in listed} == {site.url}


async def test_the_stories_a_search_found_are_offered_under_their_own_outlet(
    async_session: AsyncSession,
) -> None:
    me = await listener(async_session, "interests_offer")
    other = await listener(async_session, "interests_other")
    site = feed("https://offer-site.example/feed", owner=me.id)
    found, theirs = interest_row(me.id), interest_row(other.id)
    async_session.add_all([site, found, theirs])
    await async_session.flush()
    mine = story(found, "i1", 2)
    mine.outlet = "The Outlet"
    async_session.add_all([story(site, "s1", 1), mine, story(theirs, "o1", 1)])
    await async_session.flush()

    offered = {
        candidate.title: candidate
        for candidate in await news_candidates(
            me.id,
            disabled_feeds=(),
            since=NOW - timedelta(hours=48),
            limit=50,
            interests_limit=50,
        )
    }
    assert (offered["Story s1"].from_interests, offered["Story s1"].outlet) == (
        False,
        "offer-site.example",
    )
    assert (offered["Story i1"].from_interests, offered["Story i1"].outlet) == (
        True,
        "The Outlet",
    )
    assert "Story o1" not in offered
    opened = await read_story(me.id, mine.id)
    assert opened is not None and opened.outlet == "The Outlet"
    assert await read_story(other.id, mine.id) is None


async def test_the_interests_stories_have_a_bound_of_their_own(
    async_session: AsyncSession,
) -> None:
    """Measured on dev 2026-09-29: 1 214 source stories in 48 hours, and four of the six a
    search found fell past the 300 freshest — read by no desk although the listener's key
    paid for them. Two bounds: the sources never crowd the interests out, the interests
    never the sources, and within each what was heard comes last."""
    me = await listener(async_session, "interests_bound")
    base = feed("https://interests-bound.example/rss", language="en")
    site = feed("https://interests-bound-site.example/feed", owner=me.id)
    found = interest_row(me.id)
    async_session.add_all([base, site, found])
    await async_session.flush()
    heard = story(found, "i-heard", 20)
    async_session.add_all(
        [
            *(story(base, f"s{hours}", hours) for hours in (1, 2, 3, 4)),
            story(site, "site", 5),
            heard,
            story(found, "i30", 30),
            story(found, "i40", 40),
        ]
    )
    await async_session.flush()

    offered = await news_candidates(
        me.id,
        disabled_feeds=(),
        since=NOW - timedelta(hours=48),
        limit=2,
        interests_limit=2,
        heard_keys={str(heard.id)},
    )

    assert [(c.title, c.from_interests) for c in offered] == [
        ("Story s1", False),
        ("Story s2", False),
        ("Story i30", True),  # older than every source story, still on the desk
        ("Story i40", True),
    ]


async def test_a_session_without_interests_is_offered_none_of_their_stories(
    async_session: AsyncSession,
) -> None:
    """In company, with the capability off or with no interest left, what a search found
    earlier would voice what the listener cares about: a zero bound reads none of it."""
    me = await listener(async_session, "interests_none")
    site = feed("https://interests-none-site.example/feed", owner=me.id)
    found = interest_row(me.id)
    async_session.add_all([site, found])
    await async_session.flush()
    async_session.add_all([story(site, "site", 1), story(found, "i1", 1)])
    await async_session.flush()

    offered = await news_candidates(
        me.id, disabled_feeds=(), since=NOW - timedelta(hours=48), limit=10, interests_limit=0
    )

    assert [candidate.title for candidate in offered] == ["Story site"]


async def test_what_a_search_found_is_filed_once_under_one_row_per_listener(
    async_session: AsyncSession,
) -> None:
    me = await listener(async_session, "interests_file")
    first, second, third = (
        interest_story(
            url=f"https://{name}.example/a",
            title=name.upper(),
            summary="Said." if name == "x" else "",
            outlet=name.upper(),
            published_at=NOW - timedelta(hours=2) if name == "x" else None,
            found_at=NOW,
        )
        for name in ("x", "y", "z")
    )
    assert first is not None and second is not None and third is not None

    assert await file_interest_stories(me.id, [first, second], now=NOW) == 2
    assert await file_interest_stories(me.id, [first, third], now=NOW) == 1
    assert await file_interest_stories(me.id, [], now=NOW) == 0

    rows = (
        (await async_session.execute(select(RadioFeed).where(RadioFeed.owner_id == me.id)))
        .scalars()
        .all()
    )
    assert [(row.kind, row.url) for row in rows] == [(FeedKind.INTEREST.value, INTEREST_FEED_URL)]
    items = (
        (
            await async_session.execute(
                select(RadioNewsItem)
                .where(RadioNewsItem.feed_id == rows[0].id)
                .order_by(RadioNewsItem.title)
            )
        )
        .scalars()
        .all()
    )
    assert [(item.title, item.outlet, item.summary, item.text_state) for item in items] == [
        ("X", "X", "Said.", TextState.PENDING.value),
        ("Y", "Y", "", TextState.PENDING.value),
        ("Z", "Z", "", TextState.PENDING.value),
    ]
    assert items[0].published_at == NOW - timedelta(hours=2)
    assert items[1].published_at == NOW
