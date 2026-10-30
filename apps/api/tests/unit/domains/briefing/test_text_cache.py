"""The dashboard text: read from caches only, generated once per input, never relaunched."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

import src.domains.briefing.llm as llm
import src.domains.briefing.progressive as progressive
from src.domains.briefing.progressive import _keepable, act_text, initial_cards
from src.domains.briefing.schemas import (
    BriefingWindows,
    CardsBundle,
    CardSection,
    CardStatus,
    SynthesisResponse,
    TextSection,
)
from src.domains.briefing.service import BriefingService, build_briefing_windows
from src.domains.briefing.sms_context import NO_PROMPT_SMS, PromptSms
from src.domains.briefing.text_cache import local_hour, project_cards, text_fingerprint
from src.domains.sms.summary import SmsSignal
from src.infrastructure.locks.redis_claim import ClaimLost
from tests.unit.domains.briefing.page_load_harness import Rig, make_user
from tests.unit.domains.briefing.progressive_harness import (
    MODEL_USAGE,
    MORNING,
    progressive_installed,
)

pytestmark = pytest.mark.unit

GREETING = "src.domains.briefing.service.generate_greeting"


async def _act(user: Any) -> str:
    return (await initial_cards(BriefingService(user), now=MORNING)).act


def _slow_greeting(delay: float = 0.05) -> AsyncMock:
    async def greet(**_kwargs: object) -> tuple[str, Any]:
        await asyncio.sleep(delay)
        return ("Bonjour.", MODEL_USAGE)

    return AsyncMock(side_effect=greet)


def _signal(owner: UUID, stamp: str) -> SmsSignal:
    return SmsSignal(
        timezone="Europe/Paris",
        total=4,
        window_total=1,
        window_start=MORNING - timedelta(hours=24),
        as_of=MORNING,
        latest_at=MORNING,
        owner=owner,
        revision=0,
        stamp=stamp,
        messages=[],
    )


async def test_text_reads_caches_only() -> None:
    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        act = await _act(user)
        rig.reset_calls()
        text = await act_text(BriefingService(user), act=act, force=False, now=MORNING)

    assert sum(rig.calls.values()) == 0
    assert text.state == "ready"
    assert text.greeting.text == "Bonjour."
    # A section nobody read yet is unavailable to the text, never fetched for it.
    assert rig.summarised[-1].weather.status is not CardStatus.OK


async def test_text_generated_once_per_fingerprint() -> None:
    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        act = await _act(user)
        greeting = _slow_greeting()
        with patch(GREETING, greeting):
            first, second = await asyncio.gather(
                act_text(BriefingService(user), act=act, force=False, now=MORNING),
                act_text(BriefingService(user), act=act, force=False, now=MORNING),
            )
            again = await act_text(BriefingService(user), act=act, force=False, now=MORNING)
            forced = await act_text(BriefingService(user), act=act, force=True, now=MORNING)

    assert greeting.await_count == 2  # the first generation, then the forced one
    assert sorted([first.reused, second.reused]) == [False, True]
    assert {first.state, second.state, again.state} == {"ready"}
    assert again.reused is True
    assert forced.reused is False


async def test_text_lost_lease_is_uncertain_and_not_relaunched() -> None:
    rig = Rig()
    user = make_user()

    @asynccontextmanager
    async def lost(*_args: object, **_kwargs: object) -> AsyncIterator[None]:
        yield
        raise ClaimLost("briefing_text", "taken_over")

    with progressive_installed(rig):
        act = await _act(user)
        greeting = _slow_greeting(0)
        with (
            patch(GREETING, greeting),
            patch("src.domains.briefing.progressive.held_claim", lost),
        ):
            text = await act_text(BriefingService(user), act=act, force=False, now=MORNING)

    assert text.state == "uncertain"
    assert text.synthesis is None
    assert greeting.await_count == 1


async def test_a_holder_gone_without_a_text_leaves_its_waiter_uncertain() -> None:
    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        act = await _act(user)
        greeting = AsyncMock(return_value=("Bonjour.", None))  # a written fallback: never kept
        release = asyncio.Event()

        async def held_back(**kwargs: object) -> tuple[str, Any]:
            await release.wait()
            return await greeting(**kwargs)

        with patch(GREETING, AsyncMock(side_effect=held_back)):
            holder = asyncio.create_task(
                act_text(BriefingService(user), act=act, force=False, now=MORNING)
            )
            await asyncio.sleep(0.02)
            waiter = asyncio.create_task(
                act_text(BriefingService(user), act=act, force=False, now=MORNING)
            )
            await asyncio.sleep(0.02)
            release.set()
            held, waited = await asyncio.gather(holder, waiter)

    assert held.state == "ready"
    assert waited.state == "uncertain"
    assert greeting.await_count == 1


async def test_text_spend_blocked_returns_fallback_greeting() -> None:
    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        act = await _act(user)
        with (
            patch(GREETING, llm.generate_greeting),
            patch("src.domains.briefing.service.generate_synthesis", llm.generate_synthesis),
            patch(
                "src.domains.usage_limits.enforcement.spend_blocked", AsyncMock(return_value=True)
            ),
            patch.object(llm, "_resolve_personality", AsyncMock(return_value="")),
            patch.object(llm, "_resolve_user_model_block", AsyncMock(return_value="")),
            patch.object(llm, "get_llm") as model,
        ):
            first = await act_text(BriefingService(user), act=act, force=False, now=MORNING)
            second = await act_text(BriefingService(user), act=act, force=False, now=MORNING)

    service = BriefingService(user)
    fallback = llm.fallback_greeting(user, service.user_tz, service.language)
    assert first.greeting.text == fallback
    assert first.state == "ready"
    assert first.greeting.usage is None
    assert second.reused is False  # a refusal is never kept as the text
    model.assert_not_called()


async def test_sms_witness_change_drops_cached_text() -> None:
    rig = Rig()
    user = make_user()
    witness = {"stamp": "4:a"}

    async def prompt_sms(owner: UUID, _section: CardSection) -> PromptSms:
        return PromptSms(signal=_signal(owner, witness["stamp"]), brief="", detailed="")

    with progressive_installed(rig):
        act = await _act(user)
        greeting = _slow_greeting(0)
        with (
            patch(GREETING, greeting),
            patch("src.domains.briefing.progressive.read_prompt_sms", prompt_sms),
            patch(
                "src.domains.briefing.progressive.sms_signal_current",
                AsyncMock(return_value=True),
            ),
        ):
            await act_text(BriefingService(user), act=act, force=False, now=MORNING)
            same = await act_text(BriefingService(user), act=act, force=False, now=MORNING)
            witness["stamp"] = "5:b"
            changed = await act_text(BriefingService(user), act=act, force=False, now=MORNING)

    assert same.reused is True
    assert changed.reused is False
    assert greeting.await_count == 2


async def test_sms_that_changed_during_generation_is_stale_and_not_kept() -> None:
    rig = Rig()
    user = make_user()

    async def prompt_sms(owner: UUID, _section: CardSection) -> PromptSms:
        return PromptSms(signal=_signal(owner, "4:a"), brief="", detailed="")

    with progressive_installed(rig):
        act = await _act(user)
        greeting = _slow_greeting(0)
        with (
            patch(GREETING, greeting),
            patch("src.domains.briefing.progressive.read_prompt_sms", prompt_sms),
            patch(
                "src.domains.briefing.progressive.sms_signal_current",
                AsyncMock(return_value=False),
            ),
        ):
            stale = await act_text(BriefingService(user), act=act, force=False, now=MORNING)
            again = await act_text(BriefingService(user), act=act, force=False, now=MORNING)

    assert stale.state == again.state == "sms_stale"
    assert again.reused is False
    assert greeting.await_count == 2


def _bundle(**sections: CardSection) -> CardsBundle:
    hidden = CardSection(status=CardStatus.HIDDEN, generated_at=MORNING)
    return CardsBundle(**{name: sections.get(name, hidden) for name in CardsBundle.model_fields})


def _fingerprint(
    cards: CardsBundle,
    *,
    windows: BriefingWindows | None = None,
    slot: str = "slot",
    sms: str | None = None,
    hour: datetime = MORNING,
    person: str = "person",
) -> str:
    projected, statuses = project_cards(cards)
    return text_fingerprint(
        projected,
        statuses,
        windows or build_briefing_windows(),
        slot,
        "v1/v1",
        sms,
        local_hour=local_hour(hour),
        person=person,
    )


def test_fingerprint_ignores_what_changes_at_every_fetch_and_follows_the_rest() -> None:
    ok = CardSection(status=CardStatus.EMPTY, generated_at=MORNING)
    refetched = CardSection(
        status=CardStatus.EMPTY,
        generated_at=MORNING + timedelta(minutes=3),
        from_cache=True,
        stale_generated_at=MORNING,
        last_attempt_at=MORNING,
    )
    base = _fingerprint(_bundle(agenda=ok))

    assert _fingerprint(_bundle(agenda=refetched)) == base
    failed = CardSection(status=CardStatus.ERROR, generated_at=MORNING)
    assert _fingerprint(_bundle(agenda=failed)) != base
    assert _fingerprint(_bundle(agenda=ok), slot="other") != base
    assert _fingerprint(_bundle(agenda=ok), sms="5:b") != base
    assert _fingerprint(_bundle(agenda=ok), hour=MORNING + timedelta(hours=1)) != base
    assert _fingerprint(_bundle(agenda=ok), hour=MORNING + timedelta(minutes=30)) == base
    assert _fingerprint(_bundle(agenda=ok), person="another personality") != base


def test_a_sparse_day_keeps_its_text_and_a_failed_synthesis_does_not() -> None:
    text = SynthesisResponse(
        greeting=TextSection(text="Bonjour.", generated_at=MORNING, usage=MODEL_USAGE),
        synthesis=None,
    )
    quiet = _bundle()
    data = {"status": CardStatus.OK, "generated_at": MORNING}
    busy = _bundle(
        agenda=CardSection(**data, data=None),
        mails=CardSection(**data, data=None),
        tasks=CardSection(**data, data=None),
    )

    assert _keepable(text, quiet, NO_PROMPT_SMS) is True
    assert _keepable(text, busy, NO_PROMPT_SMS) is False


async def test_without_the_shared_lease_the_text_is_generated_unshared() -> None:
    """No cache to share the lease through: the text is still written, once."""
    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        act = await _act(user)
        greeting = _slow_greeting(0)
        with (
            patch(GREETING, greeting),
            patch(
                "src.domains.briefing.progressive.try_claim",
                AsyncMock(side_effect=ConnectionError("cache down")),
            ),
        ):
            text = await act_text(BriefingService(user), act=act, force=False, now=MORNING)

    assert text.state == "ready"
    assert greeting.await_count == 1


def _held_elsewhere(get: AsyncMock) -> Any:
    """A lease another worker holds: the claim is refused, its key read through ``get``."""
    redis = AsyncMock()
    redis.get = get
    return (
        patch("src.domains.briefing.progressive.try_claim", AsyncMock(return_value=False)),
        patch("src.domains.briefing.progressive.get_redis_cache", AsyncMock(return_value=redis)),
        patch.object(progressive.settings, "briefing_shared_build_max_wait_seconds", 0.05),
        patch("src.domains.briefing.progressive.TEXT_POLL_SECONDS", 0.01),
    )


@pytest.mark.parametrize(
    "get",
    [
        AsyncMock(return_value="another-worker"),  # held, and readable
        AsyncMock(side_effect=ConnectionError("unreadable")),  # decides nothing: still held
    ],
    ids=["held", "unreadable"],
)
async def test_a_waiter_past_its_deadline_is_uncertain_and_never_generates(
    get: AsyncMock,
) -> None:
    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        act = await _act(user)
        greeting = _slow_greeting(0)
        claim, cache, wait, poll = _held_elsewhere(get)
        with patch(GREETING, greeting), claim, cache, wait, poll:
            text = await act_text(BriefingService(user), act=act, force=False, now=MORNING)

    assert text.state == "uncertain"
    assert greeting.await_count == 0
    assert get.await_count >= 1


async def test_a_waiter_serves_the_text_its_holder_published_while_still_holding() -> None:
    """The holder's text is served at the next poll, before its lease is released."""
    rig = Rig()
    user = make_user()
    get = AsyncMock(return_value="another-worker")
    kept = SynthesisResponse(
        greeting=TextSection(text="Bonjour du voisin.", generated_at=MORNING, usage=MODEL_USAGE)
    )

    async def published_once_polled(_key: str) -> SynthesisResponse | None:
        return kept if get.await_count else None

    with progressive_installed(rig):
        act = await _act(user)
        greeting = _slow_greeting(0)
        claim, cache, wait, poll = _held_elsewhere(get)
        with (
            patch(GREETING, greeting),
            claim,
            cache,
            wait,
            poll,
            patch(
                "src.domains.briefing.progressive.read_text",
                AsyncMock(side_effect=published_once_polled),
            ),
        ):
            text = await act_text(BriefingService(user), act=act, force=False, now=MORNING)

    assert (text.state, text.reused) == ("ready", True)
    assert text.greeting.text == "Bonjour du voisin."
    assert greeting.await_count == 0


async def test_an_unreachable_text_cache_reads_nothing_and_writes_in_silence() -> None:
    """Best-effort both ways: a cold read generates, a failed write loses only reuse."""
    from src.domains.briefing.text_cache import read_text, write_text

    down = AsyncMock(side_effect=ConnectionError("cache down"))
    text = SynthesisResponse(
        greeting=TextSection(text="Bonjour.", generated_at=MORNING, usage=MODEL_USAGE)
    )
    with patch("src.domains.briefing.text_cache.get_redis_cache", down):
        assert await read_text("briefing:v2:text:k") is None
        await write_text("briefing:v2:text:k", text)

    assert down.await_count == 2


async def test_an_unreadable_kept_text_is_a_cold_read() -> None:
    from src.domains.briefing.text_cache import read_text

    redis = AsyncMock()
    redis.get = AsyncMock(return_value="{not json")
    with patch("src.domains.briefing.text_cache.get_redis_cache", AsyncMock(return_value=redis)):
        assert await read_text("briefing:v2:text:k") is None


async def test_a_disabled_text_cache_generates_each_text_and_shares_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh review B6: « 0 disables » worked by accident — ``set(ex=0)`` raised and was
    swallowed, while a second tab still waited on the holder, found nothing published
    and answered ``uncertain``. Disabled now means: nothing read, kept or waited for."""
    monkeypatch.setattr(progressive.settings, "briefing_text_cache_ttl_seconds", 0)
    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        act = await _act(user)
        greeting = _slow_greeting()
        with patch(GREETING, greeting):
            first, second = await asyncio.gather(
                act_text(BriefingService(user), act=act, force=False, now=MORNING),
                act_text(BriefingService(user), act=act, force=False, now=MORNING),
            )

    assert (first.state, second.state) == ("ready", "ready")
    assert (first.reused, second.reused) == (False, False)
    assert greeting.await_count == 2


async def test_what_the_prompts_read_of_the_person_is_part_of_the_texts_identity() -> None:
    """Fresh review B1: the prompts read LIA's personality, the display name and the user
    model block, the fingerprint did not — a personality changed was answered for five
    minutes with the greeting written under the old one, marked ``ready``."""
    rig = Rig()
    user = make_user()
    person = AsyncMock(side_effect=["personality A", "personality A", "personality B"])
    with progressive_installed(rig), patch.object(progressive, "person_inputs_digest", person):
        act = await _act(user)
        greeting = _slow_greeting(0)
        with patch(GREETING, greeting):
            first = await act_text(BriefingService(user), act=act, force=False, now=MORNING)
            same = await act_text(BriefingService(user), act=act, force=False, now=MORNING)
            changed = await act_text(BriefingService(user), act=act, force=False, now=MORNING)

    assert (first.reused, same.reused, changed.reused) == (False, True, False)
    assert greeting.await_count == 2


async def test_the_person_digest_follows_each_input_the_prompts_read() -> None:
    user = make_user()

    async def digest(personality: str, model_block: str) -> str:
        with (
            patch.object(llm, "_resolve_personality", AsyncMock(return_value=personality)),
            patch.object(llm, "_resolve_user_model_block", AsyncMock(return_value=model_block)),
        ):
            return await llm.person_inputs_digest(user)

    base = await digest("warm", "portrait")

    assert await digest("warm", "portrait") == base
    assert await digest("dry", "portrait") != base
    assert await digest("warm", "another portrait") != base


async def test_a_section_the_page_shows_is_in_the_text_even_when_its_cache_expired() -> None:
    """Fresh review B2: a section served from the cache at the load, expired before the
    text was asked for, reached the synthesis as « not configured » — a card the person
    sees, missing from what LIA says of the day. The act keeps what it showed."""
    from src.domains.briefing.constants import SECTION_MAILS_TTL_SECONDS
    from src.domains.briefing.progressive import act_section

    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        first = await initial_cards(BriefingService(user), now=MORNING)
        await act_section(BriefingService(user), "mails", act=first.act, now=MORNING)
        load = await initial_cards(BriefingService(user), now=MORNING)
        assert load.cards.mails.status is CardStatus.OK  # served from the cache
        rig.clock.advance(SECTION_MAILS_TTL_SECONDS + 1)  # expires before the text
        await act_text(BriefingService(user), act=load.act, force=False, now=MORNING)

    assert rig.summarised[-1].mails.status is CardStatus.OK


async def test_without_the_acts_copy_an_expired_section_is_unavailable_never_invented() -> None:
    """The copy is best-effort: lost, the text reads the caches alone, as before it."""
    from src.domains.briefing.constants import SECTION_MAILS_TTL_SECONDS
    from src.domains.briefing.progressive import act_section

    rig = Rig()
    user = make_user()
    with progressive_installed(rig):
        first = await initial_cards(BriefingService(user), now=MORNING)
        await act_section(BriefingService(user), "mails", act=first.act, now=MORNING)
        load = await initial_cards(BriefingService(user), now=MORNING)
        rig.clock.advance(SECTION_MAILS_TTL_SECONDS + 1)
        with patch("src.domains.briefing.progressive.served_sections", AsyncMock(return_value={})):
            text = await act_text(BriefingService(user), act=load.act, force=False, now=MORNING)

    assert text.state == "ready"
    assert rig.summarised[-1].mails.status is not CardStatus.OK


async def test_the_person_digest_reads_the_user_model_block_without_counting_it() -> None:
    """Third fresh review: the presence counters must count blocks a prompt carried."""
    user = make_user()
    model_block = AsyncMock(return_value="portrait")
    with (
        patch.object(llm, "_resolve_personality", AsyncMock(return_value="warm")),
        patch.object(llm, "_resolve_user_model_block", model_block),
    ):
        await llm.person_inputs_digest(user)

    model_block.assert_awaited_once_with(user, counted=False)
