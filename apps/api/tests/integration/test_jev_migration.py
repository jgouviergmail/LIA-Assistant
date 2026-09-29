"""Native catalogue seeding preserves administered models and prices on PostgreSQL."""

import importlib.util
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.models import LLMModel, LLMModelPricing

pytestmark = pytest.mark.integration


def _migration():
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/2026_09_28_2101-b138c047a5d2_seed_jev.py"
    )
    spec = importlib.util.spec_from_file_location("seed_jev", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_seed_is_repeatable_and_preserves_operator_price(async_session: AsyncSession) -> None:
    migration = _migration()
    for _ in range(2):
        await async_session.execute(migration.INSERT_MODEL)
        await async_session.execute(migration.INSERT_TARIFF)
    await async_session.flush()
    model = (
        await async_session.scalars(select(LLMModel).where(LLMModel.model_name == "jev-1.13.0"))
    ).one()
    price = (
        await async_session.scalars(
            select(LLMModelPricing).where(LLMModelPricing.model_id == model.id)
        )
    ).one()
    assert model.provider.value == "typesafe" and model.kind.value == "decision"
    assert not model.supports_structured_output and not model.supports_temperature
    assert model.capability_provenance.value == "verified"
    assert price.input_unit_price == Decimal(".042") and price.output_unit_price == 0
    model.max_input_tokens = 1234
    price.input_unit_price = Decimal(".05")
    await async_session.flush()
    await async_session.execute(migration.INSERT_MODEL)
    await async_session.execute(migration.INSERT_TARIFF)
    await async_session.refresh(model)
    await async_session.refresh(price)
    assert model.max_input_tokens == 1234 and price.input_unit_price == Decimal(".05")


@pytest.mark.parametrize(
    "operator_edit",
    [
        "UPDATE llm_model_pricing SET input_unit_price = 0.05 WHERE model_id = 'b3aceb9c-bd2a-4cb6-a0ab-cd9108e4e128'",
        "UPDATE llm_models SET max_input_tokens = 1234 WHERE model_name = 'jev-1.13.0'",
        "UPDATE llm_models SET model_name = 'jev-custom' WHERE model_name = 'jev-1.13.0'",
    ],
)
async def test_downgrade_refuses_operator_data_even_without_timestamp_update(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, operator_edit: str
) -> None:
    migration = _migration()
    await async_session.execute(migration.INSERT_MODEL)
    await async_session.execute(migration.INSERT_TARIFF)
    await async_session.execute(text(operator_edit))

    def downgrade(sync_session):
        connection = sync_session.connection()
        monkeypatch.setattr(
            migration,
            "op",
            SimpleNamespace(
                get_bind=lambda: connection,
                execute=connection.execute,
            ),
        )
        migration.downgrade()

    with pytest.raises(RuntimeError, match="preserve operator data"):
        await async_session.run_sync(downgrade)
    assert (
        await async_session.scalar(
            select(LLMModel.id).where(LLMModel.id == "b3aceb9c-bd2a-4cb6-a0ab-cd9108e4e128")
        )
        is not None
    )
