"""Dashboard previews are explicit personal reads, never implicit model evidence."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.briefing.schemas import SmsData
from src.domains.sms.summary import SmsSummary

pytestmark = pytest.mark.unit


async def test_only_card_delivery_requests_previews(monkeypatch):
    import src.domains.briefing.sms_context as source

    now = datetime.now(UTC)
    summary = SmsSummary(total=1, window_total=0, window_start=now, as_of=now, latest_at=now)
    metadata = AsyncMock(return_value=summary)
    preview = AsyncMock(return_value=SmsData(**summary.model_dump()))
    monkeypatch.setattr(source.settings, "sms_enabled", True)
    monkeypatch.setattr(source, "read_sms_summary", metadata)
    monkeypatch.setattr(source, "read_sms_card", preview, raising=False)
    owner = uuid4()
    await source.fetch_sms(user_id=owner)
    metadata.assert_awaited_once_with(owner)
    preview.assert_not_awaited()
    await source.fetch_sms(user_id=owner, include_messages=True)
    preview.assert_awaited_once_with(owner)
    assert metadata.await_count == 1


def test_personal_card_excerpts_never_enter_generic_prompt_projection():
    from src.domains.briefing.prompt_cards import _summarize_cards_for_llm
    from src.domains.briefing.schemas import CardSection, CardStatus
    from tests.unit.domains.briefing.test_llm import _bundle_with_weather, _weather_section

    now = datetime.now(UTC)
    data = SmsData(
        total=1,
        window_total=0,
        window_start=now,
        as_of=now,
        latest_at=now,
        items=[
            {
                "id": uuid4(),
                "sender": "PRIVATE_SENDER",
                "display_name": "PRIVATE_PERSON",
                "received_at": now,
                "date_kind": "received",
                "body_excerpt": "CARD_ONLY_CANARY",
                "body_truncated": False,
            }
        ],
    )
    cards = _bundle_with_weather(_weather_section()).model_copy(
        update={"sms": CardSection(status=CardStatus.OK, data=data, generated_at=now)}
    )
    for verbose in (False, True):
        text = _summarize_cards_for_llm(cards, verbose=verbose)
        assert "CARD_ONLY_CANARY" not in text and "PRIVATE_" not in text


async def test_ui_and_shared_worker_bundles_keep_previews_out_of_other_readers(monkeypatch):
    import src.domains.briefing.service as module
    from src.domains.briefing.schemas import CardSection, CardStatus
    from tests.unit.domains.briefing.test_service import _make_user

    now = datetime.now(UTC)
    base = {"total": 1, "window_total": 1, "window_start": now, "as_of": now, "latest_at": now}
    item = {
        "id": uuid4(),
        "sender": "Alice",
        "display_name": "Alice",
        "received_at": now,
        "date_kind": "received",
        "body_excerpt": "Visible personal preview",
        "body_truncated": False,
    }

    async def fetch(*, user_id, include_messages=False):
        return SmsData(**base, items=[item] if include_messages else [])

    monkeypatch.setattr(module, "fetch_sms", fetch)
    service = module.BriefingService(_make_user())
    service._read_cache = AsyncMock(
        return_value=CardSection(status=CardStatus.EMPTY, generated_at=now)
    )
    published = await service._published_bundle()
    assert (
        published is not None
        and published.sms.data.items[0].body_excerpt == "Visible personal preview"
    )
    cached, _ = await service._read_cached_bundle()
    assert cached.sms.data.items == []
    selected = next(plan for plan in service._build_plan(frozenset()) if plan.name == "sms")
    assert (await selected.fetcher()).items == []


async def test_withdrawn_previews_are_removed_before_a_bundle_leaves_the_service(monkeypatch):
    import src.domains.briefing.sms_context as source
    from src.domains.briefing.schemas import CardSection, CardStatus
    from tests.unit.domains.briefing.test_llm import _bundle_with_weather, _weather_section

    now = datetime.now(UTC)
    data = SmsData(
        total=1,
        window_total=1,
        window_start=now,
        as_of=now,
        latest_at=now,
        items=[
            {
                "id": uuid4(),
                "sender": "Alice",
                "display_name": "Alice",
                "received_at": now,
                "date_kind": "received",
                "body_excerpt": "WITHDRAWN_PRIVATE_SMS",
                "body_truncated": False,
            }
        ],
    )
    cards = _bundle_with_weather(_weather_section()).model_copy(
        update={"sms": CardSection(status=CardStatus.OK, data=data, generated_at=now)}
    )
    monkeypatch.setattr(source, "sms_card_current", AsyncMock(return_value=False), raising=False)
    guarded = await source.revalidate_sms_card(cards)
    assert guarded.sms.status is CardStatus.ERROR and guarded.sms.data is None
    assert "WITHDRAWN_PRIVATE_SMS" not in guarded.model_dump_json()


async def test_global_refresh_withdraws_sms_erased_while_text_is_generated(monkeypatch):
    import src.domains.briefing.sms_context as source
    from src.domains.briefing.schemas import CardSection, CardStatus, SynthesisResponse, TextSection
    from src.domains.briefing.service import BriefingService
    from tests.unit.domains.briefing.test_llm import _bundle_with_weather, _weather_section
    from tests.unit.domains.briefing.test_service import _make_user

    now = datetime.now(UTC)
    data = SmsData(
        total=1,
        window_total=1,
        window_start=now,
        as_of=now,
        latest_at=now,
        items=[
            {
                "id": uuid4(),
                "sender": "Alice",
                "display_name": "Alice",
                "received_at": now,
                "date_kind": "received",
                "body_excerpt": "ERASED_DURING_TEXT",
                "body_truncated": False,
            }
        ],
    )
    cards = _bundle_with_weather(_weather_section()).model_copy(
        update={"sms": CardSection(status=CardStatus.OK, data=data, generated_at=now)}
    )
    service = BriefingService(_make_user())
    service.build_cards = AsyncMock(return_value=cards)

    async def generate_text(*, cards):
        # The source was current at build_cards; erasure commits during model IO.
        monkeypatch.setattr(source, "sms_card_current", AsyncMock(return_value=False))
        return SynthesisResponse(greeting=TextSection(text="Hello", generated_at=now))

    service.build_text = AsyncMock(side_effect=generate_text)
    result = await service.build_today(force_refresh={"all"})
    assert result.cards.sms.status is CardStatus.ERROR
    assert "ERASED_DURING_TEXT" not in result.model_dump_json()
    assert result.greeting.text == "Hello"
