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
import uuid
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, NamedTuple
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
from src.domains.briefing.cache_keys import last_good_key, section_cache_key
from src.domains.briefing.constants import (
    BRIEFING_SHARED_BUILD_WAIT_SECONDS,
    ERROR_CODE_INTERNAL,
    SECTION_AGENDA,
    SECTION_AGENDA_TTL_SECONDS,
    SECTION_BIRTHDAYS,
    SECTION_DOCUMENTS,
    SECTION_DOCUMENTS_TTL_SECONDS,
    SECTION_FOR_YOU,
    SECTION_FOR_YOU_TTL_SECONDS,
    SECTION_HEALTH,
    SECTION_HEALTH_TTL_SECONDS,
    SECTION_MAILS,
    SECTION_MAILS_TTL_SECONDS,
    SECTION_NAMES,
    SECTION_REMINDERS,
    SECTION_REMINDERS_TTL_SECONDS,
    SECTION_TASKS,
    SECTION_TASKS_TTL_SECONDS,
    SECTION_WEATHER,
    SECTION_WEATHER_TTL_SECONDS,
)
from src.domains.briefing.consultations import SURFACE as BRIEFING_SURFACE
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
from src.domains.shared.consultation_sink import consultation_collector
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.observability.metrics_briefing import (
    briefing_build_duration_seconds,
    briefing_bundle_builds_total,
    briefing_refresh_requests_total,
    briefing_section_status_total,
)
from src.infrastructure.utils.shared_flight import CLAIM_PREFIX, run_shared_flight
from src.infrastructure.utils.single_flight import run_single_flight

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

# Whether a caller gathered the bundle or shared one already being gathered.
_BUILD_OWNED = "owned"
_BUILD_JOINED = "joined"


class _SectionPlan(NamedTuple):
    """How one section is obtained during a build.

    Attributes:
        name: Section name, as declared in ``SECTION_NAMES``.
        fetcher: Produces the live payload when the cache is not used.
        ttl: How long a successful outcome stays in the cache. Always > 0:
            a section that is never written is invisible to the readers that
            only read the cache.
        force: Bypass the cache READ for this build.
        cache_eligible: Whether being served from cache is a possible outcome
            for this section. False for the always-live one, which would
            otherwise make every build look 'partial' in the duration
            histogram — a section that can never be a cache hit says nothing
            about how warm the cache is.
    """

    name: str
    fetcher: Callable[[], Awaitable[Any]]
    ttl: int
    force: bool
    cache_eligible: bool = True


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
        # One correlation key per service instance, so a bundle's consultations
        # are one readable act rather than nine unrelated reads.
        self._consultation_run_id = f"briefing_cards_{uuid.uuid4().hex[:12]}"

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
        greeting + synthesis (handled by ``build_text``).

        **One page load is one act of reading.** ``/briefing/cards`` and
        ``/briefing/synthesis`` are issued in parallel by the dashboard and
        both want this bundle, so the gathering is coalesced: whoever asks
        first builds it, whoever asks while it is running is handed the very
        same object. Measured on the running instance before this seam existed,
        44 of 151 bundle builds over seven days were duplicates — every
        connector called twice within the same second, and two batches of
        consultation rows filed for a single act.

        Wrapped in the consultation register: the sections that were actually
        READ — never the ones served from cache, hidden by the person, or
        gathered by another caller — are collected here and written once, so
        the account holder can see which of their sources LIA opened and when.

        Args:
            force_refresh: Set of section names to bypass cache for.

        Returns:
            CardsBundle ready for the UI.
        """
        # A shared build is shielded, so it outlives a caller that disconnects
        # — and it then reads ``self.user`` from a request whose session has
        # been closed. That is safe here, and not by luck: the sessionmaker
        # sets ``expire_on_commit=False``, ``User`` declares no deferred
        # column, and the whole build path touches loaded COLUMNS only (id,
        # language, timezone, the health toggle, the home location) — never a
        # relationship, which is the access that would lazy-load off a
        # detached instance. Every fetcher opens its own session anyway.
        # Adding a relationship read below would break that, silently.
        force = frozenset(force_refresh or ())
        # The collector costs NOTHING on the common path: a page load served
        # entirely from cache collects no row, and the flush returns before
        # opening a session. Only a load that actually opened a source pays for
        # the write — and that load already paid for the network fetches.
        #
        # A caller that JOINS collects nothing: the shared task runs in the
        # context of the caller that started it, so the rows land in that
        # caller's live list. That is the honest record — one act, one set of
        # consultations, one decision — and it is why the register stopped
        # double-counting the home page without a line of register code.
        if force:
            # Counted per REQUEST, which is what the metric says it counts —
            # and it has to be outside the coalescing seam to stay true: two
            # people double-clicking "refresh all" at the same instant share
            # one build, and a counter placed inside it would report one
            # refresh where two were asked for.
            scope = "all" if "all" in force else "single"
            briefing_refresh_requests_total.labels(scope=scope).inc()

        async with consultation_collector(self._consultation_run_id) as consulted:
            flight = await run_single_flight(
                self._flight_key(force), lambda: self._gather_once_per_deployment(force)
            )
            read_something = bool(consulted)
        briefing_bundle_builds_total.labels(
            outcome=_BUILD_JOINED if flight.joined else _BUILD_OWNED
        ).inc()
        if read_something:
            await self._record_cards_turn()
        return flight.value

    async def _gather_once_per_deployment(self, force: frozenset[str]) -> CardsBundle:
        """Gather the bundle once across WORKERS, not merely once per process.

        ``run_single_flight`` shares the work between callers on one event
        loop, and production runs four of them (``WEB_CONCURRENCY=4``), so the
        two requests of a page load usually land on different workers — measured
        on the deployed instance 2026-09-07: three overlapping pairs, none
        joined, and ``briefing:mails`` opened five times for two page loads.

        So one worker claims the build and the others wait for what it
        publishes, which is the section cache it fills anyway — no payload of
        this seam's own travels through Redis. A waiter loses nothing it would
        not have spent building the same bundle, and the sources are opened
        once.

        A FORCED refresh never waits: the caller asked to bypass the cache, and
        handing it what another build published is exactly the cache it
        refused.

        Args:
            force: Section names whose cache this build bypasses.

        Returns:
            The bundle, built here or published by the worker that claimed it.
        """
        if force:
            return await self._gather_cards(force)

        shared = await run_shared_flight(
            self._claim_key(),
            build=lambda: self._gather_cards(force),
            read_shared=self._published_bundle,
            wait_budget_s=BRIEFING_SHARED_BUILD_WAIT_SECONDS,
        )
        return shared.value

    def _claim_key(self) -> str:
        """The cross-worker claim's identity.

        The same identity as the in-process flight, flattened to a string and
        carrying its declared family head: a claim shared between two builds
        that would produce different bundles would hand one caller the other's
        answer, and a key whose family only appears after a helper prepends it
        is a key the ADR-260 guard cannot read.
        """
        hidden = ",".join(sorted(self._hidden_sections))
        return (
            f"{CLAIM_PREFIX}:briefing_bundle:{self.user.id}"
            f":{self.language}:{self.user_tz}:{hidden}"
        )

    async def _published_bundle(self) -> CardsBundle | None:
        """The bundle another worker has finished publishing, or None.

        « Finished » is the whole point: a partially written cache would hand
        the waiter a bundle with holes, which is worse than the duplicate build
        it is avoiding. Nothing missing means the holder wrote every visible
        section — reminders included, which is why that section needed a TTL of
        its own.
        """
        bundle, missing = await self._read_cached_bundle()
        return None if missing else bundle

    def _flight_key(self, force: frozenset[str]) -> tuple[object, ...]:
        """What makes two bundle builds the same work.

        Everything that changes the bundle belongs here: a key that is too
        coarse hands a caller a bundle built for someone else, or in another
        language, which is worse than building it twice. A forced refresh
        therefore never joins an unforced build — joining would silently
        ignore the force and return the cache the caller asked to bypass.

        Args:
            force: Sections whose cache this build bypasses.

        Returns:
            A hashable identity for the coalescing registry.
        """
        return (
            "briefing_bundle",
            self.user.id,
            self.language,
            str(self.user_tz),
            self._hidden_sections,
            force,
        )

    async def _record_cards_turn(self) -> None:
        """File the act the consultations belong to.

        Only when at least one source was actually read: a page load served
        entirely from cache opened nothing, and a register row for it would
        claim a read that never happened.

        Never raises — the dashboard is already built when this runs.
        """
        try:
            from src.domains.agents.effects.decision_recorder import record_decision
            from src.domains.agents.effects.decisions import out_of_turn_decision
            from src.domains.agents.effects.models import DecisionOutcome, EffectSource

            decision = out_of_turn_decision(
                run_id=self._consultation_run_id,
                user_id=self.user.id,
                thread_id=self._consultation_run_id,
                # A request reached the API; nothing schedules the briefing.
                source=EffectSource.USER.value,
            )
            decision.outcome = DecisionOutcome.ANSWERED
            decision.route = "briefing_cards"
            await record_decision(decision)
        except Exception as exc:  # noqa: BLE001 - observing never breaks the observed
            logger.warning(
                "briefing_cards_decision_not_recorded",
                run_id=self._consultation_run_id,
                error_type=type(exc).__name__,
            )

    def _build_plan(self, force: frozenset[str]) -> tuple[_SectionPlan, ...]:
        """How each of the nine sections is obtained for this build.

        One declaration, read by everything downstream: the gather, the
        duration histogram's cold/warm verdict and the structured log all
        derive from it. They used to list the nine names each in their own
        shape — a bundle, a tuple of TTLs and a dict — which is three places
        for a section to be added to two of them.

        Args:
            force: Section names whose cache this build bypasses.

        Returns:
            One plan per section, in gather order.
        """
        force_all = "all" in force

        def forced(name: str) -> bool:
            return force_all or name in force

        return (
            _SectionPlan(
                SECTION_WEATHER,
                lambda: fetch_weather(user=self.user, user_tz=self.user_tz, language=self.language),
                SECTION_WEATHER_TTL_SECONDS,
                forced(SECTION_WEATHER),
            ),
            _SectionPlan(
                SECTION_AGENDA,
                lambda: fetch_agenda(user=self.user, user_tz=self.user_tz, language=self.language),
                SECTION_AGENDA_TTL_SECONDS,
                forced(SECTION_AGENDA),
            ),
            _SectionPlan(
                SECTION_MAILS,
                lambda: fetch_mails(user=self.user, user_tz=self.user_tz, language=self.language),
                SECTION_MAILS_TTL_SECONDS,
                forced(SECTION_MAILS),
            ),
            _SectionPlan(
                SECTION_BIRTHDAYS,
                lambda: fetch_birthdays(user=self.user, user_tz=self.user_tz),
                # Birthday cards pre-compute `days_until`, so the cache MUST
                # expire at local midnight — otherwise a value cached on day N
                # still advertises the same "N days" on day N+1 until the next
                # manual refresh. Cap hard at 24 h as a belt-and-braces safety.
                _seconds_to_next_local_midnight(self.user_tz),
                forced(SECTION_BIRTHDAYS),
            ),
            _SectionPlan(
                SECTION_REMINDERS,
                lambda: fetch_reminders(
                    user_id=self.user.id,
                    user_tz=self.user_tz,
                    language=self.language,
                ),
                SECTION_REMINDERS_TTL_SECONDS,
                # Always live — a local DB lookup under 10 ms, and a reminder
                # created a moment ago must appear now. The TTL only makes the
                # section READABLE by the cache-only readers; it never serves
                # this card.
                True,
                cache_eligible=False,
            ),
            _SectionPlan(
                SECTION_HEALTH,
                lambda: fetch_health(user=self.user),
                SECTION_HEALTH_TTL_SECONDS,
                forced(SECTION_HEALTH),
            ),
            _SectionPlan(
                SECTION_FOR_YOU,
                lambda: fetch_for_you(
                    user_id=self.user.id, user_tz=self.user_tz, language=self.language
                ),
                SECTION_FOR_YOU_TTL_SECONDS,
                forced(SECTION_FOR_YOU),
            ),
            _SectionPlan(
                SECTION_TASKS,
                lambda: fetch_tasks(user=self.user, user_tz=self.user_tz),
                SECTION_TASKS_TTL_SECONDS,
                forced(SECTION_TASKS),
            ),
            _SectionPlan(
                SECTION_DOCUMENTS,
                lambda: fetch_documents(
                    user=self.user, user_tz=self.user_tz, language=self.language
                ),
                SECTION_DOCUMENTS_TTL_SECONDS,
                forced(SECTION_DOCUMENTS),
            ),
        )

    async def _gather_cards(self, force: frozenset[str]) -> CardsBundle:
        """Fetch the nine sections in parallel and assemble the bundle.

        Runs inside the coalescing seam (see ``build_cards``): at most one
        execution of this method per identity is in flight at any moment, so
        every counter and log line below describes ONE act of reading.

        Args:
            force: Section names whose cache this build bypasses.

        Returns:
            CardsBundle ready for the UI.
        """
        start = time.perf_counter()

        # Fetch all 9 sections in parallel — each independently failable.
        # Each fetcher acquires its own DB session (SQLAlchemy AsyncSession is
        # not safe for concurrent use, see fetchers.py module docstring).
        plans = self._build_plan(force)
        results = await asyncio.gather(
            *(
                self._section(plan.name, plan.fetcher, ttl=plan.ttl, force=plan.force)
                for plan in plans
            )
        )
        sections = dict(zip((plan.name for plan in plans), results, strict=True))
        cards = CardsBundle(**sections)

        duration_s = time.perf_counter() - start
        cache_state = self._classify_cache_state(
            (sections[plan.name], plan.cache_eligible) for plan in plans
        )
        briefing_build_duration_seconds.labels(cache_state=cache_state).observe(duration_s)
        logger.info(
            "briefing_cards_built",
            user_id=str(self.user.id),
            duration_ms=int(duration_s * 1000),
            cache_state=cache_state,
            sections_status={name: section.status.value for name, section in sections.items()},
            forced_refresh=sorted(force),
        )
        return cards

    async def build_text(self, cards: CardsBundle | None = None) -> SynthesisResponse:
        """Build the LLM greeting + synthesis.

        When ``cards`` is None (the standard ``/briefing/synthesis`` path), the
        bundle is read from the Redis cache, and BUILT when the cache is
        missing any visible section.

        The question asked here is "has this bundle been built?", never "does
        it hold anything interesting?". They read alike and are not the same:
        the second one cannot tell a cold cache from a legitimately quiet day,
        and answering it is how ``/synthesis`` came to rebuild the whole
        dashboard on every call for anyone whose morning was empty, while a
        second implementation of the same threshold — this one counting six
        sections, the LLM helper counting nine — decided "too sparse" about
        bundles the synthesis would have summarised.

        Building here is not a duplicate of ``/briefing/cards``: the gathering
        is coalesced (see ``build_cards``), so on a page load this joins the
        build already running and both responses describe the very same
        bundle. Whether the synthesis is worth generating at all remains the
        LLM helper's decision, in the one place that owns it.

        When ``cards`` is provided (the bundled ``build_today`` / refresh
        path), it is used as-is to avoid rebuilding what the caller already
        produced.

        Args:
            cards: An already-built bundle, or None to obtain one.

        Returns:
            SynthesisResponse with greeting (always populated, fallback if LLM
            down) and synthesis (None when the dashboard genuinely has too few
            populated sections, or when the LLM call itself fails).
        """
        if cards is None:
            cards, missing = await self._read_cached_bundle()
            if missing:
                logger.info(
                    "briefing_synthesis_bundle_not_cached",
                    user_id=str(self.user.id),
                    missing_sections=sorted(missing),
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

    def _record_consultation(self, name: str, section: CardSection, started: float) -> None:
        """Tell the register which source was actually read, and how it went.

        The briefing calls fetchers, not tools, so the tool gate that fills the
        consultation register never sees it — its reads were absent by
        construction. And the briefing answers a REQUEST: nothing schedules it
        (verified on the call graph, 2026-09-07), so the authorship is the
        person's, not an initiative of LIA's.

        Args:
            name: Section key.
            section: What the fetch produced.
            started: ``time.perf_counter()`` taken before the fetch.
        """
        # ``_section`` is documented « Never raises. », and that contract is the
        # dashboard's: a register that can take the home page down is worse
        # than the gap it closes. ``record_surface_consultations`` is
        # best-effort in full, but the status read below is not, so the whole
        # body stays guarded.
        try:
            # OK and EMPTY both mean the source answered; NOT_CONFIGURED and
            # ERROR mean it could not be read. « Nothing to report » is not
            # « I could not look », and the register must not merge them.
            answered = section.status in (CardStatus.OK, CardStatus.EMPTY)
            record_surface_consultations(
                surface=BRIEFING_SURFACE,
                user_id=self.user.id,
                run_id=self._consultation_run_id,
                opened=[name],
                failed=() if answered else [name],
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001 - observing never breaks the observed
            logger.debug(
                "briefing_consultation_not_recorded",
                section=name,
                error_type=type(exc).__name__,
            )

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

        cache_key = self._cache_key(name)

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
        # Only THIS branch is a consultation: a cache hit above reads Redis,
        # not the person's mailbox, and a hidden section never runs at all.
        started = time.perf_counter()
        section = await self._fetch_and_map(name, fetcher)
        self._record_consultation(name, section, started)

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

    def _cache_key(self, name: str) -> str:
        """The cache key of one section.

        Built by ``briefing.cache_keys``, never here: the push invalidation in
        another domain deletes the very same keys, and a second builder is how
        one of them silently stopped matching.

        Args:
            name: Section name.

        Returns:
            The fully scoped Redis key.
        """
        return section_cache_key(user_id=self.user.id, language=self.language, section=name)

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
        cards, _missing = await self._read_cached_bundle()
        return cards

    async def _read_cached_bundle(self) -> tuple[CardsBundle, frozenset[str]]:
        """Read the bundle from cache, and say which sections were absent.

        The absence is the useful half: it is what tells a caller whether the
        bundle has been BUILT recently, which is a different question from
        whether it is INTERESTING. Conflating the two is what made a quiet
        dashboard indistinguishable from a cold cache, and had ``/synthesis``
        rebuild everything on every single call for anyone whose day happened
        to be empty.

        A hidden section is never fetched, so its absence is not a gap. A
        section that FAILED is not written either (an error must retry, not
        stick), so a failing connector does read as absent — the honest
        consequence is one extra gather, which on a page load costs nothing
        because it is coalesced with the one ``/cards`` is already running.

        Returns:
            The bundle, and the names of the visible sections the cache had no
            entry for.
        """
        now = datetime.now(UTC)
        results = await asyncio.gather(*(self._read_section_cache(name) for name in SECTION_NAMES))
        by_name = dict(zip(SECTION_NAMES, results, strict=True))
        missing = frozenset(name for name, section in by_name.items() if section is None)

        def _or_placeholder(name: str) -> CardSection:
            return by_name[name] or CardSection(status=CardStatus.NOT_CONFIGURED, generated_at=now)

        bundle = CardsBundle(**{name: _or_placeholder(name) for name in SECTION_NAMES})
        return bundle, missing

    async def _read_section_cache(self, name: str) -> CardSection | None:
        """Per-section cache read honoring hidden preferences (UXR B4).

        Args:
            name: Section name.

        Returns:
            The cached section, a HIDDEN placeholder when the person hid it
            (no Redis IO at all), or None when the cache holds nothing.
        """
        if name in self._hidden_sections:
            return CardSection(status=CardStatus.HIDDEN, generated_at=datetime.now(UTC))
        return await self._read_cache(self._cache_key(name))

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
        """The long-TTL side key holding this section's last known-good payload."""
        return last_good_key(user_id=self.user.id, language=self.language, section=name)

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
    def _classify_cache_state(
        outcomes: Iterable[tuple[CardSection, bool]],
    ) -> str:
        """Return 'cold' / 'warm' / 'partial' for the duration histogram label.

        Heuristic: a section was a cache hit if its ``generated_at`` predates
        this build. Sections that can never be cache hits (the always-live one)
        are excluded — counting them would report every build as 'partial'.

        This is a coarse global tag; per-section origin is what the
        ``origin`` label on ``briefing_section_status_total`` carries.

        Args:
            outcomes: Each built section and whether a cache hit was possible
                for it.

        Returns:
            One of 'cold', 'warm', 'partial'.
        """
        now = datetime.now(UTC)
        live_count = 0
        eligible_count = 0
        for section, cache_eligible in outcomes:
            if not cache_eligible:
                continue
            eligible_count += 1
            if (now - section.generated_at).total_seconds() < 1.5:
                live_count += 1
        if eligible_count == 0 or live_count == 0:
            return "warm"
        if live_count == eligible_count:
            return "cold"
        return "partial"
