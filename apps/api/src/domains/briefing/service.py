"""BriefingService — orchestrates source fetchers, cache, and LLM helpers.

Lecture pure: no LangGraph, no DB model, no migration. Sources are fetched in
parallel via asyncio.gather. Cacheable sections use source-specific Redis TTLs.

Two LLM calls (greeting + synthesis) run in parallel after the cards are
assembled. Both are non-fatal: failures fall back to a static greeting and a
None synthesis so the dashboard always renders.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import structlog

from src.core.config import settings
from src.core.i18n import normalize_language

# Moved to core/time_utils (P7) — kept under its historical private name.
from src.core.time_utils import (
    resolve_user_timezone,
)
from src.core.time_utils import (
    seconds_to_next_local_midnight as _seconds_to_next_local_midnight,
)
from src.domains.briefing.act_decision import file_briefing_act
from src.domains.briefing.cache_keys import EDITORIAL_MAILS_SECTION
from src.domains.briefing.cache_state import classify_cache_state
from src.domains.briefing.cached_cards import cached_cards_bundle, published_cards_bundle
from src.domains.briefing.card_content import _has_content as _has_content
from src.domains.briefing.constants import (
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
    SECTION_SMS,
    SECTION_TASKS,
    SECTION_TASKS_TTL_SECONDS,
    SECTION_WEATHER,
    SECTION_WEATHER_TTL_SECONDS,
    SECTION_WORKBOARD,
    SECTION_WORKBOARD_TTL_SECONDS,
)
from src.domains.briefing.consultations import SURFACE as BRIEFING_SURFACE
from src.domains.briefing.consultations import SectionReadObserver
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
    fetch_workboard,
)
from src.domains.briefing.llm import generate_greeting, generate_synthesis
from src.domains.briefing.preferences import sanitize_briefing_preferences
from src.domains.briefing.schemas import (
    BriefingResponse,
    BriefingWindows,
    CardsBundle,
    CardSection,
    CardStatus,
    MailsData,
    SynthesisResponse,
    TextSection,
)
from src.domains.briefing.section_outcomes import (
    SectionKeys,
    fetch_and_map,
    persist_live_outcome,
    read_generation,
    read_section,
    read_settled_section,
    section_keys,
)
from src.domains.briefing.selected_cards import SectionPlan as _SectionPlan
from src.domains.briefing.selected_cards import selected_cards_bundle
from src.domains.briefing.sms_context import (
    PromptSms,
    fetch_sms,
    read_prompt_sms,
    revalidate_sms_card,
)
from src.domains.shared.consultation_sink import consultation_collector
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.infrastructure.observability.metrics_briefing import (
    briefing_build_duration_seconds,
    briefing_bundle_builds_total,
    briefing_refresh_requests_total,
    briefing_section_status_total,
)
from src.infrastructure.proactive.tracking import out_of_turn_spend
from src.infrastructure.utils.shared_flight import CLAIM_PREFIX, run_shared_flight
from src.infrastructure.utils.single_flight import run_single_flight

if TYPE_CHECKING:
    from src.domains.users.models import User

logger = structlog.get_logger(__name__)

# Metric label values for the per-section origin counter. Since D-04 the
# cache/live distinction IS exposed on the wire too (CardSection.from_cache):
# "updated 2 h ago" without saying it came from a cache was freshness theater.
# The live and stale origins are decided where the read is persisted.
_ORIGIN_CACHE = "cache"
_ORIGIN_HIDDEN = "hidden"  # UXR Lot 5 (B4): user-hidden placeholder, zero IO

# Whether a caller gathered the bundle or shared one already being gathered.
_BUILD_OWNED = "owned"
_BUILD_JOINED = "joined"


def _resolve_user_tz(user: User) -> ZoneInfo:
    """Best-effort timezone resolution with safe fallback.

    Delegates to the shared helper: this used to be one of two byte-identical
    copies, and a third caller had to import THIS private symbol to reuse it.
    """
    return resolve_user_timezone(user)


def build_briefing_windows() -> BriefingWindows:
    """The windows the fetchers read from settings, published with the cards.

    Returns:
        One ``BriefingWindows`` built from the live settings — the same values
        ``fetch_birthdays``, ``fetch_health`` and the others pass to their sources.
    """
    return BriefingWindows(
        birthdays_horizon_days=settings.briefing_max_birthdays_horizon_days,
        health_window_days=settings.briefing_health_window_days,
        agenda_lookahead_hours=settings.briefing_agenda_lookahead_hours,
        tasks_horizon_days=settings.briefing_tasks_horizon_days,
        weather_forecast_days=settings.briefing_weather_daily_forecast_days,
    )


class BriefingService:
    """Orchestrator for the Today briefing.

    Lifetime: created per request (cheap — only holds the user reference).

    No db session is held by the service: each fetcher acquires its own session
    via ``get_db_context()`` to allow safe concurrent execution under
    asyncio.gather (SQLAlchemy AsyncSession does not support concurrent
    operations on a single session).
    """

    def __init__(self, user: User, *, exclude_commercial_mails: bool = False) -> None:
        self.user = user
        self._exclude_commercial_mails = exclude_commercial_mails
        self.user_tz = _resolve_user_tz(user)
        self.language = normalize_language(user.language)
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
        """Build the card bundle (no LLM call). Fast — returns when cards are ready.

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

        # The spend ledger is fed around the whole act, like the consultation
        # register: the weather card reads Google Weather on the deployment's
        # key, and a paid call with no ambient tracker was dropped in silence
        # (2026-09-19). A joiner's tracker stays empty — the shared build runs
        # in the owner's context — and an empty tracker persists nothing.
        async with (
            consultation_collector(self._consultation_run_id) as consulted,
            out_of_turn_spend(self._consultation_run_id, self.user.id, "briefing_cards"),
        ):
            flight = await run_single_flight(
                self._flight_key(force), lambda: self._gather_once_per_deployment(force)
            )
            read_something = bool(consulted)
        briefing_bundle_builds_total.labels(
            outcome=_BUILD_JOINED if flight.joined else _BUILD_OWNED
        ).inc()
        if read_something:
            await self._record_cards_turn()
        return await revalidate_sms_card(flight.value)

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

        # Owner liveness (spec 2026-10-21 §5.7): a waiter keeps waiting while the
        # owner's claim is alive and builds once it is gone without a complete
        # bundle — one re-claiming waiter, not every waiter after a fixed timer.
        shared = await run_shared_flight(
            self._claim_key(),
            build=lambda: self._gather_cards(force),
            read_shared=self._published_bundle,
            read_settled=self._settled_bundle,
            wait_budget_s=settings.briefing_shared_build_max_wait_seconds,
            owner_liveness=True,
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
        mode = ":editorial-mails-v1" if self._exclude_commercial_mails else ""
        return (
            f"{CLAIM_PREFIX}:briefing_bundle:{self.user.id}"
            f":{self.language}:{self.user_tz}:{hidden}{mode}"
        )

    async def _published_bundle(self) -> CardsBundle | None:
        """The bundle another worker has finished publishing, or None.

        « Finished » is the whole point: a partially written cache would hand
        the waiter a bundle with holes, which is worse than the duplicate build
        it is avoiding. Nothing missing means the holder wrote every visible
        section — reminders included, which is why that section needed a TTL of
        its own.
        """
        return await published_cards_bundle(self._read_section_cache)

    async def _settled_bundle(self) -> CardsBundle | None:
        """What a WAITING worker accepts: the bundle, a recently failed section settled.

        The owner's own look (``_published_bundle``) never counts an attempt
        marker, so the next owner retries the failed source live; a waiter of
        the same build accepts it instead of waiting out its budget (E12).
        """
        return await published_cards_bundle(self._read_settled_section)

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
            self._exclude_commercial_mails,
        )

    async def _record_cards_turn(
        self, *, run_id: str | None = None, route: str = "briefing_cards"
    ) -> None:
        """File the act the consultations belong to (``act_decision``). Never raises."""
        await file_briefing_act(
            user_id=self.user.id, run_id=run_id or self._consultation_run_id, route=route
        )

    def _build_plan(
        self, force: frozenset[str], *, sms_previews: bool = False
    ) -> tuple[_SectionPlan, ...]:
        """How each section of the grid is obtained for this build.

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
                self._fetch_mails,
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
                SECTION_SMS,
                lambda: fetch_sms(user_id=self.user.id, include_messages=sms_previews),
                0,
                True,
                cache_eligible=False,
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
            _SectionPlan(
                SECTION_WORKBOARD,
                lambda: fetch_workboard(user_id=self.user.id),
                SECTION_WORKBOARD_TTL_SECONDS,
                # Always live, like the reminders: a ticket answered a moment
                # ago must stop reading « waits on you » now.
                True,
                cache_eligible=False,
            ),
        )

    async def _gather_cards(self, force: frozenset[str]) -> CardsBundle:
        """Fetch every section in parallel and assemble the bundle.

        Runs inside the coalescing seam (see ``build_cards``): at most one
        execution of this method per identity is in flight at any moment, so
        every counter and log line below describes ONE act of reading.

        Args:
            force: Section names whose cache this build bypasses.

        Returns:
            CardsBundle ready for the UI.
        """
        start = time.perf_counter()

        # Fetch every section in parallel — each independently failable.
        # Each fetcher acquires its own DB session (SQLAlchemy AsyncSession is
        # not safe for concurrent use, see fetchers.py module docstring).
        plans = self._build_plan(force, sms_previews=True)
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

        text_run_id = f"briefing_text_{uuid.uuid4().hex[:12]}"
        async with consultation_collector(text_run_id) as consulted:
            # ONE SMS read for both prompts (E13); each still checks consent.
            prompt_sms = await read_prompt_sms(self.user.id, cards.sms)
            text = await self.compose_text(cards, prompt_sms)
        if consulted:
            await self._record_cards_turn(run_id=text_run_id, route="briefing_text")
        return text

    async def compose_text(self, cards: CardsBundle, prompt_sms: PromptSms) -> SynthesisResponse:
        """The greeting and synthesis of a bundle: the two model calls, nothing else read."""
        (greeting_text, greeting_usage), (synthesis_text, synthesis_usage) = await asyncio.gather(
            generate_greeting(
                user=self.user,
                user_tz=self.user_tz,
                cards=cards,
                language=self.language,
                prompt_sms=prompt_sms,
            ),
            generate_synthesis(
                user=self.user,
                user_tz=self.user_tz,
                cards=cards,
                language=self.language,
                prompt_sms=prompt_sms,
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
        # Text generation may outlive an erasure after the cards' first check.
        cards = await revalidate_sms_card(cards)
        return BriefingResponse(
            greeting=text.greeting,
            synthesis=text.synthesis,
            cards=cards,
            windows=build_briefing_windows(),
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
        respect_hidden: bool = True,
        record: bool = True,
        on_read: SectionReadObserver | None = None,
    ) -> CardSection:
        """Wrap a fetcher with cache + status mapping. **Never raises.**"""
        # 0. UXR Lot 5 (B4): a user-hidden section short-circuits BEFORE any
        # fetch or cache IO — the economy is the point, not just the display.
        if respect_hidden and name in self._hidden_sections:
            briefing_section_status_total.labels(
                section=name, status=CardStatus.HIDDEN.value, origin=_ORIGIN_HIDDEN
            ).inc()
            return CardSection(status=CardStatus.HIDDEN, generated_at=datetime.now(UTC))

        keys = self._section_keys(name)

        # 1. Try cache (skipped when ttl=0 or force=True). An attempt marker is
        #    NOT read here: the cards retry a failed source live.
        if ttl > 0 and not force:
            cached = await self._read_cache(keys.cache)
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
        # The push generation is read BEFORE the fetch: the write after it is
        # refused when a push invalidated the section meanwhile (E5).
        generation = await read_generation(keys.generation) if ttl > 0 else None
        section = await self._read_live_section(name, fetcher, record=record, on_read=on_read)

        # 3. Persist (section_outcomes): the cache on cacheable outcomes, the
        #    D-04 last known-good copy, and for an ERROR its stale copy plus the
        #    attempt marker the completeness readers settle on. NOT_CONFIGURED
        #    never gets a stale copy: a disconnect cannot leak one.
        section, origin = await persist_live_outcome(
            name, section, keys=keys, ttl=ttl, generation=generation
        )

        briefing_section_status_total.labels(
            section=name, status=section.status.value, origin=origin
        ).inc()
        return section

    async def _read_live_section(
        self,
        name: str,
        fetcher: Callable[[], Awaitable[Any]],
        *,
        record: bool,
        on_read: SectionReadObserver | None,
    ) -> CardSection:
        """Close each live read even on cancellation, before cache writes or siblings finish."""
        started = time.perf_counter()
        section = CardSection(status=CardStatus.ERROR, generated_at=datetime.now(UTC))
        try:
            section = await self._fetch_and_map(name, fetcher)
            return section
        finally:
            if record:
                self._record_consultation(name, section, started)
            if on_read is not None:
                try:
                    on_read(name, section.status)
                except Exception as exc:  # noqa: BLE001 — observing never breaks the read
                    logger.warning(
                        "briefing_read_observer_failed",
                        section=name,
                        error_type=type(exc).__name__,
                    )

    async def _fetch_and_map(
        self,
        name: str,
        fetcher: Callable[[], Awaitable[Any]],
    ) -> CardSection:
        """Run the live fetch and map its outcome (``section_outcomes``). **Never raises**."""
        return await fetch_and_map(name, fetcher, user_id=self.user.id)

    # =========================================================================
    # Redis helpers (defensive — cache is best-effort)
    # =========================================================================

    def _cache_key(self, name: str) -> str:
        """The cache key of one section (built by ``briefing.cache_keys``)."""
        return self._section_keys(name).cache

    def _section_keys(self, name: str) -> SectionKeys:
        """Every key of one section, built by ``briefing.cache_keys`` and never here.

        The push invalidation in another domain deletes the very same keys, and
        a second builder is how one of them silently stopped matching.

        Args:
            name: Section name.

        Returns:
            The section's cache, last-good, attempt-marker and generation keys.
        """
        return section_keys(
            user_id=self.user.id,
            language=self.language,
            section=name,
            cache_section=self._cache_section(name),
        )

    def _cache_section(self, name: str) -> str:
        return (
            EDITORIAL_MAILS_SECTION
            if name == SECTION_MAILS and self._exclude_commercial_mails
            else name
        )

    async def _fetch_mails(self) -> MailsData:
        if self._exclude_commercial_mails:
            return await fetch_mails(
                user=self.user,
                user_tz=self.user_tz,
                language=self.language,
                exclude_commercial_mails=True,
            )
        return await fetch_mails(user=self.user, user_tz=self.user_tz, language=self.language)

    # =========================================================================
    # One-plan reads for the progressive dashboard (``progressive.py``)
    # =========================================================================

    @property
    def hidden_sections(self) -> frozenset[str]:
        """The sections the person hid: never read, never cached."""
        return self._hidden_sections

    def consult_as(self, run_id: str) -> None:
        """File this service's reads under an act's run id."""
        self._consultation_run_id = run_id

    def plans(self, force: frozenset[str] = frozenset()) -> tuple[_SectionPlan, ...]:
        """How each section is obtained (gather order)."""
        return self._build_plan(force, sms_previews=True)

    async def read_plan(self, plan: _SectionPlan) -> CardSection:
        """One section through the cards' own read (cache, live, outcomes). Never raises."""
        return await self._section(plan.name, plan.fetcher, ttl=plan.ttl, force=plan.force)

    async def cached_section(self, name: str, *, settled: bool = False) -> CardSection | None:
        """A cache-eligible section's cache — a recent failure counts when ``settled``.

        Never a fetch: it is asked only for visible, cache-eligible sections
        (``progressive``), whose settled reader opens no source.
        """
        section = await (
            self._read_settled_section(name) if settled else self._read_cache(self._cache_key(name))
        )
        if section is not None:
            section.from_cache = True
        return section

    async def settled_bundle(self, served: Mapping[str, CardSection] | None = None) -> CardsBundle:
        """What the text may read: caches and recent failures only; absent = unavailable.

        Args:
            served: What the act's first response showed (``act_snapshot``): read for a
                section the cache let go since, so the text speaks of the same page.
        """
        if not served:
            cards, _missing = await self._read_cached_bundle(sms_previews=True)
            return cards

        async def read(name: str, *, include_messages: bool = False) -> CardSection | None:
            section = await self._read_settled_section(name, include_messages=include_messages)
            return section if section is not None else served.get(name)

        cards, _missing = await cached_cards_bundle(read, include_sms=True, sms_previews=True)
        return cards

    async def read_cached_weather(self) -> CardSection | None:
        """Borrow weather for the companion; a miss NEVER starts a source fetch."""
        if SECTION_WEATHER in self._hidden_sections:
            return None
        return await self._read_cache(self._cache_key(SECTION_WEATHER))

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
        cards, _missing = await self._read_cached_bundle(include_sms=False)
        return cards

    async def read_selected_cards(
        self, sections: frozenset[str], *, on_read: SectionReadObserver | None = None
    ) -> CardsBundle:
        """Read another surface's allowed sources, filling cold or expired caches.

        The caller supplies its own source selection, independent of dashboard display
        preferences, and records live reads under its own run. Unselected sections are
        HIDDEN without cache or source IO. ``from_cache`` distinguishes reuse from a
        consultation, including empty results. No model or separate spend tracker runs:
        source costs remain attached to the caller's ambient tracker.

        Args:
            sections: The section names the calling surface permits reading.
            on_read: Reports each attempted live read, including cancellation,
                before the bundle completes. Cache hits report nothing.

        Returns:
            The bundle with only the selected sections populated.

        Raises:
            ValueError: When a selected section does not exist.
        """
        if sections - set(SECTION_NAMES):
            raise ValueError("unknown briefing section")
        plans = [plan for plan in self._build_plan(frozenset()) if plan.name in sections]
        return await selected_cards_bundle(plans, self._section, on_read)

    async def _read_cached_bundle(
        self, *, include_sms: bool = True, sms_previews: bool = False
    ) -> tuple[CardsBundle, frozenset[str]]:
        """Read permitted sections and distinguish a cold bundle from a quiet day."""
        return await cached_cards_bundle(
            self._read_settled_section, include_sms=include_sms, sms_previews=sms_previews
        )

    async def _read_section_cache(
        self, name: str, *, include_messages: bool = False
    ) -> CardSection | None:
        """Per-section cache read honoring hidden preferences (UXR B4).

        Args:
            name: Section name.

        Returns:
            The cached section, a HIDDEN placeholder when the person hid it
            (no Redis IO at all), or None when the cache holds nothing.
        """
        if name in self._hidden_sections:
            return CardSection(status=CardStatus.HIDDEN, generated_at=datetime.now(UTC))
        if name == SECTION_SMS:
            return await self._read_live_section(
                name,
                lambda: fetch_sms(user_id=self.user.id, include_messages=include_messages),
                record=True,
                on_read=None,
            )
        return await self._read_cache(self._cache_key(name))

    async def _read_settled_section(
        self, name: str, *, include_messages: bool = False
    ) -> CardSection | None:
        """A completeness reader's view: a recent failed attempt settles the section (A8).

        Read by the synthesis and by waiting workers, never by the cards' own
        reads, which retry a failed source live.
        """
        if name in self._hidden_sections or name == SECTION_SMS:
            return await self._read_section_cache(name, include_messages=include_messages)
        return await read_settled_section(self._read_cache, self._section_keys(name))

    async def _read_cache(self, key: str) -> CardSection | None:
        """One cached section by key, or None (best-effort, see ``section_outcomes``)."""
        return await read_section(key)

    # =========================================================================
    # Cache state classification (for the duration histogram label)
    # =========================================================================

    @staticmethod
    def _classify_cache_state(
        outcomes: Iterable[tuple[CardSection, bool]],
    ) -> str:
        """Classify by provenance (``from_cache``), never by age (spec 2026-10-21 A8)."""
        return classify_cache_state(outcomes)
