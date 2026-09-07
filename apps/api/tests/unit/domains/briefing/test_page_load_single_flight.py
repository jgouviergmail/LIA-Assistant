"""One page load is ONE act of reading the person's sources.

``GET /briefing/cards`` and ``GET /briefing/synthesis`` are issued in parallel
by the dashboard, and each used to build the whole bundle: measured on the
running instance over seven days, 44 of 151 bundle builds were duplicates and
39 % of page loads opened every connector twice — Google Calendar, Gmail,
Drive, Tasks and the weather API, each called twice within the same second,
plus two batches of consultation rows in the effect register for a single act.

These tests pin the contract that ends it.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.briefing.constants import SECTION_MAILS, SECTION_WEATHER
from src.domains.briefing.schemas import CardsBundle, CardStatus
from src.domains.briefing.service import BriefingService
from src.infrastructure.observability.metrics_briefing import briefing_bundle_builds_total
from tests.unit.domains.briefing.page_load_harness import (
    SECTION_NAMES,
    Rig,
    make_user,
    not_configured,
)

# asyncio_mode = "auto" (pyproject): an explicit asyncio mark would also be
# applied to the synchronous completeness checks below and warn.
pytestmark = [pytest.mark.unit]


# =============================================================================
# The bundle is built once per page load
# =============================================================================


async def test_cold_cache_page_load_builds_the_bundle_once() -> None:
    """The founding case: nothing cached, both endpoints want the bundle."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await rig.page_load(user)
    assert rig.builds == 1, f"expected one bundle build, got {rig.builds}"


async def test_cold_cache_page_load_opens_each_source_once() -> None:
    """Every connector, not just the bundle as a whole."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await rig.page_load(user)
    doubled = {name: count for name, count in rig.calls.items() if count > 1}
    assert not doubled, f"these sources were opened more than once: {doubled}"


async def test_synthesis_arriving_first_also_builds_once() -> None:
    """Request order is not guaranteed — whoever arrives first owns the build."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await asyncio.gather(
            BriefingService(user).build_text(),
            BriefingService(user).build_cards(),
        )
    assert rig.builds == 1


async def test_three_concurrent_readers_build_once() -> None:
    """Two tabs plus the mobile shell still make one act of reading."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await asyncio.gather(
            BriefingService(user).build_cards(),
            BriefingService(user).build_text(),
            BriefingService(user).build_cards(),
        )
    assert rig.builds == 1


async def test_two_accounts_never_share_a_build() -> None:
    """Coalescing is per person — never across accounts."""
    rig = Rig()
    with rig.installed():
        await asyncio.gather(
            BriefingService(make_user()).build_cards(),
            BriefingService(make_user()).build_cards(),
        )
    assert rig.builds == 2


# =============================================================================
# A failing connector is not retried twice per load
# =============================================================================


async def test_failing_connector_is_opened_once_per_page_load() -> None:
    """An ERROR section is deliberately never cached, so it has no floor of
    its own: without coalescing it was retried on every build, and every page
    load ran two builds — a retry storm aimed at the one dependency already
    in trouble."""
    rig = Rig(failures={"mails": RuntimeError("gmail is down")})
    user = make_user()
    with rig.installed():
        for _ in range(3):
            rig.reset_calls()
            await rig.page_load(user)
            assert (
                rig.calls["mails"] == 1
            ), f"the failing connector was opened {rig.calls['mails']} times in one load"


# =============================================================================
# The synthesis describes the cards the reader is looking at
# =============================================================================


async def test_synthesis_summarises_the_very_bundle_the_cards_returned() -> None:
    """Two independent fetches could disagree; one shared build cannot."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        cards, _text = await rig.page_load(user)
    assert rig.summarised, "the synthesis was never generated"
    summarised = rig.summarised[-1]
    # Identity, not equality: the rig returns constant payloads, so two
    # INDEPENDENT builds would compare equal and the oracle would pass over
    # the very defect it exists to catch. Only a shared build gives the same
    # object.
    assert summarised is cards


async def test_a_source_that_moves_between_fetches_cannot_split_the_page() -> None:
    """The regression that made the card say one unread and the synthesis two."""
    rig = Rig()
    user = make_user()
    seen: list[int] = []

    async def _mails(*_args: object, **_kwargs: object):
        rig.calls["mails"] += 1
        # Snapshot BEFORE suspending: read afterwards, both concurrent fetches
        # would observe the final value and the divergence would be invisible.
        nth = rig.calls["mails"]
        seen.append(nth)
        await asyncio.sleep(rig.latency_s)
        from src.domains.briefing.schemas import MailItem, MailsData

        return MailsData(
            items=[
                MailItem(sender_email=f"{i}@x.y", subject=f"S{i}", received_local="09:00")
                for i in range(nth)
            ],
            total_unread_today=nth,
        )

    with (
        rig.installed(),
        patch("src.domains.briefing.service.fetch_mails", AsyncMock(side_effect=_mails)),
    ):
        cards, _text = await rig.page_load(user)

    assert seen == [1], f"the mailbox was read {len(seen)} times for one page load"
    rendered = cards.mails.data.total_unread_today
    summarised = rig.summarised[-1].mails.data.total_unread_today
    assert (
        rendered == summarised
    ), f"the card shows {rendered} unread while the synthesis describes {summarised}"


# =============================================================================
# A warm cache is trusted: "sparse" must mean MISSING, never "uninteresting"
# =============================================================================


async def test_warm_cache_is_never_rebuilt_for_a_thin_dashboard() -> None:
    """A dashboard whose only populated sections are tasks and documents is a
    legitimately quiet dashboard, not a cold cache. It used to be rebuilt on
    every single ``/synthesis`` call, forever."""
    quiet = {
        name: not_configured() for name in ("weather", "agenda", "mails", "birthdays", "health")
    }
    rig = Rig(failures=quiet)
    user = make_user()
    with rig.installed():
        await BriefingService(user).build_cards()  # warm every cacheable section
        for _ in range(3):
            rig.reset_calls()
            await BriefingService(user).build_text()
            assert rig.builds == 0, "the synthesis rebuilt a bundle the cache already held"


async def test_a_missing_section_still_triggers_a_build() -> None:
    """Coverage, not richness: one absent section means the bundle is stale."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await BriefingService(user).build_cards()
        rig.redis.drop(SECTION_WEATHER)
        rig.reset_calls()
        await BriefingService(user).build_text()
        assert rig.builds == 1
        assert rig.calls[SECTION_WEATHER] == 1


async def test_hidden_sections_are_not_expected_in_the_cache() -> None:
    """A section the person hid is never fetched, so its absence from the
    cache must not be read as a stale bundle."""
    rig = Rig()
    user = make_user(hidden=(SECTION_MAILS,))
    with rig.installed():
        await BriefingService(user).build_cards()
        rig.reset_calls()
        await BriefingService(user).build_text()
    assert rig.builds == 0
    assert rig.calls[SECTION_MAILS] == 0


# =============================================================================
# A forced refresh is never served by a cached build
# =============================================================================


async def test_forced_refresh_does_not_join_an_unforced_build() -> None:
    """Joining would silently ignore the force and hand back cached data."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await asyncio.gather(
            BriefingService(user).build_cards(),
            BriefingService(user).build_cards(force_refresh={"all"}),
        )
    assert rig.builds == 2


async def test_two_identical_forced_refreshes_share_one_build() -> None:
    """A double-click on "refresh all" is one refresh."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await asyncio.gather(
            BriefingService(user).build_cards(force_refresh={"all"}),
            BriefingService(user).build_cards(force_refresh={"all"}),
        )
    assert rig.builds == 1


async def test_a_completed_build_is_never_handed_to_a_later_request() -> None:
    """Coalescing shares work in flight; it is not a cache."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await BriefingService(user).build_cards(force_refresh={"all"})
        rig.reset_calls()
        await BriefingService(user).build_cards(force_refresh={"all"})
    assert rig.builds == 1


# =============================================================================
# The reminders card reaches the text the reader is given
# =============================================================================


async def test_the_synthesis_is_told_about_the_reminders() -> None:
    """``_summarize_cards_for_llm`` has always had a reminders branch, and the
    normal page load could never reach it: the section is fetched live, so a
    cache reader saw a NOT_CONFIGURED placeholder. Only "refresh all" ever
    fed it — two routes to one text, silently disagreeing."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await rig.page_load(user)
    assert rig.summarised[-1].reminders.status is CardStatus.OK


async def test_the_synthesis_sees_reminders_on_a_warm_cache_too() -> None:
    """The warm path is the common one; it must not lose the section."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await BriefingService(user).build_cards()
        rig.reset_calls()
        await BriefingService(user).build_text()
    assert rig.summarised[-1].reminders.status is CardStatus.OK


# =============================================================================
# The section cache belongs to a language
# =============================================================================


async def test_changing_the_language_does_not_serve_the_previous_one() -> None:
    """Agenda, mails, reminders and documents are pre-formatted server-side in
    the account language, and the cache key ignored it: after a language
    change the cards stayed in the old one until the TTL elapsed."""
    rig = Rig()
    account = uuid4()
    with rig.installed():
        await BriefingService(make_user(language="fr", user_id=account)).build_cards()
        rig.reset_calls()
        await BriefingService(make_user(language="de", user_id=account)).build_cards()
    assert rig.calls["agenda"] == 1, "the German dashboard was served the French cache"


async def test_the_same_language_still_hits_the_cache() -> None:
    """Keying on the language must not defeat the cache for everyone else."""
    rig = Rig()
    account = uuid4()
    with rig.installed():
        await BriefingService(make_user(language="fr", user_id=account)).build_cards()
        rig.reset_calls()
        await BriefingService(make_user(language="fr", user_id=account)).build_cards()
    assert rig.calls["agenda"] == 0


# =============================================================================
# Nothing is left behind
# =============================================================================


async def test_the_registry_is_empty_once_every_build_has_finished() -> None:
    """An in-flight registry that keeps entries is a leak that also serves
    stale bundles."""
    from src.infrastructure.utils.single_flight import in_flight_count

    rig = Rig()
    user = make_user()
    with rig.installed():
        await rig.page_load(user)
    assert in_flight_count() == 0


async def test_every_section_is_still_produced() -> None:
    """Whatever the plumbing, the bundle keeps all nine sections."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        cards, _text = await rig.page_load(user)
    for name in SECTION_NAMES:
        assert getattr(cards, name) is not None


async def test_read_cached_cards_still_returns_what_we_already_know() -> None:
    """The public capability the chat's grounded suggestions rely on: "what we
    already know, at no cost". It now delegates to the coverage-aware read, and
    must keep its contract — a bundle, no fetching, ever."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await BriefingService(user).build_cards()
        rig.reset_calls()
        cached = await BriefingService(user).read_cached_cards()
    assert rig.calls == {}, "a cache-only read woke a connector"
    assert cached.mails.status is CardStatus.OK
    assert cached.reminders.status is CardStatus.OK


# =============================================================================
# What a page load costs in model calls
# =============================================================================


async def test_a_page_load_costs_exactly_one_greeting_and_one_synthesis() -> None:
    """The cost invariant. Coalescing removed a duplicate BUNDLE build, never a
    model call — the two texts were always generated once, by ``/synthesis``
    alone, and they still are. Asserted rather than reasoned about, because the
    conclusion decides whether this change costs money."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await rig.page_load(user)
    assert len(rig.summarised) == 1, "the synthesis model was called more than once"


async def test_a_warm_reload_costs_the_same_single_synthesis() -> None:
    """The warm path no longer rebuilds the bundle, and that must not have
    silenced the text nor doubled it."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await rig.page_load(user)
        before = len(rig.summarised)
        await rig.page_load(user)
    assert len(rig.summarised) - before == 1


# =============================================================================
# Completeness: three declarations of "the sections" must not drift apart
# =============================================================================


def test_the_build_plan_covers_exactly_the_declared_sections() -> None:
    """``_build_plan``, ``SECTION_NAMES`` and the bundle's own fields are read
    against one another at runtime (the gather zips them, the bundle is built
    by keyword). A section added to one and not the others fails at request
    time, on the home page, for everyone — so it is checked here instead."""
    plan = BriefingService(make_user())._build_plan(frozenset())
    assert tuple(step.name for step in plan) == SECTION_NAMES
    assert set(CardsBundle.model_fields) == set(SECTION_NAMES)


def test_every_section_is_written_to_the_cache() -> None:
    """A section with no TTL is never written, and is therefore invisible to
    every cache-only reader — which is exactly how the reminders section
    disappeared from the synthesis. Coverage-based freshness assumes each
    visible section can be present, so none may have a zero TTL."""
    plan = BriefingService(make_user())._build_plan(frozenset())
    without_ttl = [step.name for step in plan if step.ttl <= 0]
    assert not without_ttl, f"these sections can never be read back: {without_ttl}"


# =============================================================================
# Degraded mode
# =============================================================================


async def test_a_page_load_survives_redis_being_down() -> None:
    """Nothing can be cached, so every load is cold — but it must still be
    ONE act of reading, not two."""
    rig = Rig()
    user = make_user()
    with (
        rig.installed(),
        patch(
            "src.domains.briefing.service.get_redis_cache",
            AsyncMock(side_effect=ConnectionError("redis-down")),
        ),
    ):
        cards, _text = await rig.page_load(user)
    assert rig.builds == 1
    assert cards.weather.status is CardStatus.OK


# =============================================================================
# The proof surface an operator reads
# =============================================================================


async def test_the_counter_tells_an_owned_build_from_a_joined_one() -> None:
    """Without this the fix is unobservable in production, and a metric nobody
    can see is a metric nobody acts on."""
    before = _build_counts()
    rig = Rig()
    user = make_user()
    with rig.installed():
        await rig.page_load(user)
    after = _build_counts()
    assert after["owned"] - before["owned"] == 1
    assert after["joined"] - before["joined"] == 1


def _build_counts() -> dict[str, float]:
    """Current value of the owned/joined counter, by outcome."""
    counts = {"owned": 0.0, "joined": 0.0}
    for metric in briefing_bundle_builds_total.collect():
        for sample in metric.samples:
            outcome = sample.labels.get("outcome")
            if sample.name.endswith("_total") and outcome in counts:
                counts[outcome] = sample.value
    return counts


# =============================================================================
# Across WORKERS: production runs four of them
# =============================================================================


async def test_two_workers_open_each_source_once() -> None:
    """The in-process seam cannot reach across processes, and production runs
    four uvicorn workers (``WEB_CONCURRENCY=4``): measured on the deployed
    instance, three overlapping pairs were never joined and ``briefing:mails``
    was opened five times for two page loads.

    Two workers are simulated by calling the cross-worker seam directly, which
    is exactly what two separate in-process registries reduce to.
    """
    rig = Rig()
    user = make_user()
    with rig.installed():
        await asyncio.gather(
            BriefingService(user)._gather_once_per_deployment(frozenset()),
            BriefingService(user)._gather_once_per_deployment(frozenset()),
        )
    doubled = {name: count for name, count in rig.calls.items() if count > 1}
    assert not doubled, f"two workers opened these sources twice: {doubled}"


async def test_the_waiting_worker_gets_a_complete_bundle() -> None:
    """A waiter takes what the holder published — never a bundle with holes."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        first, second = await asyncio.gather(
            BriefingService(user)._gather_once_per_deployment(frozenset()),
            BriefingService(user)._gather_once_per_deployment(frozenset()),
        )
    for bundle in (first, second):
        for name in SECTION_NAMES:
            section = getattr(bundle, name)
            assert section is not None and section.status is not None


async def test_a_forced_refresh_never_takes_another_workers_result() -> None:
    """It asked to bypass the cache, and what a holder publishes IS the cache."""
    rig = Rig()
    user = make_user()
    with rig.installed():
        await asyncio.gather(
            BriefingService(user)._gather_once_per_deployment(frozenset()),
            BriefingService(user)._gather_once_per_deployment(frozenset({"all"})),
        )
    assert rig.builds == 2, "a forced refresh waited for a cached result"


async def test_the_claim_is_released_so_the_next_load_is_not_stuck() -> None:
    rig = Rig()
    user = make_user()
    with rig.installed():
        await BriefingService(user)._gather_once_per_deployment(frozenset())
        claims = [k for k in rig.redis.keys() if k.startswith("shared_flight:")]
    assert claims == [], f"a claim outlived its build: {claims}"


async def test_two_accounts_do_not_share_a_claim() -> None:
    rig = Rig()
    with rig.installed():
        await asyncio.gather(
            BriefingService(make_user())._gather_once_per_deployment(frozenset()),
            BriefingService(make_user())._gather_once_per_deployment(frozenset()),
        )
    assert rig.builds == 2
