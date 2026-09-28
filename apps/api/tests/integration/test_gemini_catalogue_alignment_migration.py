"""The 2026-09-26 Gemini catalogue alignment, executed on a real PostgreSQL.

The upgrade is six statement constants; this test runs the SAME SQL against
rows shaped like the ones an instance holds: an empty catalogue (a fresh
install), an imported row carrying the registry's shutdown date, a row an
administrator curated, a model the API no longer serves with and without a
slot configured on it, an embedding filed under the wrong provider — and
twice in a row.
"""

from __future__ import annotations

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from src.domains.llm.models import (
    LLMCapabilityProvenanceEnum,
    LLMModel,
    LLMModelKindEnum,
    LLMModelPricing,
    LLMProviderEnum,
)
from src.domains.llm_config.models import LLMConfigOverride
from tests.helpers.llm_helpers import create_llm_pricing_async, ensure_llm_model_async

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "2026_09_26_1800-70fd39bf9e8d_align_gemini_catalogue_on_google.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("align_gemini_catalogue", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()


async def _count(session: AsyncSession, statement: TextClause, params: dict[str, Any]) -> int:
    result = await session.execute(statement, params)
    assert isinstance(result, CursorResult)
    return result.rowcount


async def _upgrade(session: AsyncSession) -> tuple[int, int, int, int, int]:
    inserted = aligned = dated = retired = refiled = 0
    for name in MIGRATION.CATALOGUE:
        inserted += await _count(session, MIGRATION.INSERT_MODEL, MIGRATION.model_params(name))
    for name in MIGRATION.CATALOGUE:
        aligned += await _count(session, MIGRATION.ALIGN_CAPABILITIES, MIGRATION.model_params(name))
    for name, day in MIGRATION.SHUTDOWN_DATES.items():
        dated += await _count(
            session, MIGRATION.ALIGN_SHUTDOWN_DATE, {"model_name": name, "deprecation_date": day}
        )
    for name in MIGRATION.NOT_SERVED:
        retired += await _count(session, MIGRATION.DEACTIVATE_NOT_SERVED, {"model_name": name})
        await session.execute(MIGRATION.RETIRE_NOT_SERVED_TARIFF, {"model_name": name})
    for name in MIGRATION.GOOGLE_EMBEDDINGS:
        refiled += await _count(session, MIGRATION.FILE_UNDER_GEMINI, {"model_name": name})
    await session.commit()
    return inserted, aligned, dated, retired, refiled


async def _model(session: AsyncSession, name: str) -> LLMModel:
    model = await session.scalar(select(LLMModel).where(LLMModel.model_name == name))
    assert model is not None
    await session.refresh(model)
    return model


async def _imported(session: AsyncSession, name: str, **values: object) -> LLMModel:
    model = await ensure_llm_model_async(session, name, LLMProviderEnum.gemini)
    model.capability_provenance = LLMCapabilityProvenanceEnum.imported
    for column, value in values.items():
        setattr(model, column, value)
    await session.flush()
    return model


@pytest.mark.asyncio
async def test_a_fresh_catalogue_gets_the_sixteen_verified(async_session: AsyncSession) -> None:
    inserted, aligned, dated, _, _ = await _upgrade(async_session)

    assert (inserted, aligned) == (len(MIGRATION.CATALOGUE), 0)
    assert dated == 1  # gemini-3.1-flash-lite: the others are NULL already
    flash = await _model(async_session, "gemini-3.7-flash")
    assert flash.capability_provenance is LLMCapabilityProvenanceEnum.verified
    assert (flash.max_input_tokens, flash.max_output_tokens) == (1_048_576, 65_536)
    assert flash.supports_frequency_penalty is True
    speech = await _model(async_session, "gemini-2.5-pro-preview-tts")
    assert speech.kind is LLMModelKindEnum.tts
    assert speech.supports_temperature is False
    assert (await _model(async_session, "gemini-3.1-flash-lite")).deprecation_date == date(
        2027, 5, 7
    )


@pytest.mark.asyncio
async def test_an_uncurated_row_takes_the_vendors_values(async_session: AsyncSession) -> None:
    await _imported(
        async_session,
        "gemini-2.5-flash",
        max_input_tokens=1_000_000,
        deprecation_date=date(2026, 10, 20),
    )
    await _imported(
        async_session,
        "gemini-2.5-pro-preview-tts",
        max_input_tokens=1_048_576,
        supports_structured_output=True,
        kind=LLMModelKindEnum.tts,
    )
    await async_session.commit()

    _, aligned, _, _, _ = await _upgrade(async_session)

    assert aligned == 2
    flash = await _model(async_session, "gemini-2.5-flash")
    assert flash.max_input_tokens == 1_048_576
    assert flash.deprecation_date is None
    assert flash.reasoning_enum_values == ["low", "medium", "high"]
    assert flash.capability_provenance is LLMCapabilityProvenanceEnum.verified
    speech = await _model(async_session, "gemini-2.5-pro-preview-tts")
    assert (speech.max_input_tokens, speech.max_output_tokens) == (8_192, 16_384)
    assert speech.supports_structured_output is False


@pytest.mark.asyncio
async def test_a_curated_row_keeps_its_values_but_follows_the_announced_shutdown(
    async_session: AsyncSession,
) -> None:
    """An administrator curated gemini-3.1-flash-lite: only the vendor's date moves."""
    model = await ensure_llm_model_async(
        async_session, "gemini-3.1-flash-lite", LLMProviderEnum.gemini
    )
    model.capability_provenance = LLMCapabilityProvenanceEnum.verified
    model.max_input_tokens = 500_000
    await async_session.commit()

    await _upgrade(async_session)

    curated = await _model(async_session, "gemini-3.1-flash-lite")
    assert curated.max_input_tokens == 500_000
    assert curated.deprecation_date == date(2027, 5, 7)


@pytest.mark.asyncio
async def test_a_model_the_api_no_longer_serves_leaves_unless_a_slot_runs_on_it(
    async_session: AsyncSession,
) -> None:
    for name in ("gemini-2.0-flash", "gemini-3.1-flash-preview-tts"):
        await create_llm_pricing_async(
            async_session,
            model_name=name,
            input_price=Decimal("0.10"),
            output_price=Decimal("0.40"),
            provider=LLMProviderEnum.gemini,
        )
    async_session.add(
        LLMConfigOverride(llm_type="router", provider="gemini", model="gemini-2.0-flash")
    )
    await async_session.commit()

    retired = (await _upgrade(async_session))[3]

    assert retired == 1
    assert (await _model(async_session, "gemini-2.0-flash")).is_active is True
    gone = await _model(async_session, "gemini-3.1-flash-preview-tts")
    assert gone.is_active is False
    active_tariffs = (
        await async_session.scalars(
            select(LLMModelPricing).where(
                LLMModelPricing.model_id == gone.id, LLMModelPricing.is_active
            )
        )
    ).all()
    assert active_tariffs == []
    assert (await _model(async_session, "gemini-2.0-flash")).deprecation_date == date(2026, 6, 1)


@pytest.mark.asyncio
async def test_a_google_embedding_filed_elsewhere_moves_under_gemini(
    async_session: AsyncSession,
) -> None:
    await ensure_llm_model_async(async_session, "embedding-001", LLMProviderEnum.openai)
    await async_session.commit()

    assert (await _upgrade(async_session))[4] == 1
    embedding = await _model(async_session, "embedding-001")
    assert embedding.provider is LLMProviderEnum.gemini
    assert embedding.is_active is False


@pytest.mark.asyncio
async def test_a_second_run_changes_nothing(async_session: AsyncSession) -> None:
    await _imported(async_session, "gemini-3.7-flash", max_output_tokens=64_000)
    await _imported(async_session, "gemini-3.5-flash", deprecation_date=date(2027, 5, 19))
    await async_session.commit()

    first = await _upgrade(async_session)
    assert first[1] == 2
    assert await _upgrade(async_session) == (0, 0, 0, 0, 0)
    assert (await _model(async_session, "gemini-3.7-flash")).max_output_tokens == 65_536
