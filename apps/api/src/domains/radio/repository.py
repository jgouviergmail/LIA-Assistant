"""A listener's radio in the database: their settings, their sites, their stories (ADR-324).

Every function opens its own short session (ADR-304): the antenna reads the
stories while a session airs, the routes read and write the settings — none
holds a transaction around anything but its own statements.

- The stories offered to a session are those of every base source the
  listener did not untick, in every language (everything airs translated),
  and of their own sites they did not pause — the ones they never heard first,
  so a bound keeps what can still air. What a search found for their interests is
  read under a bound of its OWN: thousands of source stories would otherwise push
  it past the sources' bound, unread although the listener's key paid for it.
- The settings are one row: the JSON the settings page edits, the personality
  in a column so its deletion clears it. They are read field by field
  (``read_radio_preferences``): a row older than a field reads as its default.
  The same row files when the listener last listened — the newsroom reads only
  for recent listeners — and neither write touches the other's columns.
- A listener's sites are bounded: counted and written under one per-account
  lock, so two additions at once cannot pass the ceiling.
- What each source published lately is LISTED over the window for the settings'
  counters (``source_stories``): the stories are few per source, and whether the
  listener heard one is answered by their ledger, not by the database.
- One story is read for the radio page under the same visibility as a session's
  shortlist: the catalogue's, or the listener's own sites' — never another
  listener's site, and an id the listener may not read is simply unknown.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.radio.constants import INTEREST_FEED_URL
from src.domains.radio.editorial import NewsCandidate
from src.domains.radio.interests import InterestStory
from src.domains.radio.models import (
    FeedKind,
    RadioFeed,
    RadioNewsItem,
    RadioPreferencesRow,
    TextState,
)
from src.domains.radio.newsroom.editorial_rows import editorial_rows
from src.domains.radio.preferences import (
    VOICES_BY_ENGINE,
    RadioPreferences,
    engine_voices,
    read_radio_preferences,
    with_engine_voices,
)
from src.domains.shared.commercial_content import editorial_excerpt, is_commercial_content
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.database.session import get_db_context

#: The per-account lock scope under which a listener's sites are counted and added.
_SOURCES_LOCK_SCOPE = "radio_custom_source"


class RadioSourceLimitReached(Exception):
    """The listener already has as many sites as the instance allows."""


@dataclass(frozen=True, slots=True)
class RadioSource:
    """A site a listener added to their newsroom.

    Attributes:
        id: The source.
        feed_url: Its feed.
        title: How the station names it (the listener may rename it).
        language: The language it declares, when it does.
        paused: Whether the listener paused it (not read, not offered).
        failing: Whether its last readings failed (the newsroom backs off).
    """

    id: uuid.UUID
    feed_url: str
    title: str
    language: str | None
    paused: bool = False
    failing: bool = False


@dataclass(frozen=True, slots=True)
class SourceStory:
    """A story one of the listener's sources published within a window — what a counter counts.

    Attributes:
        feed_id: Its feed.
        feed_url: Its feed's address (a base source is known by it).
        own: Whether the feed is the listener's own site.
        key: The story's key in the aired ledger.
        fingerprint: The same story across outlets.
    """

    feed_id: uuid.UUID
    feed_url: str
    own: bool
    key: str
    fingerprint: str


def _sources_heard_by(user_id: uuid.UUID, disabled_feeds: Collection[str]) -> ColumnElement[bool]:
    """The sources a listener's radio reads: every base source they did not untick, in
    every language, and their own sites they did not pause."""
    base: ColumnElement[bool] = RadioFeed.owner_id.is_(None)
    if disabled_feeds:
        base = and_(base, RadioFeed.url.not_in(list(disabled_feeds)))
    own_sites = and_(
        RadioFeed.owner_id == user_id,
        RadioFeed.kind == FeedKind.SOURCE.value,
        RadioFeed.paused.is_(False),
    )
    return or_(base, own_sites)


def _interests_of(user_id: uuid.UUID) -> ColumnElement[bool]:
    """The row of what a search found for the listener's interests (never paused)."""
    return and_(RadioFeed.owner_id == user_id, RadioFeed.kind == FeedKind.INTEREST.value)


def _story_ids(keys: Collection[str]) -> list[uuid.UUID]:
    """The keys that name a stored story — its row's id; a fact of the day names none."""
    ids: list[uuid.UUID] = []
    for key in keys:
        # A key of the listener's day (an event, a notification) is no story's id.
        with suppress(ValueError):
            ids.append(uuid.UUID(key))
    return ids


def _heard_last(keys: Collection[str], stories: Collection[str]) -> list[ColumnElement[bool]]:
    """The ordering that puts a story heard — the article itself, or another outlet's
    telling of it — after every other; none when nothing was heard (PostgreSQL refuses
    a constant to order by)."""
    heard: list[ColumnElement[bool]] = []
    ids = _story_ids(keys)
    if ids:
        heard.append(RadioNewsItem.id.in_(ids))
    fingerprints = sorted({story for story in stories if story})
    if fingerprints:
        heard.append(RadioNewsItem.fingerprint.in_(fingerprints))
    return [or_(*heard)] if heard else []


async def news_candidates(
    user_id: uuid.UUID,
    *,
    disabled_feeds: Collection[str],
    since: datetime,
    limit: int,
    interests_limit: int,
    heard_keys: Collection[str] = (),
    heard_stories: Collection[str] = (),
) -> list[NewsCandidate]:
    """The stories a listener's session may choose from: never heard first, the freshest first.

    Every language fills any bound with its freshest stories (measured on dev
    2026-09-27: 818 in 48 hours, the 300 freshest covering 17), so the stories the
    listener heard come last: the bound keeps what can still air, and what was heard
    still tells an exhausted newsroom from an empty one.

    What a search found for their interests (ADR-324 decision 40) is read under a bound
    of its own, never in competition with the sources: measured on dev 2026-09-29, 1 214
    source stories in 48 hours left four of six such stories past a shared bound of 300.

    Args:
        user_id: The listener.
        disabled_feeds: The base sources they unticked (by address).
        since: The oldest story worth offering.
        limit: The most stories of the sources and their sites returned.
        interests_limit: The most stories a search found for their interests returned
            (0: none — the session holds no interest).
        heard_keys: The keys they heard (a story's key is its id; others are ignored).
        heard_stories: The fingerprints of the stories they heard.

    Returns:
        The stories of every base source they hear and of their running sites, then
        what a search found for their interests.
    """
    heard_last = _heard_last(heard_keys, heard_stories)

    def read(where: ColumnElement[bool]) -> Select[tuple[RadioNewsItem, str]]:
        return (
            select(RadioNewsItem, RadioFeed.outlet)
            .join(RadioFeed, RadioFeed.id == RadioNewsItem.feed_id)
            .where(RadioNewsItem.published_at >= since, where)
            .order_by(*heard_last, RadioNewsItem.published_at.desc(), RadioNewsItem.id.desc())
        )

    async with get_db_context() as db:
        sources = await editorial_rows(
            db,
            read(_sources_heard_by(user_id, disabled_feeds)),
            limit=limit,
            eligible=lambda row: _stored_editorial(row[0]),
            identity=lambda row: row[0].id,
        )
        found = await editorial_rows(
            db,
            read(_interests_of(user_id)),
            limit=interests_limit,
            eligible=lambda row: _stored_editorial(row[0]),
            identity=lambda row: row[0].id,
        )
    return [
        *(_candidate(item, outlet, from_interests=False) for item, outlet in sources),
        *(_candidate(item, outlet, from_interests=True) for item, outlet in found),
    ]


def _stored_editorial(item: RadioNewsItem) -> bool:
    return not is_commercial_content(item.title, summary=item.summary, body=item.full_text or "")


def _candidate(item: RadioNewsItem, outlet: str, *, from_interests: bool) -> NewsCandidate:
    """One stored story as a desk candidate — its own outlet first (a search names one)."""
    return NewsCandidate(
        key=str(item.id),
        outlet=item.outlet or outlet,
        url=item.url,
        title=item.title,
        summary=editorial_excerpt(item.summary),
        published_at=item.published_at,
        fingerprint=item.fingerprint,
        full_text=(
            (editorial_excerpt(item.full_text) if item.full_text else None)
            if item.text_state == TextState.READY.value
            else None
        ),
        from_interests=from_interests,
    )


@dataclass(frozen=True, slots=True)
class NewsStory:
    """One stored story, as the radio page opens it.

    Attributes:
        id: The story.
        outlet: Its outlet's name.
        url: The article.
        title: The headline.
        summary: The feed's summary (may be empty).
        published_at: When it was published.
        language: Its feed's language, when the feed declares one.
        full_text: The article's text, when the newsroom could read it.
    """

    id: uuid.UUID
    outlet: str
    url: str
    title: str
    summary: str
    published_at: datetime
    language: str | None
    full_text: str | None


async def read_story(user_id: uuid.UUID, story_id: uuid.UUID) -> NewsStory | None:
    """A story the listener may open: the catalogue's, one of their own sites', or one a
    search found for their interests.

    Args:
        user_id: The listener.
        story_id: The story.

    Returns:
        The story; ``None`` when it does not exist or is not the listener's to read.
    """
    stmt = (
        select(RadioNewsItem, RadioFeed.outlet, RadioFeed.language)
        .join(RadioFeed, RadioFeed.id == RadioNewsItem.feed_id)
        .where(
            RadioNewsItem.id == story_id,
            or_(RadioFeed.owner_id.is_(None), RadioFeed.owner_id == user_id),
        )
    )
    async with get_db_context() as db:
        row = (await db.execute(stmt)).first()
    if row is None:
        return None
    item, outlet, language = row
    return NewsStory(
        id=item.id,
        outlet=item.outlet or outlet,
        url=item.url,
        title=item.title,
        summary=item.summary,
        published_at=item.published_at,
        language=language,
        full_text=item.full_text if item.text_state == TextState.READY.value else None,
    )


async def read_preferences(user_id: uuid.UUID, *, engine: str) -> RadioPreferences:
    """The listener's settings, their voices those kept for ``engine``; the defaults when
    they never saved any.

    Args:
        user_id: The listener.
        engine: The voice engine in place (``cast.engine_key``).

    Returns:
        The settings as the page and a start read them.
    """
    async with get_db_context() as db:
        row = (
            await db.execute(
                select(RadioPreferencesRow.preferences, RadioPreferencesRow.personality_id).where(
                    RadioPreferencesRow.user_id == user_id
                )
            )
        ).first()
    if row is None:
        return RadioPreferences()
    return read_radio_preferences(row.preferences).model_copy(
        update={
            "personality_id": row.personality_id,
            "voices": engine_voices(row.preferences, engine),
        }
    )


async def write_preferences(
    user_id: uuid.UUID, preferences: RadioPreferences, *, engine: str
) -> RadioPreferences:
    """Replace the listener's settings; their voices are kept for ``engine`` alone.

    Every other engine's voices stay: the row is read under a lock and written back as
    a NEW mapping in the same transaction, so two saves never lose each other's engine.
    The flat voices of a row written before voices were kept per engine are dropped.

    Args:
        user_id: The listener.
        preferences: The whole new settings, already validated.
        engine: The voice engine the voices were chosen on (``cast.engine_key``).

    Returns:
        The settings as stored.
    """
    now = datetime.now(UTC)
    payload = preferences.model_dump(mode="json", exclude={"personality_id", "voices"})
    async with get_db_context() as db:
        stored = (
            await db.execute(
                select(RadioPreferencesRow.preferences)
                .where(RadioPreferencesRow.user_id == user_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        payload[VOICES_BY_ENGINE] = with_engine_voices(stored, engine, preferences.voices)
        await _upsert_preferences(db, user_id, payload, preferences.personality_id, now=now)
    return preferences


async def _upsert_preferences(
    db: AsyncSession,
    user_id: uuid.UUID,
    payload: dict[str, object],
    personality_id: uuid.UUID | None,
    *,
    now: datetime,
) -> None:
    """Create or update the listener's settings row — one statement."""
    stmt = pg_insert(RadioPreferencesRow).values(
        id=uuid.uuid4(),
        user_id=user_id,
        preferences=payload,
        personality_id=personality_id,
        created_at=now,
        updated_at=now,
    )
    await db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_radio_preferences_user",
            set_={
                "preferences": stmt.excluded.preferences,
                "personality_id": stmt.excluded.personality_id,
                "updated_at": now,
            },
        )
    )


async def mark_listened(user_id: uuid.UUID, *, now: datetime) -> None:
    """File that the listener started a session (one statement; settings untouched).

    Args:
        user_id: The listener.
        now: When the session started (timezone-aware).
    """
    stmt = pg_insert(RadioPreferencesRow).values(
        id=uuid.uuid4(),
        user_id=user_id,
        preferences={},
        last_listened_at=now,
        created_at=now,
        updated_at=now,
    )
    async with get_db_context() as db:
        await db.execute(
            stmt.on_conflict_do_update(
                constraint="uq_radio_preferences_user",
                set_={"last_listened_at": stmt.excluded.last_listened_at},
            )
        )


def _source(row: Any) -> RadioSource:
    return RadioSource(
        row.id, row.url, row.outlet, row.language, paused=row.paused, failing=row.failures > 0
    )


_SOURCE_COLUMNS = (
    RadioFeed.id,
    RadioFeed.url,
    RadioFeed.outlet,
    RadioFeed.language,
    RadioFeed.paused,
    RadioFeed.failures,
)


def _site_of(user_id: uuid.UUID) -> ColumnElement[bool]:
    """The sites a listener added — never the row of what a search found for them."""
    return and_(RadioFeed.owner_id == user_id, RadioFeed.kind == FeedKind.SOURCE.value)


async def list_sources(user_id: uuid.UUID) -> list[RadioSource]:
    """The sites a listener added, in the order they were added."""
    async with get_db_context() as db:
        rows = (
            await db.execute(
                select(*_SOURCE_COLUMNS)
                .where(_site_of(user_id))
                .order_by(RadioFeed.created_at, RadioFeed.id)
            )
        ).all()
    return [_source(row) for row in rows]


async def update_source(
    user_id: uuid.UUID, source_id: uuid.UUID, *, title: str | None, paused: bool | None
) -> bool:
    """Rename or pause one of the listener's sites (one statement).

    Args:
        user_id: The listener.
        source_id: The site.
        title: Its new name, or ``None`` to keep it.
        paused: Whether it is paused now, or ``None`` to keep it as it is.

    Returns:
        False when the site is not theirs (a base source never is).
    """
    changes: dict[str, object] = {"updated_at": datetime.now(UTC)}
    if title is not None:
        changes["outlet"] = title
    if paused is not None:
        changes["paused"] = paused
    async with get_db_context() as db:
        result = await db.execute(
            update(RadioFeed)
            .where(RadioFeed.id == source_id, _site_of(user_id))
            .values(**changes)
            .returning(RadioFeed.id)
        )
        return result.first() is not None


async def source_stories(user_id: uuid.UUID, *, since: datetime) -> list[SourceStory]:
    """Every story published since an instant by the base sources and the listener's own
    sites — paused or unticked ones included: the settings say what each one holds.

    Args:
        user_id: The listener.
        since: The window's start (the oldest story a programme airs).

    Returns:
        One entry per story; never another listener's site.
    """
    stmt = (
        select(
            RadioFeed.id,
            RadioFeed.url,
            RadioFeed.owner_id,
            RadioNewsItem.id.label("story_id"),
            RadioNewsItem.fingerprint,
        )
        .join(RadioFeed, RadioFeed.id == RadioNewsItem.feed_id)
        .where(
            RadioNewsItem.published_at >= since,
            RadioFeed.kind == FeedKind.SOURCE.value,
            or_(RadioFeed.owner_id.is_(None), RadioFeed.owner_id == user_id),
        )
    )
    async with get_db_context() as db:
        rows = (await db.execute(stmt)).all()
    return [
        SourceStory(
            feed_id=row.id,
            feed_url=row.url,
            own=row.owner_id is not None,
            key=str(row.story_id),
            fingerprint=row.fingerprint,
        )
        for row in rows
    ]


async def failing_base_sources() -> frozenset[str]:
    """The base sources whose last readings failed (the newsroom backs off them)."""
    async with get_db_context() as db:
        rows = (
            await db.execute(
                select(RadioFeed.url).where(RadioFeed.owner_id.is_(None), RadioFeed.failures > 0)
            )
        ).scalars()
        return frozenset(rows)


async def add_source(
    user_id: uuid.UUID,
    *,
    feed_url: str,
    title: str,
    language: str | None,
    max_sources: int,
) -> RadioSource:
    """Add a site to the listener's newsroom; adding it again returns it unchanged.

    Args:
        user_id: The listener.
        feed_url: The feed found for the site.
        title: How the station names it.
        language: The language it declares, when it does.
        max_sources: The instance's ceiling (published).

    Returns:
        The source.

    Raises:
        RadioSourceLimitReached: A new site past the ceiling.
    """
    async with get_db_context() as db:
        await hold_owner_lock(db, _SOURCES_LOCK_SCOPE, user_id)
        existing = (
            await db.execute(
                select(*_SOURCE_COLUMNS).where(_site_of(user_id), RadioFeed.url == feed_url)
            )
        ).first()
        if existing is not None:
            return _source(existing)
        count = (
            await db.execute(select(func.count()).select_from(RadioFeed).where(_site_of(user_id)))
        ).scalar_one()
        if count >= max_sources:
            raise RadioSourceLimitReached
        now = datetime.now(UTC)
        source = RadioSource(uuid.uuid4(), feed_url, title, language)
        db.add(
            RadioFeed(
                id=source.id,
                owner_id=user_id,
                url=feed_url,
                outlet=title,
                language=language,
                # The site's articles are opened like the catalogue's: robots.txt
                # decides page by page, and the analysis needs a full text.
                full_text=True,
                failures=0,
                created_at=now,
                updated_at=now,
            )
        )
    return source


async def _interest_row(db: AsyncSession, user_id: uuid.UUID, now: datetime) -> uuid.UUID:
    """The listener's interest row, made the first time: one per listener, at the owner's
    unique address ``INTEREST_FEED_URL`` — no site can have it (a site is ``http(s)``)."""
    await db.execute(
        pg_insert(RadioFeed)
        .values(
            id=uuid.uuid4(),
            owner_id=user_id,
            url=INTEREST_FEED_URL,
            outlet="",
            # Its articles are opened like any other: the newsroom reads the text of
            # every pending story, robots.txt deciding page by page.
            full_text=True,
            kind=FeedKind.INTEREST.value,
            failures=0,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(
            index_elements=[RadioFeed.owner_id, RadioFeed.url],
            index_where=RadioFeed.owner_id.is_not(None),
        )
    )
    found: uuid.UUID = (
        await db.execute(
            select(RadioFeed.id).where(
                RadioFeed.owner_id == user_id, RadioFeed.kind == FeedKind.INTEREST.value
            )
        )
    ).scalar_one()
    return found


async def file_interest_stories(
    user_id: uuid.UUID, stories: Sequence[InterestStory], *, now: datetime
) -> int:
    """File what a search found for the listener's interests; return how many were new.

    Args:
        user_id: The listener.
        stories: The stories found (normalised: ``interests.interest_story``).
        now: When they were found.

    Returns:
        How many were stored — a story already filed is kept as it was.
    """
    if not stories:
        return 0
    async with get_db_context() as db:
        feed_id = await _interest_row(db, user_id, now)
        result = await db.execute(
            pg_insert(RadioNewsItem)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "feed_id": feed_id,
                        "item_key": story.item_key,
                        "url": story.url,
                        "title": story.title,
                        "summary": story.summary,
                        "published_at": story.published_at,
                        "fingerprint": story.fingerprint,
                        "outlet": story.outlet,
                        "text_state": TextState.PENDING.value,
                        "text_attempts": 0,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for story in stories
                ]
            )
            .on_conflict_do_nothing(index_elements=[RadioNewsItem.feed_id, RadioNewsItem.item_key])
            .returning(RadioNewsItem.id)
        )
        return len(result.all())


async def remove_source(user_id: uuid.UUID, source_id: uuid.UUID) -> bool:
    """Remove one of the listener's sites (its stories go with it); False when not theirs."""
    async with get_db_context() as db:
        result = await db.execute(
            delete(RadioFeed)
            .where(RadioFeed.id == source_id, _site_of(user_id))
            .returning(RadioFeed.id)
        )
        return result.first() is not None


__all__ = [
    "NewsStory",
    "RadioSource",
    "RadioSourceLimitReached",
    "SourceStory",
    "add_source",
    "failing_base_sources",
    "file_interest_stories",
    "list_sources",
    "mark_listened",
    "news_candidates",
    "read_preferences",
    "read_story",
    "remove_source",
    "source_stories",
    "update_source",
    "write_preferences",
]
