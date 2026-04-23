"""BriefingService — orchestrates the 6 source fetchers, cache, and LLM helpers.

Lecture pure: no LangGraph, no DB model, no migration. Sources are fetched in
parallel via asyncio.gather. Each section has its own Redis cache TTL.

Two LLM calls (greeting + synthesis) run in parallel after the cards are
assembled. Both are non-fatal: failures fall back to a static greeting and a
None synthesis so the dashboard always renders.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.auth.models import User
from src.domains.briefing.constants import (
    BRIEFING_CACHE_PREFIX,
    ERROR_CODE_INTERNAL,
    SECTION_AGENDA,
    SECTION_AGENDA_TTL_SECONDS,
    SECTION_BIRTHDAYS,
    SECTION_BIRTHDAYS_TTL_SECONDS,
    SECTION_HEALTH,
    SECTION_HEALTH_TTL_SECONDS,
    SECTION_MAILS,
    SECTION_MAILS_TTL_SECONDS,
    SECTION_REMINDERS,
    SECTION_REMINDERS_TTL_SECONDS,
    SECTION_WEATHER,
    SECTION_WEATHER_TTL_SECONDS,
)
from src.domains.briefing.exceptions import (
    ConnectorAccessError,
    ConnectorNotConfiguredError,
)
from src.domains.briefing.fetchers import (
    fetch_agenda,
    fetch_birthdays,
    fetch_health,
    fetch_mails,
    fetch_reminders,
    fetch_weather,
)
from src.domains.briefing.llm import generate_greeting, generate_synthesis
from src.domains.briefing.schemas import (
    BriefingResponse,
    CardsBundle,
    CardSection,
    CardStatus,
    SynthesisResponse,
    TextSection,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.metrics_briefing import (
    briefing_build_duration_seconds,
    briefing_refresh_requests_total,
    briefing_section_status_total,
)

logger = structlog.get_logger(__name__)

# Sentinel value to distinguish "freshly fetched live" vs. "cache hit" without
# leaking that distinction into the wire payload.
_ORIGIN_LIVE = "live"
_ORIGIN_CACHE = "cache"


def _resolve_user_tz(user: User) -> ZoneInfo:
    """Best-effort timezone resolution with safe fallback."""
    try:
        return ZoneInfo(user.timezone)
    except (KeyError, ValueError, AttributeError, TypeError):
        return ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)


def _seconds_to_next_local_midnight(user_tz: ZoneInfo, *, cap_seconds: int = 86400) -> int:
    """Return the seconds remaining until the next 00:00 in `user_tz`.

    Used for caches that pre-compute relative-day fields (e.g. `days_until` on
    birthday cards): expiring at local midnight guarantees the value is
    recomputed at the right moment rather than carrying stale arithmetic
    until the next manual refresh. Capped at 24 h as a safety net.
    """
    now_local = datetime.now(user_tz)
    next_midnight = (now_local + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    seconds = int((next_midnight - now_local).total_seconds())
    return max(1, min(seconds, cap_seconds))


def _has_content(data: Any) -> bool:
    """Return True if the data payload has at least one displayable item."""
    if data is None:
        return False
    for attr in ("events", "items"):
        value = getattr(data, attr, None)
        if value is not None:
            return len(value) > 0
    # Non-list payloads (e.g. WeatherData) — assume present means content.
    return True


class BriefingService:
    """Orchestrator for the Today briefing.

    Lifetime: created per request (cheap — only holds the user reference).

    No db session is held by the service: each fetcher acquires its own session
    via ``get_db_context()`` to allow safe concurrent execution under
    asyncio.gather (SQLAlchemy AsyncSession does not support concurrent
    operations on a single session).
    """

    def __init__(self, user: User) -> None:
        self.user = user
        self.user_tz = _resolve_user_tz(user)
        self.language = user.language or "en"

    # =========================================================================
    # Public entry point
    # =========================================================================

    async def build_cards(
        self,
        force_refresh: set[str] | None = None,
    ) -> CardsBundle:
        """Build the 6-card bundle (no LLM call). Fast — returns when cards are ready.

        This is the non-blocking endpoint backbone: the frontend renders the
        dashboard grid as soon as this returns, without waiting for the LLM
        greeting + synthesis (handled by build_synthesis()).

        Args:
            force_refresh: Set of section names to bypass cache for.

        Returns:
            CardsBundle ready for the UI.
        """
        force = force_refresh or set()
        force_all = "all" in force
        if force:
            briefing_refresh_requests_total.labels(scope="all" if force_all else "single").inc()

        start = time.perf_counter()

        # Fetch all 6 sections in parallel — each independently failable.
        # Each fetcher acquires its own DB session (SQLAlchemy AsyncSession is
        # not safe for concurrent use, see fetchers.py module docstring).
        weather, agenda, mails, birthdays, reminders, health = await asyncio.gather(
            self._section(
                SECTION_WEATHER,
                lambda: fetch_weather(user=self.user, user_tz=self.user_tz, language=self.language),
                ttl=SECTION_WEATHER_TTL_SECONDS,
                force=force_all or SECTION_WEATHER in force,
            ),
            self._section(
                SECTION_AGENDA,
                lambda: fetch_agenda(user=self.user, user_tz=self.user_tz),
                ttl=SECTION_AGENDA_TTL_SECONDS,
                force=force_all or SECTION_AGENDA in force,
            ),
            self._section(
                SECTION_MAILS,
                lambda: fetch_mails(user=self.user, user_tz=self.user_tz),
                ttl=SECTION_MAILS_TTL_SECONDS,
                force=force_all or SECTION_MAILS in force,
            ),
            self._section(
                SECTION_BIRTHDAYS,
                lambda: fetch_birthdays(user=self.user, user_tz=self.user_tz),
                # Birthday cards pre-compute `days_until`, so the cache MUST
                # expire at local midnight — otherwise a value cached on day N
                # still advertises the same "N days" on day N+1 until the next
                # manual refresh. Cap hard at 24 h as a belt-and-braces safety.
                ttl=_seconds_to_next_local_midnight(self.user_tz),
                force=force_all or SECTION_BIRTHDAYS in force,
            ),
            self._section(
                SECTION_REMINDERS,
                lambda: fetch_reminders(
                    user_id=self.user.id,
                    user_tz=self.user_tz,
                    language=self.language,
                ),
                ttl=SECTION_REMINDERS_TTL_SECONDS,
                force=True,  # always live — local DB lookup is < 10 ms
            ),
            self._section(
                SECTION_HEALTH,
                lambda: fetch_health(user=self.user),
                ttl=SECTION_HEALTH_TTL_SECONDS,
                force=force_all or SECTION_HEALTH in force,
            ),
        )

        cards = CardsBundle(
            weather=weather,
            agenda=agenda,
            mails=mails,
            birthdays=birthdays,
            reminders=reminders,
            health=health,
        )

        duration_s = time.perf_counter() - start
        cache_state = self._classify_cache_state(
            (weather, SECTION_WEATHER_TTL_SECONDS),
            (agenda, SECTION_AGENDA_TTL_SECONDS),
            (mails, SECTION_MAILS_TTL_SECONDS),
            (birthdays, SECTION_BIRTHDAYS_TTL_SECONDS),
            (reminders, 0),  # always live
            (health, SECTION_HEALTH_TTL_SECONDS),
        )
        briefing_build_duration_seconds.labels(cache_state=cache_state).observe(duration_s)
        logger.info(
            "briefing_cards_built",
            user_id=str(self.user.id),
            duration_ms=int(duration_s * 1000),
            cache_state=cache_state,
            sections_status={
                SECTION_WEATHER: weather.status.value,
                SECTION_AGENDA: agenda.status.value,
                SECTION_MAILS: mails.status.value,
                SECTION_BIRTHDAYS: birthdays.status.value,
                SECTION_REMINDERS: reminders.status.value,
                SECTION_HEALTH: health.status.value,
            },
            forced_refresh=sorted(force),
        )
        return cards

    async def build_text(self) -> SynthesisResponse:
        """Build the LLM greeting + synthesis from the current cached cards.

        Reads each section from the Redis cache. Sections without a cache entry
        are reported as NOT_CONFIGURED to the LLM (the LLM works with what it has).
        This avoids re-fetching: the cards endpoint is supposed to populate the
        cache moments before this is called.

        Returns:
            SynthesisResponse with greeting (always populated, fallback if LLM down)
            and synthesis (None when too few cards have data).
        """
        cards = await self._read_cards_from_cache()

        (greeting_text, greeting_usage), (synthesis_text, synthesis_usage) = await asyncio.gather(
            generate_greeting(
                user=self.user,
                user_tz=self.user_tz,
                cards=cards,
                language=self.language,
            ),
            generate_synthesis(
                user=self.user,
                user_tz=self.user_tz,
                cards=cards,
                language=self.language,
            ),
        )

        now = datetime.now(UTC)
        return SynthesisResponse(
            greeting=TextSection(text=greeting_text, generated_at=now, usage=greeting_usage),
            synthesis=(
                TextSection(text=synthesis_text, generated_at=now, usage=synthesis_usage)
                if synthesis_text
                else None
            ),
        )

    async def build_today(
        self,
        force_refresh: set[str] | None = None,
    ) -> BriefingResponse:
        """Backward-compatible bundled call: cards + LLM in one response.

        Used by POST /briefing/refresh which still returns the full payload.
        For the initial page load, the frontend now uses the split endpoints
        (/briefing/cards + /briefing/synthesis) for non-blocking rendering.
        """
        cards = await self.build_cards(force_refresh=force_refresh)
        text = await self.build_text()
        return BriefingResponse(
            greeting=text.greeting,
            synthesis=text.synthesis,
            cards=cards,
        )

    # =========================================================================
    # Section orchestration (cache + status mapping + safety net)
    # =========================================================================

    async def _section(
        self,
        name: str,
        fetcher: Callable[[], Awaitable[Any]],
        *,
        ttl: int,
        force: bool,
    ) -> CardSection:
        """Wrap a fetcher with cache + status mapping. **Never raises.**"""
        cache_key = f"{BRIEFING_CACHE_PREFIX}:{self.user.id}:{name}"

        # 1. Try cache (skipped when ttl=0 or force=True).
        if ttl > 0 and not force:
            cached = await self._read_cache(cache_key)
            if cached is not None:
                briefing_section_status_total.labels(
                    section=name, status=cached.status.value, origin=_ORIGIN_CACHE
                ).inc()
                return cached

        # 2. Live fetch + status mapping.
        now = datetime.now(UTC)
        section: CardSection
        try:
            data = await fetcher()
            section = CardSection(
                status=CardStatus.OK if _has_content(data) else CardStatus.EMPTY,
                data=data if _has_content(data) else None,
                generated_at=now,
            )
        except ConnectorNotConfiguredError as exc:
            section = CardSection(
                status=CardStatus.NOT_CONFIGURED,
                generated_at=now,
                error_code=exc.error_code,
            )
        except ConnectorAccessError as exc:
            section = CardSection(
                status=CardStatus.ERROR,
                generated_at=now,
                error_code=exc.error_code,
                error_message=exc.message,
            )
            logger.info(
                "briefing_section_access_error",
                section=name,
                user_id=str(self.user.id),
                error_code=exc.error_code,
                source=exc.source,
            )
        except Exception as exc:  # safety net
            logger.warning(
                "briefing_section_failed",
                section=name,
                user_id=str(self.user.id),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            section = CardSection(
                status=CardStatus.ERROR,
                generated_at=now,
                error_code=ERROR_CODE_INTERNAL,
            )

        # 3. Persist on cacheable outcomes (skip ttl=0 and ERROR — errors should
        #    retry next request, not be sticky).
        if ttl > 0 and section.status in (
            CardStatus.OK,
            CardStatus.EMPTY,
            CardStatus.NOT_CONFIGURED,
        ):
            await self._write_cache(cache_key, section, ttl)

        briefing_section_status_total.labels(
            section=name, status=section.status.value, origin=_ORIGIN_LIVE
        ).inc()
        return section

    # =========================================================================
    # Redis helpers (defensive — cache is best-effort)
    # =========================================================================

    async def _read_cards_from_cache(self) -> CardsBundle:
        """Read every card section from Redis cache.

        Sections without a cache entry are returned as NOT_CONFIGURED placeholders
        — the LLM helpers will then ignore them when summarizing for the prompt.
        """
        now = datetime.now(UTC)
        sections = await asyncio.gather(
            self._read_cache(f"{BRIEFING_CACHE_PREFIX}:{self.user.id}:{SECTION_WEATHER}"),
            self._read_cache(f"{BRIEFING_CACHE_PREFIX}:{self.user.id}:{SECTION_AGENDA}"),
            self._read_cache(f"{BRIEFING_CACHE_PREFIX}:{self.user.id}:{SECTION_MAILS}"),
            self._read_cache(f"{BRIEFING_CACHE_PREFIX}:{self.user.id}:{SECTION_BIRTHDAYS}"),
            # Reminders are TTL=0 (always live) — synthesis won't have them.
            asyncio.sleep(0, result=None),
            self._read_cache(f"{BRIEFING_CACHE_PREFIX}:{self.user.id}:{SECTION_HEALTH}"),
        )

        def _or_placeholder(s: CardSection | None) -> CardSection:
            return s or CardSection(status=CardStatus.NOT_CONFIGURED, generated_at=now)

        return CardsBundle(
            weather=_or_placeholder(sections[0]),
            agenda=_or_placeholder(sections[1]),
            mails=_or_placeholder(sections[2]),
            birthdays=_or_placeholder(sections[3]),
            reminders=_or_placeholder(sections[4]),
            health=_or_placeholder(sections[5]),
        )

    async def _read_cache(self, key: str) -> CardSection | None:
        try:
            redis = await get_redis_cache()
            raw = await redis.get(key)
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return CardSection.model_validate_json(raw)
        except Exception as exc:
            logger.debug(
                "briefing_cache_read_failed",
                key=key,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None

    async def _write_cache(self, key: str, section: CardSection, ttl: int) -> None:
        try:
            redis = await get_redis_cache()
            await redis.setex(key, ttl, section.model_dump_json())
        except Exception as exc:
            logger.debug(
                "briefing_cache_write_failed",
                key=key,
                error=str(exc),
                error_type=type(exc).__name__,
            )

    # =========================================================================
    # Cache state classification (for the duration histogram label)
    # =========================================================================

    @staticmethod
    def _classify_cache_state(
        *sections_with_ttl: tuple[CardSection, int],
    ) -> str:
        """Return 'cold' / 'warm' / 'partial' for the duration histogram label.

        Heuristic: a section was 'cache-hit' if its generated_at predates the
        request boundary (start of build_today). Reminders (ttl=0) are always
        live and excluded from the count.

        We don't track per-section origin precisely here (that's done by the
        Counter with the ``origin`` label) — this is just a coarse global tag.
        """
        # A section is considered live if its generated_at is within the last
        # second (i.e. fetched in this build). Otherwise it came from cache.
        now = datetime.now(UTC)
        live_count = 0
        cacheable_count = 0
        for section, ttl in sections_with_ttl:
            if ttl <= 0:
                continue
            cacheable_count += 1
            age_seconds = (now - section.generated_at).total_seconds()
            if age_seconds < 1.5:
                live_count += 1
        if cacheable_count == 0:
            return "warm"
        if live_count == 0:
            return "warm"
        if live_count == cacheable_count:
            return "cold"
        return "partial"
