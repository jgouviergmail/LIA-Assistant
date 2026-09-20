"""The audio rate pair through the service: persisted, inherited, cleared, judged merged.

ADR-300 wave 3. The schema sees one payload; the service sees the MERGED
state (payload over the current row), which is where half a pair or a pair
beside a switched unit can only be caught — the time slots' own doctrine.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.schemas import ModelPriceCreate, ModelPriceUpdate
from src.domains.llm.service import AudioRatesMergeError, LLMModelService

pytestmark = pytest.mark.unit

_CREATE_FIELDS: dict[str, Any] = {
    "provider": "gemini",
    "kind": "realtime",
    "max_input_tokens": 8192,
    "max_output_tokens": 4096,
    "supports_tools": True,
    "supports_structured_output": False,
    "supports_strict_mode": False,
    "supports_streaming": True,
    "supports_vision": False,
    "supports_temperature": False,
    "supports_top_p": False,
    "supports_frequency_penalty": False,
    "supports_presence_penalty": False,
    "is_reasoning_model": False,
    "input_unit_price": Decimal("0.75"),
    "cached_input_unit_price": None,
    "output_unit_price": Decimal("4.5"),
}


def _create(model_name: str, **overrides: Any) -> ModelPriceCreate:
    return ModelPriceCreate(model_name=model_name, **{**_CREATE_FIELDS, **overrides})


async def _priced(service: LLMModelService, name: str) -> LLMModelService:
    await service.create(
        _create(name, audio_input_unit_price=Decimal("3"), audio_output_unit_price=Decimal("12"))
    )
    return service


async def test_create_persists_the_pair(async_session: AsyncSession) -> None:
    service = LLMModelService(async_session)
    _, pricing = await service.create(
        _create(
            "live-pair", audio_input_unit_price=Decimal("3"), audio_output_unit_price=Decimal("12")
        )
    )
    assert (pricing.audio_input_unit_price, pricing.audio_output_unit_price) == (
        Decimal("3"),
        Decimal("12"),
    )


async def test_a_text_price_bump_inherits_the_pair(async_session: AsyncSession) -> None:
    service = await _priced(LLMModelService(async_session), "live-inherit")
    _, updated = await service.update(
        "live-inherit", ModelPriceUpdate(input_unit_price=Decimal("1"))
    )
    assert updated is not None
    assert (updated.audio_input_unit_price, updated.audio_output_unit_price) == (
        Decimal("3"),
        Decimal("12"),
    )


async def test_one_rate_may_change_alone_when_the_other_is_inherited(
    async_session: AsyncSession,
) -> None:
    service = await _priced(LLMModelService(async_session), "live-half-update")
    _, updated = await service.update(
        "live-half-update", ModelPriceUpdate(audio_output_unit_price=Decimal("10"))
    )
    assert updated is not None
    assert (updated.audio_input_unit_price, updated.audio_output_unit_price) == (
        Decimal("3"),
        Decimal("10"),
    )


async def test_the_pair_is_cleared_through_its_own_flag(async_session: AsyncSession) -> None:
    service = await _priced(LLMModelService(async_session), "live-clear")
    _, updated = await service.update("live-clear", ModelPriceUpdate(clear_audio_prices=True))
    assert updated is not None
    assert updated.audio_input_unit_price is None
    assert updated.audio_output_unit_price is None
    # and the text prices survived the clearing
    assert updated.input_unit_price == Decimal("0.75")


async def test_half_a_pair_on_a_row_that_had_none_is_refused(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    await service.create(_create("live-no-pair"))
    with pytest.raises(AudioRatesMergeError, match="together"):
        await service.update("live-no-pair", ModelPriceUpdate(audio_input_unit_price=Decimal("3")))


async def test_switching_to_a_minute_unit_while_the_pair_survives_is_refused(
    async_session: AsyncSession,
) -> None:
    service = await _priced(LLMModelService(async_session), "live-unit-switch")
    with pytest.raises(AudioRatesMergeError, match="per_1m_tokens"):
        await service.update("live-unit-switch", ModelPriceUpdate(pricing_unit="per_audio_minute"))

    # Clearing alongside the switch is the legal one-call form.
    _, updated = await service.update(
        "live-unit-switch",
        ModelPriceUpdate(pricing_unit="per_audio_minute", clear_audio_prices=True),
    )
    assert updated is not None
    assert updated.audio_input_unit_price is None
    assert updated.pricing_unit.value == "per_audio_minute"


async def test_clearing_alone_writes_a_new_tariff_version(async_session: AsyncSession) -> None:
    service = LLMModelService(async_session)
    _, first = await service.create(
        _create(
            "live-clear-version",
            audio_input_unit_price=Decimal("3"),
            audio_output_unit_price=Decimal("12"),
        )
    )
    _, updated = await service.update(
        "live-clear-version", ModelPriceUpdate(clear_audio_prices=True)
    )
    assert updated is not None and updated.id != first.id
    assert first.is_active is False
