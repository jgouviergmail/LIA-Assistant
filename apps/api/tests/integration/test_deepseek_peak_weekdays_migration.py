"""The DeepSeek weekday migration, executed on a real PostgreSQL.

A unit test cannot see what this migration does: its whole behaviour is a
JSONB rewrite inside one UPDATE. The statements are module constants so the
test runs the SAME SQL the upgrade runs, against rows shaped like the ones
measured on production and dev on 2026-09-23 (three DeepSeek tariffs, one of
them entered through the admin UI), and then asks the runtime resolver what
a weekend call costs.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.models import LLMModelPricing, LLMProviderEnum
from src.domains.llm.pricing_time_slots import find_active_slot
from tests.helpers.llm_helpers import create_llm_pricing_async

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "2026_09_23_1200-e4a7c2f9b1d6_deepseek_peak_weekdays.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("deepseek_peak_weekdays", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load_migration()


def _window(start: str, end: str, price: float, **extra: Any) -> dict[str, Any]:
    return {
        "start_utc": start,
        "end_utc": end,
        "input_unit_price": price,
        "cached_input_unit_price": price / 50,
        "output_unit_price": price * 4,
        **extra,
    }


VENDOR_SLOTS = [_window("01:00", "04:00", 0.3), _window("06:00", "10:00", 0.3)]


async def _tariff(
    session: AsyncSession,
    model_name: str,
    slots: list[dict[str, Any]],
    *,
    provider: LLMProviderEnum = LLMProviderEnum.deepseek,
    is_active: bool = True,
) -> LLMModelPricing:
    pricing = await create_llm_pricing_async(
        session,
        model_name=model_name,
        input_price=Decimal("0.15"),
        output_price=Decimal("0.60"),
        cached_input_price=Decimal("0.003"),
        provider=provider,
        is_active=is_active,
    )
    await session.execute(
        update(LLMModelPricing).where(LLMModelPricing.id == pricing.id).values(time_slots=slots)
    )
    await session.commit()
    return pricing


async def _slots(session: AsyncSession, pricing: LLMModelPricing) -> list[dict[str, Any]]:
    await session.refresh(pricing)
    return list(pricing.time_slots or [])


async def _upgrade(session: AsyncSession) -> int:
    result = await session.execute(MIGRATION.ADD_WEEKDAYS, MIGRATION.statement_params())
    await session.commit()
    return int(result.rowcount)


async def _downgrade(session: AsyncSession) -> int:
    result = await session.execute(MIGRATION.REMOVE_WEEKDAYS)
    await session.commit()
    return int(result.rowcount)


@pytest.mark.asyncio
async def test_the_vendor_windows_of_every_active_deepseek_tariff_learn_their_days(
    async_session: AsyncSession,
) -> None:
    pro_slots = [_window("01:00", "04:00", 1.32), _window("06:00", "10:00", 1.32)]
    flash = await _tariff(async_session, "deepseek-flash", VENDOR_SLOTS)
    pro = await _tariff(async_session, "deepseek-v4-pro", pro_slots)

    assert await _upgrade(async_session) == 2

    # The days are ADDED: every other key of every window, and the order of
    # the windows, is what it was.
    days = {"weekdays": MIGRATION.WEEKDAYS}
    assert await _slots(async_session, flash) == [{**slot, **days} for slot in VENDOR_SLOTS]
    assert await _slots(async_session, pro) == [{**slot, **days} for slot in pro_slots]


@pytest.mark.asyncio
async def test_the_resolver_now_prices_a_weekend_peak_hour_off_peak(
    async_session: AsyncSession,
) -> None:
    flash = await _tariff(async_session, "deepseek-flash", VENDOR_SLOTS)
    await _upgrade(async_session)
    slots = await _slots(async_session, flash)

    saturday_0200 = datetime(2026, 9, 19, 2, 0, tzinfo=UTC)
    tuesday_0200 = datetime(2026, 9, 22, 2, 0, tzinfo=UTC)
    assert find_active_slot(slots, saturday_0200) is None
    assert find_active_slot(slots, tuesday_0200) is not None


@pytest.mark.asyncio
async def test_what_an_administrator_shaped_is_left_as_it_is(
    async_session: AsyncSession,
) -> None:
    """A reshaped window, a window already carrying days, a superseded tariff
    and another provider's identical hours are none of this migration's business."""
    reshaped = await _tariff(
        async_session,
        "deepseek-v4-flash",
        [_window("02:00", "04:00", 0.44), _window("06:00", "10:00", 0.44, weekdays=[1, 2, 3])],
    )
    history = await _tariff(async_session, "deepseek-chat", VENDOR_SLOTS, is_active=False)
    other = await _tariff(
        async_session, "gpt-probe-windows", VENDOR_SLOTS, provider=LLMProviderEnum.openai
    )

    assert await _upgrade(async_session) == 0

    assert await _slots(async_session, reshaped) == [
        _window("02:00", "04:00", 0.44),
        _window("06:00", "10:00", 0.44, weekdays=[1, 2, 3]),
    ]
    assert await _slots(async_session, history) == VENDOR_SLOTS
    assert await _slots(async_session, other) == VENDOR_SLOTS


@pytest.mark.asyncio
async def test_a_second_run_settles_nothing(async_session: AsyncSession) -> None:
    flash = await _tariff(async_session, "deepseek-flash", VENDOR_SLOTS)
    assert await _upgrade(async_session) == 1
    first = await _slots(async_session, flash)

    assert await _upgrade(async_session) == 0
    assert await _slots(async_session, flash) == first


@pytest.mark.asyncio
async def test_the_downgrade_leaves_no_day_the_previous_revision_cannot_read(
    async_session: AsyncSession,
) -> None:
    """The revision before this one reads no ``weekdays``: its ``TimeSlotPrice``
    forbids unknown keys, so ONE day left anywhere — the upgrade's, or one an
    administrator entered since — fails its admin listing, and its pricing
    ignored the days anyway. The inverse is therefore a dropped column, whoever
    wrote the days, with every other key and the order of the windows kept."""
    flash = await _tariff(async_session, "deepseek-flash", VENDOR_SLOTS)
    await _upgrade(async_session)
    entered = [
        _window("01:00", "04:00", 0.44),
        _window("06:00", "10:00", 0.44, weekdays=[1, 2, 3]),
    ]
    mixed = await _tariff(async_session, "deepseek-v4-flash", entered)
    other = await _tariff(
        async_session,
        "gpt-probe-windows",
        [_window("22:00", "02:00", 0.5, weekdays=[6, 7])],
        provider=LLMProviderEnum.openai,
    )
    history = await _tariff(
        async_session,
        "deepseek-chat",
        [_window("01:00", "04:00", 0.3, weekdays=[1])],
        is_active=False,
    )
    untouched = await _tariff(async_session, "deepseek-reasoner", VENDOR_SLOTS)

    # Four rows carry a day; the fifth, which carries none, is not rewritten.
    assert await _downgrade(async_session) == 4

    assert await _slots(async_session, flash) == VENDOR_SLOTS
    assert await _slots(async_session, mixed) == [
        _window("01:00", "04:00", 0.44),
        _window("06:00", "10:00", 0.44),
    ]
    assert await _slots(async_session, other) == [_window("22:00", "02:00", 0.5)]
    assert await _slots(async_session, history) == [_window("01:00", "04:00", 0.3)]
    assert await _slots(async_session, untouched) == VENDOR_SLOTS
