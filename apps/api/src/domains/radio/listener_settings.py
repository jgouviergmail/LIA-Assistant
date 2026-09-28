"""What a listener may set — offered as published, checked where it is written (ADR-324).

The settings page is offered exactly what a write accepts (ADR-184), and a
write refuses what a session would drop (ADR-245: the write path rejects, the
runtime coerces): a timer past the instance's maximum, a voice the radio's
engine does not offer in the listener's language, a personality that is not
offered any more. What the page READS obeys the same rule: a stored voice the
engine no longer offers — its engine was changed, its language too — reads as
automatic, since sent back it would refuse every save. A site is looked for
before it is shown, and looked for AGAIN when it is added: the address a page
previewed a minute ago may lead elsewhere now, and only what the server found
is stored.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.i18n import normalize_language
from src.domains.personalities.models import Personality
from src.domains.radio.adapters import aired_ledger, radio_engine, radio_engine_key
from src.domains.radio.cast import usable_voices
from src.domains.radio.constants import SOURCE_DISCOVERY_TIMEOUT_S, SOURCE_LABEL_MAX_CHARS
from src.domains.radio.editorial import NEWS_MAX_AGE_S
from src.domains.radio.errors import (
    PERSONALITY_UNKNOWN,
    SOURCE_LIMIT,
    SOURCE_REFUSED,
    TIMER_TOO_LONG,
    VOICE_UNKNOWN,
    raise_source_not_found,
    refuse,
)
from src.domains.radio.newsroom.catalogue import CATALOGUE
from src.domains.radio.newsroom.sources import Discovery, DiscoveryOutcome, discover_feed
from src.domains.radio.options import build_options
from src.domains.radio.preferences import RadioPreferences
from src.domains.radio.repository import (
    RadioSource,
    RadioSourceLimitReached,
    add_source,
    failing_base_sources,
    list_sources,
    read_preferences,
    source_stories,
    update_source,
    write_preferences,
)
from src.domains.radio.schemas import (
    RadioOptionsResponse,
    RadioSourcesResponse,
    RadioSourceUpdateRequest,
)
from src.domains.radio.setup import VerificationMode
from src.domains.radio.setup_builder import RadioStartRefused
from src.domains.radio.sources_view import sources_overview
from src.domains.radio.wiring import newsroom_client, newsroom_robots
from src.domains.voice.voices_catalog import VoiceOption
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_radio import radio_source_lookups_total

logger = structlog.get_logger(__name__)


async def offered_voices(language: str) -> list[VoiceOption]:
    """The voices the settings may offer a listener — none when the engine cannot be served.

    Args:
        language: The listener's language.

    Returns:
        The engine's voices usable in that language.
    """
    try:
        engine = await radio_engine()
    except RadioStartRefused:
        return []
    return usable_voices(engine.voices, language, engine.multilingual)


async def radio_options(language: str) -> RadioOptionsResponse:
    """The options the radio's settings publish for a listener.

    Args:
        language: The listener's stored language.

    Returns:
        Every list and bound a write accepts.
    """
    return build_options(
        voices=await offered_voices(normalize_language(language)),
        timer_default_minutes=settings.radio_timer_minutes,
        timer_max_minutes=settings.radio_timer_max_minutes,
        verification_default=VerificationMode(settings.radio_verification_default),
        custom_sources_max=settings.radio_custom_sources_max,
    )


async def listener_preferences(user_id: UUID, language: str) -> RadioPreferences:
    """The listener's settings as the page may send them back: every voice offered.

    Args:
        user_id: The listener.
        language: Their stored language.

    Returns:
        The stored settings; a voice the engine no longer offers in their
        language reads as automatic (an engine that cannot list its voices
        right now keeps the stored choice: it cannot tell).
    """
    preferences = await read_preferences(user_id, engine=await radio_engine_key())
    if not preferences.voices:
        return preferences
    offered = {voice.voice_id for voice in await offered_voices(normalize_language(language))}
    if not offered:
        return preferences
    kept = {role: voice for role, voice in preferences.voices.items() if voice in offered}
    return preferences.model_copy(update={"voices": kept})


async def _personality_offered(personality_id: UUID) -> bool:
    async with get_db_context() as db:
        personality = await db.get(Personality, personality_id)
        return personality is not None and bool(personality.is_active)


async def save_preferences(
    user_id: UUID, language: str, preferences: RadioPreferences
) -> RadioPreferences:
    """Check the listener's settings against what the radio offers, then store them.

    Args:
        user_id: The listener.
        language: Their stored language.
        preferences: The whole new settings (already valid in shape).

    Returns:
        The settings as stored.

    Raises:
        BaseAPIException: ``radio_timer_too_long``, ``radio_voice_unknown`` or
            ``radio_personality_unknown``.
    """
    timer_max = settings.radio_timer_max_minutes
    if preferences.timer_minutes is not None and preferences.timer_minutes > timer_max:
        refuse(TIMER_TOO_LONG, max_minutes=timer_max)
    if preferences.voices:
        offered = {voice.voice_id for voice in await offered_voices(normalize_language(language))}
        # An engine that cannot list its voices right now cannot be strict:
        # the cast reads a stored choice forgivingly anyway.
        if offered and not set(preferences.voices.values()) <= offered:
            refuse(VOICE_UNKNOWN)
    if preferences.personality_id is not None and not await _personality_offered(
        preferences.personality_id
    ):
        refuse(PERSONALITY_UNKNOWN)
    return await write_preferences(user_id, preferences, engine=await radio_engine_key())


async def look_for_feed(address: str) -> Discovery:
    """The feed a site serves, looked for within a bound (past it: unreachable).

    Args:
        address: What the listener typed.

    Returns:
        What looking for it found; never an exception for the network.
    """
    robots = await newsroom_robots()
    try:
        async with asyncio.timeout(SOURCE_DISCOVERY_TIMEOUT_S), newsroom_client() as client:
            found = await discover_feed(
                client,
                address,
                robots=robots,
                max_bytes=settings.radio_newsroom_feed_max_bytes,
            )
    except TimeoutError:
        found = Discovery(DiscoveryOutcome.UNREACHABLE)
    radio_source_lookups_total.labels(outcome=found.outcome.value).inc()
    return found


def _label_of(found: Discovery, feed_url: str) -> str:
    """How the station names a site: its feed's title, else its host."""
    title = found.description.title if found.description else ""
    return (title or urlsplit(feed_url).hostname or feed_url)[:SOURCE_LABEL_MAX_CHARS]


async def add_listener_source(user_id: UUID, address: str) -> RadioSource:
    """Look for the site's feed again, and add what was found.

    Args:
        user_id: The listener.
        address: What they typed.

    Returns:
        The source (the same one when the site was already added).

    Raises:
        BaseAPIException: ``radio_source_refused`` (with the outcome) when no
            feed was found, ``radio_source_limit`` (with the maximum) past it.
    """
    found = await look_for_feed(address)
    if found.outcome is not DiscoveryOutcome.FOUND or found.feed_url is None:
        refuse(SOURCE_REFUSED, outcome=found.outcome.value)
    try:
        return await add_source(
            user_id,
            feed_url=found.feed_url,
            title=_label_of(found, found.feed_url),
            language=found.description.language if found.description else None,
            max_sources=settings.radio_custom_sources_max,
        )
    except RadioSourceLimitReached:
        refuse(SOURCE_LIMIT, max_sources=settings.radio_custom_sources_max)


async def listener_sources(user_id: UUID, *, now: datetime) -> RadioSourcesResponse:
    """Every source of the listener's newsroom, and what it holds for them (decision 38).

    Args:
        user_id: The listener.
        now: The instant the window ends at (aware).

    Returns:
        The base sources and their own sites, each with what it published within
        the window a programme airs from and how many of those they never heard.
    """
    preferences = await read_preferences(user_id, engine=await radio_engine_key())
    heard_keys, heard_stories = await (await aired_ledger(user_id)).heard()
    return sources_overview(
        catalogue=CATALOGUE,
        failing_base=await failing_base_sources(),
        own=await list_sources(user_id),
        stories=await source_stories(user_id, since=now - timedelta(seconds=NEWS_MAX_AGE_S)),
        heard_keys=heard_keys,
        heard_stories=heard_stories,
        disabled_feeds=frozenset(preferences.disabled_feeds),
        window_hours=NEWS_MAX_AGE_S // 3600,
    )


async def update_listener_source(
    user_id: UUID, source_id: UUID, request: RadioSourceUpdateRequest
) -> None:
    """Rename or pause one of the listener's sites.

    Raises:
        ResourceNotFoundError: The site is not theirs (a base source is unticked in the
            settings, never paused).
    """
    if not await update_source(user_id, source_id, title=request.title, paused=request.paused):
        raise_source_not_found(source_id)


async def forget_heard(user_id: UUID) -> None:
    """Forget what the listener heard: every story may air again (a live session keeps
    its own memory until it ends)."""
    await (await aired_ledger(user_id)).forget()


__all__ = [
    "add_listener_source",
    "forget_heard",
    "listener_preferences",
    "listener_sources",
    "look_for_feed",
    "offered_voices",
    "radio_options",
    "save_preferences",
    "update_listener_source",
]
