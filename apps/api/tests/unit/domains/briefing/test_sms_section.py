"""Home SMS completeness, old bundles and zero-read hidden cards."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.domains.briefing.constants import SECTION_NAMES
from src.domains.briefing.schemas import CardsBundle, CardSection, CardStatus, SmsData
from src.domains.briefing.service import BriefingService
from src.domains.briefing.sms_context import PromptSms
from tests.unit.domains.briefing.test_llm import _bundle_with_weather, _weather_section
from tests.unit.domains.briefing.test_service import _make_user

#: An SMS read whose snapshot each test declares current or withdrawn.
_PRIVATE_PROMPT_SMS = PromptSms(signal=object(), brief="", detailed="PRIVATE_SMS_CONTEXT")  # type: ignore[arg-type]

pytestmark = pytest.mark.unit


def test_sms_plan_is_live_and_old_bundles_remain_readable():
    service = BriefingService(_make_user())
    plan = next(plan for plan in service._build_plan(frozenset()) if plan.name == "sms")
    assert plan.force and not plan.cache_eligible and plan.ttl == 0
    bundle = _bundle_with_weather(_weather_section())
    old = bundle.model_dump(mode="json")
    old.pop("sms", None)
    assert CardsBundle.model_validate(old).sms.status == CardStatus.NOT_CONFIGURED
    assert set(CardsBundle.model_fields) == set(SECTION_NAMES)


async def test_hidden_sms_card_never_reads_cache_or_archive():
    user = _make_user()
    user.briefing_preferences = {"hidden": ["sms"]}
    service = BriefingService(user)
    service._read_cache = AsyncMock(side_effect=AssertionError("cache read"))
    fetch = AsyncMock(side_effect=AssertionError("archive read"))
    section = await service._section("sms", fetch, ttl=0, force=True)
    assert section.status == CardStatus.HIDDEN
    fetch.assert_not_called()
    service._read_cache.assert_not_called()


async def test_cache_only_reader_cannot_reserve_old_sms_metadata():
    service = BriefingService(_make_user())
    fresh = CardSection(status=CardStatus.EMPTY, generated_at=datetime.now(UTC))
    service._read_live_section = AsyncMock(return_value=fresh)
    service._read_cache = AsyncMock(side_effect=AssertionError("stale SMS cache"))
    assert await service._read_section_cache("sms") == fresh
    service._read_live_section.assert_awaited_once()


def test_sms_metadata_projection_does_not_expose_message_bodies():
    from src.domains.sms.summary import SmsSummary

    data = SmsSummary(
        total=137,
        window_total=5,
        window_start=datetime.now(UTC),
        as_of=datetime.now(UTC),
        latest_at=None,
    )
    assert set(data.model_dump()) == {
        "timezone",
        "total",
        "window_total",
        "window_start",
        "as_of",
        "latest_at",
    }


def test_empty_sms_archive_is_an_empty_card():
    from src.domains.briefing.service import _has_content

    assert not _has_content(
        SmsData(
            total=0,
            window_total=0,
            window_start=datetime.now(UTC),
            as_of=datetime.now(UTC),
            latest_at=None,
        )
    )


async def test_live_sms_card_never_writes_a_last_good_copy(monkeypatch):
    import src.domains.briefing.section_outcomes as outcomes

    service = BriefingService(_make_user())
    service._read_cache = AsyncMock(side_effect=AssertionError("cache read"))
    write = AsyncMock(side_effect=AssertionError("cache write"))
    last_good = AsyncMock(side_effect=AssertionError("last-good write"))
    marker = AsyncMock(side_effect=AssertionError("attempt marker"))
    monkeypatch.setattr(outcomes, "write_section", write)
    monkeypatch.setattr(outcomes, "_write_last_good", last_good)
    monkeypatch.setattr(outcomes, "_write_marker", marker)
    data = SmsData(
        total=137,
        window_total=5,
        window_start=datetime.now(UTC),
        as_of=datetime.now(UTC),
        latest_at=None,
    )
    section = await service._section(
        "sms", AsyncMock(return_value=data), ttl=0, force=True, record=False
    )
    assert section.status == CardStatus.OK
    write.assert_not_called()
    last_good.assert_not_called()
    marker.assert_not_called()


async def test_old_grounded_suggestions_cannot_implicitly_open_sms():
    service = BriefingService(_make_user())

    async def cached(name):
        assert name != "sms", "generic cache-only reader gained SMS IO"
        return CardSection(status=CardStatus.EMPTY, generated_at=datetime.now(UTC))

    service._read_section_cache = cached
    cards = await service.read_cached_cards()
    assert cards.sms.status == CardStatus.HIDDEN


async def test_sms_consent_off_cannot_buy_synthesis_from_one_other_card(monkeypatch):
    import src.domains.briefing.llm as llm
    import src.domains.briefing.sms_context as source
    from src.core.exceptions import AuthorizationError

    denied = AsyncMock(
        side_effect=AuthorizationError(detail={"error_code": "SMS_CONSENT_REQUIRED"})
    )
    monkeypatch.setattr(source, "read_sms_signal", denied)
    invoke = AsyncMock(return_value=("SHOULD_NOT_SPEND", None))
    monkeypatch.setattr(llm, "_invoke_and_track", invoke)
    monkeypatch.setattr(llm, "_resolve_personality", AsyncMock(return_value=""))
    monkeypatch.setattr(llm, "_resolve_user_model_block", AsyncMock(return_value=""))
    data = SmsData(
        total=137,
        window_total=5,
        window_start=datetime.now(UTC),
        as_of=datetime.now(UTC),
        latest_at=None,
    )
    cards = _bundle_with_weather(_weather_section()).model_copy(
        update={"sms": CardSection(status=CardStatus.OK, data=data, generated_at=datetime.now(UTC))}
    )
    from zoneinfo import ZoneInfo

    user = _make_user()
    prompt_sms = await source.read_prompt_sms(user.id, cards.sms)
    result = await llm.generate_synthesis(
        user=user,
        user_tz=ZoneInfo("Europe/Paris"),
        cards=cards,
        language="fr",
        prompt_sms=prompt_sms,
    )
    assert prompt_sms == source.NO_PROMPT_SMS
    assert result == (None, None)
    invoke.assert_not_called()


async def test_sms_withdrawal_during_synthesis_keeps_paid_usage_but_refuses_text(monkeypatch):
    from zoneinfo import ZoneInfo

    import src.domains.briefing.llm as llm
    from src.core.llm_usage import LLMUsage

    usage = LLMUsage(tokens_in=123, tokens_out=12, cost_eur=0.02)
    monkeypatch.setattr(llm, "sms_signal_current", AsyncMock(side_effect=[True, False]))
    monkeypatch.setattr(
        llm, "_invoke_and_track", AsyncMock(return_value=("PAID_PRIVATE_RESULT", usage))
    )
    monkeypatch.setattr(llm, "_resolve_personality", AsyncMock(return_value=""))
    monkeypatch.setattr(llm, "_resolve_user_model_block", AsyncMock(return_value=""))
    data = SmsData(
        total=137,
        window_total=5,
        window_start=datetime.now(UTC),
        as_of=datetime.now(UTC),
        latest_at=None,
    )
    cards = _bundle_with_weather(_weather_section()).model_copy(
        update={"sms": CardSection(status=CardStatus.OK, data=data, generated_at=datetime.now(UTC))}
    )
    text, paid = await llm.generate_synthesis(
        user=_make_user(),
        user_tz=ZoneInfo("Europe/Paris"),
        cards=cards,
        language="fr",
        prompt_sms=_PRIVATE_PROMPT_SMS,
    )
    assert text is None and paid is usage


async def test_real_sms_prompt_reads_are_filed_as_sms_consultations(monkeypatch):
    from uuid import uuid4

    import src.domains.briefing.sms_context as source
    from src.domains.agents.effects.treatments import treatment_collector
    from src.domains.sms.summary import SmsSignal

    owner = uuid4()
    now = datetime.now(UTC)
    data = SmsData(total=2, window_total=1, window_start=now, as_of=now, latest_at=now)
    signal = SmsSignal(
        total=2,
        window_total=1,
        window_start=now,
        as_of=now,
        latest_at=now,
        owner=owner,
        revision=1,
        stamp="stamp",
        messages=[],
    )

    async def read_signal(owner, *, include_bodies, on_read):
        on_read()
        return signal

    monkeypatch.setattr(source, "read_sms_signal", AsyncMock(side_effect=read_signal))
    monkeypatch.setattr(source, "get_effective_context_window_for_slot", lambda slot: 20000)
    with treatment_collector(run_id="briefing-text-read") as rows:
        prompt_sms = await source.read_prompt_sms(
            owner, CardSection(status=CardStatus.OK, data=data, generated_at=now)
        )
    assert prompt_sms.brief and prompt_sms.detailed and prompt_sms.signal is signal
    assert len(rows) == 1 and rows[0].tool_name == "briefing:sms" and rows[0].outcome == "ok"


async def test_sms_withdrawn_during_profile_lookup_is_never_sent_to_a_model(monkeypatch):
    from zoneinfo import ZoneInfo

    import src.domains.briefing.llm as llm

    monkeypatch.setattr(llm, "sms_signal_current", AsyncMock(return_value=False))
    invoke = AsyncMock(return_value=("MUST_NOT_CALL", None))
    monkeypatch.setattr(llm, "_invoke_and_track", invoke)
    monkeypatch.setattr(llm, "_resolve_personality", AsyncMock(return_value=""))
    monkeypatch.setattr(llm, "_resolve_user_model_block", AsyncMock(return_value=""))
    data = SmsData(
        total=1,
        window_total=1,
        window_start=datetime.now(UTC),
        as_of=datetime.now(UTC),
        latest_at=None,
    )
    cards = _bundle_with_weather(_weather_section()).model_copy(
        update={"sms": CardSection(status=CardStatus.OK, data=data, generated_at=datetime.now(UTC))}
    )
    assert await llm.generate_synthesis(
        user=_make_user(),
        user_tz=ZoneInfo("Europe/Paris"),
        cards=cards,
        language="fr",
        prompt_sms=_PRIVATE_PROMPT_SMS,
    ) == (None, None)
    invoke.assert_not_awaited()


async def test_sms_withdrawal_during_greeting_keeps_paid_usage_but_refuses_text(monkeypatch):
    from zoneinfo import ZoneInfo

    import src.domains.briefing.llm as llm
    from src.core.llm_usage import LLMUsage

    usage = LLMUsage(tokens_in=80, tokens_out=9, cost_eur=0.01)
    monkeypatch.setattr(llm, "sms_signal_current", AsyncMock(side_effect=[True, False]))
    monkeypatch.setattr(
        llm, "_invoke_and_track", AsyncMock(return_value=("PAID_PRIVATE_GREETING", usage))
    )
    monkeypatch.setattr(llm, "_resolve_personality", AsyncMock(return_value=""))
    user = _make_user()

    text, paid = await llm.generate_greeting(
        user=user,
        user_tz=ZoneInfo("Europe/Paris"),
        cards=_bundle_with_weather(_weather_section()),
        language="fr",
        prompt_sms=_PRIVATE_PROMPT_SMS,
    )

    assert "PAID_PRIVATE_GREETING" not in text
    assert text == llm.fallback_greeting(user, ZoneInfo("Europe/Paris"), "fr")
    assert paid is usage


async def test_a_failed_greeting_falls_back_and_bills_nothing(monkeypatch):
    from zoneinfo import ZoneInfo

    import src.domains.briefing.llm as llm

    errors = llm.briefing_llm_invocations_total.labels(kind="greeting", outcome="error")
    before = errors._value.get()
    monkeypatch.setattr(llm, "sms_signal_current", AsyncMock(return_value=True))
    monkeypatch.setattr(
        llm, "_invoke_and_track", AsyncMock(side_effect=RuntimeError("provider down"))
    )
    monkeypatch.setattr(llm, "_resolve_personality", AsyncMock(return_value=""))
    user = _make_user()

    text, paid = await llm.generate_greeting(
        user=user,
        user_tz=ZoneInfo("Europe/Paris"),
        cards=_bundle_with_weather(_weather_section()),
        language="fr",
        prompt_sms=_PRIVATE_PROMPT_SMS,
    )

    assert text == llm.fallback_greeting(user, ZoneInfo("Europe/Paris"), "fr")
    assert paid is None
    assert errors._value.get() == before + 1
