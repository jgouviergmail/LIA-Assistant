"""The catalogue row of the image slot's model, inserted on a real PostgreSQL.

The statement is a module constant, so this test runs the SAME SQL the upgrade
runs: on an instance that lacks the row, on one that holds it, and twice.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.models import LLMModel, LLMModelKindEnum, LLMProviderEnum
from tests.helpers.llm_helpers import ensure_llm_model_async

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "2026_11_11_2000-45cf916cc02f_catalogue_row_for_the_image_slot_model.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("catalogue_row_for_the_image_slot", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()
MODEL = MIGRATION.CATALOGUE_ROW["model_name"]


async def _upgrade(session: AsyncSession) -> int:
    result = await session.execute(MIGRATION.INSERT_MODEL, MIGRATION.model_params())
    assert isinstance(result, CursorResult)
    await session.commit()
    session.expire_all()
    return result.rowcount


@pytest.mark.asyncio
async def test_an_instance_lacking_the_row_gets_it(async_session: AsyncSession) -> None:
    assert await _upgrade(async_session) == 1

    row = await async_session.scalar(select(LLMModel).where(LLMModel.model_name == MODEL))
    assert row is not None
    assert row.kind is LLMModelKindEnum.image
    assert row.provider is LLMProviderEnum.openai
    assert row.is_active is True
    assert row.capability_provenance.value == "declared"


@pytest.mark.asyncio
async def test_a_row_an_administrator_holds_stands(async_session: AsyncSession) -> None:
    held = await ensure_llm_model_async(async_session, MODEL, LLMProviderEnum.openai)
    held.is_active = False
    await async_session.commit()

    assert await _upgrade(async_session) == 0

    row = await async_session.scalar(select(LLMModel).where(LLMModel.model_name == MODEL))
    assert row is not None and row.is_active is False


@pytest.mark.asyncio
async def test_a_second_run_changes_nothing(async_session: AsyncSession) -> None:
    assert await _upgrade(async_session) == 1
    assert await _upgrade(async_session) == 0
