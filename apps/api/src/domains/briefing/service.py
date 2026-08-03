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
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import structlog

from src.core.config import settings

# Moved to core/time_utils (P7) — kept under its historical private name.
from src.core.time_utils import (
    resolve_user_timezone,
)
from src.core.time_utils import (
    seconds_to_next_local_midnight as _seconds_to_next_local_midnight,
)
from src.domains.briefing.constants import (
    BRIEFING_CACHE_PREFIX,
    BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA,
    ERROR_CODE_INTERNAL,
    SECTION_AGENDA,
    SECTION_AGENDA_TTL_SECONDS,
    SECTION_BIRTHDAYS,
    SECTION_BIRTHDAYS_TTL_SECONDS,
    SECTION_DOCUMENTS,
    SECTION_DOCUMENTS_TTL_SECONDS,
    SECTION_FOR_YOU,
    SECTION_FOR_YOU_TTL_SECONDS,
    SECTION_HEALTH,
    SECTION_HEALTH_TTL_SECONDS,
    SECTION_MAILS,
    SECTION_MAILS_TTL_SECONDS,
    SECTION_REMINDERS,
    SECTION_REMINDERS_TTL_SECONDS,
    SECTION_TASKS,
    SECTION_TASKS_TTL_SECONDS,
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
    fetch_documents,
    fetch_for_you,
    fetch_health,
    fetch_mails,
    fetch_reminders,
    fetch_tasks,
    fetch_weather,
)
from src.domains.briefing.llm import generate_greeting, generate_synthesis
from src.domains.briefing.preferences import sanitize_briefing_preferences
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

if TYPE_CHECKING:
    from src.domains.users.models import User

logger = structlog.get_logger(__name__)

# Metric label values for the per-section origin counter. Since D-04 the
# cache/live distinction IS exposed on the wire too (CardSection.from_cache):
# "updated 2 h ago" without saying it came from a cache was freshness theater.
_ORIGIN_LIVE = "live"
_ORIGIN_CACHE = "cache"
_ORIGIN_HIDDEN = "hidden"  # UXR Lot 5 (B4): user-hidden placeholder, zero IO
_ORIGIN_STALE = "stale"  # D-04: last known-good served alongside an ERROR


def _resolve_user_tz(user: User) -> ZoneInfo:
    """Best-effort timezone resolution with safe fallback.

    Delegates to the shared helper: this used to be one of two byte-identical
    copies, and a third caller had to import THIS private symbol to reuse it.
    """
    return resolve_user_timezone(user)


def _has_content(data: Any) -> bool:
    """Return True if the data payload has at least one displayable item."""
    if data is None:
        return False
    for attr in ("events", "items"):
        value = getattr(data, attr, None)
        if value is not None:
            return len(value) > 0
    # ForYouData (P15): three optional sub-blocks — content when any is filled.
    if hasattr(data, "open_loops"):
        return bool(
            getattr(data, "open_loops", None)
            or getattr(data, "recent_automations", None)
            or getattr(data, "next_automation", None)
        )
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
        # UXR Lot 5 (B4): user-hidden sections are pure placeholders — no
        # fetch, no cache IO. Tolerant reader (malformed JSONB → defaults).
        self._hidden_sections = frozenset(
            sanitize_briefing_preferences(getattr(user, "briefing_preferences", None)).hidden
        )

    # =========================================================================
    # Public entry point
    # =========================================================================

    async def build_cards(
        self,
        force_refresh: set[str] | None = None,
    ) -> CardsBundle:
        """Build the 9-card bundle (no LLM call). Fast — returns when cards are ready.

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

        # Fetch all 9 sections in parallel — each independently failable.
        # Each fetcher acquires its own DB session (SQLAlchemy AsyncSession is
        # not safe for concurrent use, see fetchers.py module docstring).
        (
            weather,
            agenda,
            mails,
            birthdays,
            reminders,
            health,
            for_you,
            tasks,
            documents,
        ) = await asyncio.gather(
            self._section(
                SECTION_WEATHER,
                lambda: fetch_weather(user=self.user, user_tz=self.user_tz, language=self.language),
                ttl=SECTION_WEATHER_TTL_SECONDS,
                force=force_all or SECTION_WEATHER in force,
            ),
            self._section(
                SECTION_AGENDA,
                lambda: fetch_agenda(user=self.user, user_tz=self.user_tz, language=self.language),
                ttl=SECTION_AGENDA_TTL_SECONDS,
                force=force_all or SECTION_AGENDA in force,
            ),
            self._section(
                SECTION_MAILS,
                lambda: fetch_mails(user=self.user, user_tz=self.user_tz, language=self.language),
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
            self._section(
                SECTION_FOR_YOU,
                lambda: fetch_for_you(
                    user_id=self.user.id, user_tz=self.user_tz, language=self.language
                ),
                ttl=SECTION_FOR_YOU_TTL_SECONDS,
                force=force_all or SECTION_FOR_YOU in force,
            ),
            self._section(
                SECTION_TASKS,
                lambda: fetch_tasks(user=self.user, user_tz=self.user_tz),
                ttl=SECTION_TASKS_TTL_SECONDS,
                force=force_all or SECTION_TASKS in force,
            ),
            self._section(
                SECTION_DOCUMENTS,
                lambda: fetch_documents(
                    user=self.user, user_tz=self.user_tz, language=self.language
                ),
                ttl=SECTION_DOCUMENTS_TTL_SECONDS,
                force=force_all or SECTION_DOCUMENTS in force,
            ),
        )

        cards = CardsBundle(
            weather=weather,
            agenda=agenda,
            mails=mails,
            birthdays=birthdays,
            reminders=reminders,
            health=health,
            for_you=for_you,
            tasks=tasks,
            documents=documents,
        )

        duration_s = time.perf_counter() - start
        cache_state = self._classify_cache_state(
            (weather, SECTION_WEATHER_TTL_SECONDS),
            (agenda, SECTION_AGENDA_TTL_SECONDS),
            (mails, SECTION_MAILS_TTL_SECONDS),
            (birthdays, SECTION_BIRTHDAYS_TTL_SECONDS),
            (reminders, 0),  # always live
            (health, SECTION_HEALTH_TTL_SECONDS),
            (for_you, SECTION_FOR_YOU_TTL_SECONDS),
            (tasks, SECTION_TASKS_TTL_SECONDS),
            (documents, SECTION_DOCUMENTS_TTL_SECONDS),
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
                SECTION_FOR_YOU: for_you.status.value,
                SECTION_TASKS: tasks.status.value,
                SECTION_DOCUMENTS: documents.status.value,
            },
            forced_refresh=sorted(force),
        )
        return cards

    async def build_text(self, cards: CardsBundle | None = None) -> SynthesisResponse:
        """Build the LLM greeting + synthesis.

        When ``cards`` is None (the standard ``/briefing/synthesis`` path), the
        bundle is read from the Redis cache. When the cache is too sparse —
        typically a cold start where ``/briefing/synthesis`` lands while the
        parallel ``/briefing/cards`` request is still in flight — the cards
        are built inline so the LLM does not see an artificially empty
        dashboard. This keeps the two endpoints independent on the wire while
        making ``/synthesis`` self-sufficient on the data side.

        When ``cards`` is provided (the bundled ``build_today`` / refresh
        path), it is used as-is to avoid rebuilding what the caller already
        produced.

        Returns:
            SynthesisResponse with greeting (always populated, fallback if LLM
            down) and synthesis (None only when the dashboard genuinely has
            fewer than ``BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA`` populated
            sections, or when the LLM call itself fails).
        """
        if cards is None:
            cards = await self.read_cached_cards()

            # Race-aware: if the cache hasn't been populated yet (cold start,
            # or /synthesis racing /cards), the synthesis would be silently
            # skipped because every section reads as NOT_CONFIGURED. Build the
            # cards inline in that case so the LLM has actual data to work
            # with.
            cache_sections_with_data = self._count_sections_with_data(cards)
            if cache_sections_with_data < BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA:
                logger.info(
                    "briefing_synthesis_cache_insufficient_building_inline",
                    user_id=str(self.user.id),
                    cache_sections_with_data=cache_sections_with_data,
                    threshold=BRIEFING_SYNTHESIS_MIN_CARDS_WITH_DATA,
                )
                cards = await self.build_cards()

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
        # Pass the freshly built cards through so build_text doesn't read the
        # cache (which may already be stale for sections we just refreshed)
        # and doesn't trigger its inline-rebuild safety net.
        text = await self.build_text(cards=cards)
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
        # 0. UXR Lot 5 (B4): a user-hidden section short-circuits BEFORE any
        # fetch or cache IO — the economy is the point, not just the display.
        if name in self._hidden_sections:
            briefing_section_status_total.labels(
                section=name, status=CardStatus.HIDDEN.value, origin=_ORIGIN_HIDDEN
            ).inc()
            return CardSection(status=CardStatus.HIDDEN, generated_at=datetime.now(UTC))

        cache_key = f"{BRIEFING_CACHE_PREFIX}:{self.user.id}:{name}"

        # 1. Try cache (skipped when ttl=0 or force=True).
        if ttl > 0 and not force:
            cached = await self._read_cache(cache_key)
            if cached is not None:
                # D-04: say so on the wire — the badge reads "cache", not
                # a false "freshly fetched".
                cached.from_cache = True
                briefing_section_status_total.labels(
                    section=name, status=cached.status.value, origin=_ORIGIN_CACHE
                ).inc()
                return cached

        # 2. Live fetch + status mapping (extracted — CC discipline).
        section = await self._fetch_and_map(name, fetcher)

        # 3. Persist on cacheable outcomes (skip ttl=0 and ERROR — errors should
        #    retry next request, not be sticky).
        if ttl > 0 and section.status in (
            CardStatus.OK,
            CardStatus.EMPTY,
            CardStatus.NOT_CONFIGURED,
        ):
            await self._write_cache(cache_key, section, ttl)

        # 3b. D-04 stale-while-error net. On OK-with-data, remember the payload
        # under a long-TTL side key; on ERROR, serve that last known-good copy
        # ALONGSIDE the error so the card shows dated data instead of a hole.
        # NOT_CONFIGURED never reaches this branch — after a connector
        # disconnect the section raises ConnectorNotConfiguredError, so a
        # stale copy can never leak past a disconnect (no purge needed).
        origin = _ORIGIN_LIVE
        if section.status is CardStatus.OK and section.data is not None:
            await self._write_last_good(name, section)
        elif section.status is CardStatus.ERROR:
            section = await self._attach_stale(name, section)
            if section.data is not None:
                origin = _ORIGIN_STALE

        briefing_section_status_total.labels(
            section=name, status=section.status.value, origin=origin
        ).inc()
        return section

    async def _fetch_and_map(
        self,
        name: str,
        fetcher: Callable[[], Awaitable[Any]],
    ) -> CardSection:
        """Run the live fetch and map the outcome to a CardSection.

        Extracted from ``_section`` (CC discipline). **Never raises** — the
        exception taxonomy maps to statuses; ERROR sections carry
        ``last_attempt_at`` (D-04 honest freshness).
        """
        now = datetime.now(UTC)
        try:
            data = await fetcher()
            return CardSection(
                status=CardStatus.OK if _has_content(data) else CardStatus.EMPTY,
                data=data if _has_content(data) else None,
                generated_at=now,
            )
        except ConnectorNotConfiguredError as exc:
            return CardSection(
                status=CardStatus.NOT_CONFIGURED,
                generated_at=now,
                error_code=exc.error_code,
            )
        except ConnectorAccessError as exc:
            logger.info(
                "briefing_section_access_error",
                section=name,
                user_id=str(self.user.id),
                error_code=exc.error_code,
                source=exc.source,
            )
            return CardSection(
                status=CardStatus.ERROR,
                generated_at=now,
                error_code=exc.error_code,
                error_message=exc.message,
                last_attempt_at=now,
            )
        except Exception as exc:  # safety net
            logger.warning(
                "briefing_section_failed",
                section=name,
                user_id=str(self.user.id),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return CardSection(
                status=CardStatus.ERROR,
                generated_at=now,
                error_code=ERROR_CODE_INTERNAL,
                last_attempt_at=now,
            )

    # =========================================================================
    # Redis helpers (defensive — cache is best-effort)
    # =========================================================================

    async def read_cached_cards(self) -> CardsBundle:
        """Read every card section from Redis cache — NEVER fetching.

        Public because it is a capability of this domain rather than a detail:
        a caller that wants "what we already know, at no cost" (the chat's
        grounded suggestions) must have a way to ask for exactly that, instead
        of reaching into the cache keys itself or calling `build_cards` and
        waking every connector.

        Sections without a cache entry are returned as NOT_CONFIGURED
        placeholders — the LLM helpers ignore them when summarizing for the
        prompt, and the suggestion builder treats them as "no evidence".
        """
        now = datetime.now(UTC)
        sections = await asyncio.gather(
            self._read_section_cache(SECTION_WEATHER),
            self._read_section_cache(SECTION_AGENDA),
            self._read_section_cache(SECTION_MAILS),
            self._read_section_cache(SECTION_BIRTHDAYS),
            # Reminders are TTL=0 (always live) — synthesis won't have them.
            self._read_section_cache(SECTION_REMINDERS, live=True),
            self._read_section_cache(SECTION_HEALTH),
            self._read_section_cache(SECTION_FOR_YOU),
            self._read_section_cache(SECTION_TASKS),
            self._read_section_cache(SECTION_DOCUMENTS),
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
            for_you=_or_placeholder(sections[6]),
            tasks=_or_placeholder(sections[7]),
            documents=_or_placeholder(sections[8]),
        )

    async def _read_section_cache(self, name: str, *, live: bool = False) -> CardSection | None:
        """Per-section cache read honoring hidden preferences (UXR B4).

        Hidden sections return their placeholder without any Redis IO; a
        ``live`` section (TTL=0, never cached) returns None without IO.
        """
        if name in self._hidden_sections:
            return CardSection(status=CardStatus.HIDDEN, generated_at=datetime.now(UTC))
        if live:
            return None
        return await self._read_cache(f"{BRIEFING_CACHE_PREFIX}:{self.user.id}:{name}")

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
            await redis.set(key, section.model_dump_json(), ex=ttl)
        except Exception as exc:
            logger.debug(
                "briefing_cache_write_failed",
                key=key,
                error=str(exc),
                error_type=type(exc).__name__,
            )

    # =========================================================================
    # D-04 stale-while-error net (last known-good side cache)
    # =========================================================================

    def _last_good_key(self, name: str) -> str:
        return f"{BRIEFING_CACHE_PREFIX}:lastgood:{self.user.id}:{name}"

    async def _write_last_good(self, name: str, section: CardSection) -> None:
        """Remember an OK-with-data payload under the long-TTL side key.

        Best-effort like every cache write. TTL 0 disables the net entirely.
        """
        ttl = settings.briefing_last_good_ttl_seconds
        if ttl <= 0:
            return
        await self._write_cache(self._last_good_key(name), section, ttl)

    async def _attach_stale(self, name: str, section: CardSection) -> CardSection:
        """Fill an ERROR section with the last known-good payload, if any.

        The error stays the STATUS (code, message, CTA all keep working); the
        stale payload rides along with its own original timestamp so the card
        can say "data from 09:12 — connector unreachable" instead of showing
        a hole. A miss returns the section unchanged.
        """
        stale = await self._read_cache(self._last_good_key(name))
        if stale is None or stale.data is None:
            return section
        section.data = stale.data
        section.stale_generated_at = stale.generated_at
        return section

    # =========================================================================
    # Cache state classification (for the duration histogram label)
    # =========================================================================

    @staticmethod
    def _count_sections_with_data(cards: CardsBundle) -> int:
        """Return the number of card sections whose status is OK.

        Used by ``build_text`` to decide whether the Redis cache is rich
        enough to feed the synthesis LLM, or whether cards must be built
        inline first.
        """
        return sum(
            1
            for section in (
                cards.weather,
                cards.agenda,
                cards.mails,
                cards.birthdays,
                cards.reminders,
                cards.health,
            )
            if section.status == CardStatus.OK
        )

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
