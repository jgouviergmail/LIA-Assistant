"""The listener's own searches for their interests (ADR-324 decision 40).

A listener who connected their own search service has their interests searched with it:
their Brave key first (its news endpoint lists articles with their dates and outlets),
else their Perplexity key (the articles its answer rests on). Their key, their spend —
never recorded as the platform's (the owner's rule) — and every search one consultation
of the radio's surface, filed by the caller (:func:`interests.refresh_interest_stories`).
A listener with neither has no interest search here.

A search the service could not answer is a FAILURE, never « nothing found »: the Brave
client answers ``None`` on every error, and reading that as an empty result would mark
the topic as searched and hide the outage for the whole freshness window.

What was searched is remembered per listener and topic for a window
(:class:`RedisSearchMarks`, the ``radio`` key family): a session started within it reuses
the stories the last search filed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.connectors.clients.brave_search_client import BraveSearchClient
from src.domains.connectors.clients.perplexity_client import PerplexityClient
from src.domains.connectors.models import ConnectorType
from src.domains.interests.helpers import get_connector_api_key
from src.domains.radio.consultations import collecting, recorder_for
from src.domains.radio.editorial import NEWS_MAX_AGE_S
from src.domains.radio.interests import (
    InterestSearch,
    InterestStory,
    interest_story,
    refresh_interest_stories,
)
from src.domains.radio.repository import file_interest_stories

logger = structlog.get_logger(__name__)

#: How far back a Perplexity search looks — a week, its narrowest window past a day; a
#: story older than any programme may air is then left unfiled (the desk reads two days).
PERPLEXITY_RECENCY: Final[str] = "week"


def brave_freshness(found_at: datetime) -> str:
    """The UTC days a Brave news search covers: the desk's horizon, never the week.

    A result older than any programme may air is dropped unfiled, so a week's window
    bought results nobody could hear; Brave takes a custom day range
    (``YYYY-MM-DDtoYYYY-MM-DD``).
    """
    until = found_at.astimezone(UTC)
    since = until - timedelta(seconds=NEWS_MAX_AGE_S)
    return f"{since:%Y-%m-%d}to{until:%Y-%m-%d}"


def _brave_date(value: object) -> datetime | None:
    """A Brave news date (``page_age``), read as UTC when it names no zone."""
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)


def _day(value: object) -> datetime | None:
    """A ``YYYY-MM-DD`` date as its midnight in UTC."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value[:10]).replace(tzinfo=UTC)
    except ValueError:
        return None


def _text(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    return value if isinstance(value, str) else ""


class BraveInterestSearch:
    """Searches the news with the listener's own Brave key."""

    section = "brave"

    def __init__(self, api_key: str, user_id: UUID, *, stories_max: int) -> None:
        self._api_key = api_key
        self._user_id = user_id
        self._stories_max = stories_max

    async def search(self, topic: str, *, language: str, found_at: datetime) -> list[InterestStory]:
        """The news about ``topic`` within the desk's days, as stories.

        Raises:
            ConnectionError: When Brave could not answer (its client says so with
                ``None``).
        """
        client = BraveSearchClient(api_key=self._api_key, language=language, user_id=self._user_id)
        try:
            data = await client.search(
                query=topic,
                endpoint="news",
                count=self._stories_max,
                freshness=brave_freshness(found_at),
            )
        finally:
            await client.close()
        if data is None:
            raise ConnectionError("the search service did not answer")
        stories: list[InterestStory] = []
        for entry in data.get("results") or []:
            if not isinstance(entry, dict):
                continue
            profile = entry.get("profile")
            site = entry.get("meta_url")
            outlet = (
                _text(profile, "name")
                if isinstance(profile, dict)
                else _text(site, "hostname") if isinstance(site, dict) else ""
            )
            story = interest_story(
                url=_text(entry, "url"),
                title=_text(entry, "title"),
                summary=_text(entry, "description"),
                outlet=outlet,
                published_at=_brave_date(entry.get("page_age")),
                found_at=found_at,
            )
            if story is not None:
                stories.append(story)
        return stories[: self._stories_max]


class PerplexityInterestSearch:
    """Searches with the listener's own Perplexity key: the articles its answer rests on."""

    section = "perplexity"

    def __init__(self, api_key: str, user_id: UUID, *, stories_max: int) -> None:
        self._api_key = api_key
        self._user_id = user_id
        self._stories_max = stories_max

    async def search(self, topic: str, *, language: str, found_at: datetime) -> list[InterestStory]:
        """The week's articles about ``topic``, as stories (the client raises on failure)."""
        client = PerplexityClient(api_key=self._api_key, user_id=self._user_id)
        try:
            result = await client.search(
                topic, search_recency_filter=PERPLEXITY_RECENCY, return_citations=True
            )
        finally:
            await client.close()
        stories: list[InterestStory] = []
        for entry in result.get("search_results") or []:
            if not isinstance(entry, dict):
                continue
            story = interest_story(
                url=_text(entry, "url"),
                title=_text(entry, "title"),
                summary=_text(entry, "snippet"),
                outlet="",
                published_at=_day(entry.get("date")),
                found_at=found_at,
            )
            if story is not None:
                stories.append(story)
        return stories[: self._stories_max]


async def listener_interest_search(user_id: UUID, *, stories_max: int) -> InterestSearch | None:
    """The listener's own search: their Brave key, else their Perplexity key, else none.

    Args:
        user_id: The listener.
        stories_max: The most stories one search keeps.

    Returns:
        The search, or ``None`` when they connected neither.
    """
    brave = await get_connector_api_key(str(user_id), ConnectorType.BRAVE_SEARCH)
    if brave:
        return BraveInterestSearch(brave, user_id, stories_max=stories_max)
    perplexity = await get_connector_api_key(str(user_id), ConnectorType.PERPLEXITY)
    if perplexity:
        return PerplexityInterestSearch(perplexity, user_id, stories_max=stories_max)
    return None


class RedisSearchMarks:
    """Which of a listener's interests were searched within the freshness window."""

    def __init__(self, redis: Any, user_id: UUID, *, fresh_s: int) -> None:
        self._redis = redis
        self._user_id = user_id
        self._fresh_s = fresh_s

    def _key(self, topic: str) -> str:
        # A digest: an interest is the listener's words, never a key's text.
        digest = hashlib.sha256(topic.strip().casefold().encode("utf-8")).hexdigest()[:16]
        return f"radio:interests:{self._user_id}:{digest}"

    async def fresh(self, topic: str) -> bool:
        """Whether the topic's last search is within the window."""
        return bool(await self._redis.exists(self._key(topic)))

    async def mark(self, topic: str) -> None:
        """The topic was just searched."""
        await self._redis.set(self._key(topic), "1", ex=self._fresh_s)


async def refresh_listener_interests(
    user_id: UUID,
    *,
    run_id: str,
    topics: Sequence[str],
    language: str,
    redis: Any,
    now: datetime,
) -> int:
    """Search a session's listener's interests with their own key; file what it found.

    Run once when a session's loop starts, beside it: the stories reach the desk at
    its next reading. Never raises — a refresh that breaks costs the session its
    interest stories, never the session.

    Args:
        user_id: The listener.
        run_id: The session's run (the searches are its consultations).
        topics: Their interests the start read, strongest first — already bounded by
            ``RADIO_INTEREST_TOPICS_MAX`` (none in company, none with the capability off).
        language: Their language.
        redis: Where the searches are remembered.
        now: The instant (aware).

    Returns:
        How many new stories were filed.
    """
    if not topics:
        return 0
    try:
        search = await listener_interest_search(
            user_id, stories_max=settings.radio_interest_stories_max
        )
        if search is None:
            return 0

        async def file(stories: Sequence[InterestStory]) -> int:
            return await file_interest_stories(user_id, stories, now=now)

        async with collecting(run_id):
            filed = await refresh_interest_stories(
                topics,
                search=search,
                marks=RedisSearchMarks(
                    redis, user_id, fresh_s=settings.radio_interest_fresh_seconds
                ),
                file=file,
                record=recorder_for(user_id, run_id),
                language=language,
                now=now,
                max_age_s=NEWS_MAX_AGE_S,
            )
    except Exception as exc:  # noqa: BLE001 — the interests are extra material, never the session
        logger.warning("radio_interest_refresh_failed", error_type=type(exc).__name__)
        return 0
    logger.info("radio_interest_stories_filed", filed=filed, section=search.section)
    return filed


__all__ = [
    "BraveInterestSearch",
    "PerplexityInterestSearch",
    "RedisSearchMarks",
    "brave_freshness",
    "listener_interest_search",
    "refresh_listener_interests",
]
