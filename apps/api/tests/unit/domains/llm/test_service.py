"""Unit tests for LLMModelService (transactional model+pricing orchestration).

Note on asyncio markers: this project sets ``asyncio_mode = "auto"`` in
``pyproject.toml`` — ``async def`` test functions are run automatically
without an explicit ``@pytest.mark.asyncio`` marker.
"""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.schemas import ModelPriceCreate, ModelPriceUpdate
from src.domains.llm.service import LLMModelService

_BASE_CREATE_FIELDS = {
    "max_input_tokens": 1000,
    "max_output_tokens": 200,
    "supports_tools": True,
    "supports_structured_output": True,
    "supports_strict_mode": False,
    "supports_streaming": True,
    "supports_vision": False,
    "is_reasoning_model": False,
}


def _make_create(model_name: str, **overrides) -> ModelPriceCreate:
    return ModelPriceCreate(
        provider="openai",
        model_name=model_name,
        input_price_per_1m_tokens=Decimal("1.0"),
        cached_input_price_per_1m_tokens=None,
        output_price_per_1m_tokens=Decimal("3.0"),
        **{**_BASE_CREATE_FIELDS, **overrides},
    )


@pytest.mark.unit
async def test_create_inserts_model_and_pricing_atomically(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    model, pricing = await service.create(_make_create("svc-1"))

    assert model.model_name == "svc-1"
    assert model.is_active is True
    assert pricing.model_id == model.id
    assert pricing.is_active is True
    assert pricing.input_price_per_1m_tokens == Decimal("1.0")


@pytest.mark.unit
async def test_create_raises_value_error_when_model_name_already_exists(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    await service.create(_make_create("svc-dup"))
    await async_session.commit()
    with pytest.raises(ValueError, match="already exists"):
        await service.create(_make_create("svc-dup"))


@pytest.mark.unit
async def test_update_capabilities_only_mutates_in_place_no_new_pricing_row(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    model, pricing = await service.create(_make_create("svc-cap"))
    await async_session.commit()

    update = ModelPriceUpdate(max_output_tokens=9999, supports_vision=True)
    new_model, new_pricing = await service.update("svc-cap", update)

    assert new_model.max_output_tokens == 9999
    assert new_model.supports_vision is True
    assert new_pricing is None  # no pricing row created
    # Original pricing row still active
    await async_session.refresh(pricing)
    assert pricing.is_active is True


@pytest.mark.unit
async def test_update_pricing_only_creates_new_versioned_row_and_deactivates_old(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    model, old_pricing = await service.create(_make_create("svc-price"))
    await async_session.commit()

    update = ModelPriceUpdate(input_price_per_1m_tokens=Decimal("2.5"))
    new_model, new_pricing = await service.update("svc-price", update)

    assert new_pricing is not None
    assert new_pricing.input_price_per_1m_tokens == Decimal("2.5")
    assert new_pricing.is_active is True
    # Output price preserved from old row (only input changed)
    assert new_pricing.output_price_per_1m_tokens == Decimal("3.0")
    # Old row deactivated
    await async_session.refresh(old_pricing)
    assert old_pricing.is_active is False


@pytest.mark.unit
async def test_update_mixed_does_both_in_one_transaction(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    model, old_pricing = await service.create(_make_create("svc-mixed"))
    await async_session.commit()

    update = ModelPriceUpdate(
        max_output_tokens=4242,
        input_price_per_1m_tokens=Decimal("5.0"),
    )
    new_model, new_pricing = await service.update("svc-mixed", update)

    assert new_model.max_output_tokens == 4242
    assert new_pricing is not None
    assert new_pricing.input_price_per_1m_tokens == Decimal("5.0")
    await async_session.refresh(old_pricing)
    assert old_pricing.is_active is False


@pytest.mark.unit
async def test_update_renames_model_on_llm_models(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    model, _ = await service.create(_make_create("svc-rename-old"))
    await async_session.commit()

    update = ModelPriceUpdate(model_name="svc-rename-new")
    new_model, new_pricing = await service.update("svc-rename-old", update)

    assert new_model.model_name == "svc-rename-new"
    # Pure rename → no new pricing row
    assert new_pricing is None


@pytest.mark.unit
async def test_update_rename_conflict_raises_value_error(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    await service.create(_make_create("svc-existing"))
    await service.create(_make_create("svc-other"))
    await async_session.commit()

    with pytest.raises(ValueError, match="already exists"):
        await service.update("svc-other", ModelPriceUpdate(model_name="svc-existing"))


@pytest.mark.unit
async def test_update_raises_lookup_error_when_model_missing(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    with pytest.raises(LookupError):
        await service.update(
            "no-such-model", ModelPriceUpdate(input_price_per_1m_tokens=Decimal("1.0"))
        )


@pytest.mark.unit
async def test_deactivate_disables_model_and_active_pricing(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    model, pricing = await service.create(_make_create("svc-deact"))
    await async_session.commit()

    await service.deactivate("svc-deact")

    await async_session.refresh(model)
    await async_session.refresh(pricing)
    assert model.is_active is False
    assert pricing.is_active is False


@pytest.mark.unit
async def test_deactivate_raises_lookup_error_when_missing(
    async_session: AsyncSession,
) -> None:
    service = LLMModelService(async_session)
    with pytest.raises(LookupError):
        await service.deactivate("no-such-model")
