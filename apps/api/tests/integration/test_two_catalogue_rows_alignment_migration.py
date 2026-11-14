"""The two-row catalogue correction, executed on a real PostgreSQL.

The statements are module constants, so this test runs the SAME SQL the upgrade
runs: on a live model left with the transcription kind, on a hand-made row that
declares nothing (in both spellings of « nothing »), on values an administrator
chose, on an instance that holds neither row, and twice in a row.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.models import LLMModel, LLMModelKindEnum, LLMProviderEnum
from tests.helpers.llm_helpers import ensure_llm_model_async

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "2026_11_11_1900-43891b5db14c_align_two_catalogue_rows.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("align_two_catalogue_rows", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()
LIVE = MIGRATION.LIVE_MODEL
DEEPSEEK = MIGRATION.DEEPSEEK_MODEL


async def _upgrade(session: AsyncSession) -> tuple[int, int, int]:
    """The upgrade's three statements, on the session's connection."""
    counts = []
    for statement, params in (
        (MIGRATION.FIX_KIND, MIGRATION.kind_params()),
        (MIGRATION.FILL_LADDER, MIGRATION.ladder_params()),
        (MIGRATION.FILL_DOC_KEY, MIGRATION.doc_key_params()),
    ):
        result = await session.execute(statement, params)
        assert isinstance(result, CursorResult)
        counts.append(result.rowcount)
    await session.commit()
    session.expire_all()
    return counts[0], counts[1], counts[2]


async def _live_row(session: AsyncSession, kind: LLMModelKindEnum) -> None:
    model = await ensure_llm_model_async(session, LIVE, LLMProviderEnum.gemini)
    model.kind = kind
    await session.commit()


async def _deepseek_row(session: AsyncSession, *, ladder_sql: str, doc_key: str | None) -> None:
    """A deepseek-flash row whose ladder is written as the given SQL literal."""
    await ensure_llm_model_async(session, DEEPSEEK, LLMProviderEnum.deepseek)
    await session.execute(
        text(
            f"UPDATE llm_models SET reasoning_enum_values = {ladder_sql}, "
            "reasoning_doc_i18n_key = :doc_key WHERE model_name = :model_name"
        ),
        {"doc_key": doc_key, "model_name": DEEPSEEK},
    )
    await session.commit()
    session.expire_all()


async def _row(session: AsyncSession, name: str) -> LLMModel:
    model = await session.scalar(select(LLMModel).where(LLMModel.model_name == name))
    assert model is not None
    return model


async def _ladder_is_sql_null(session: AsyncSession) -> bool:
    return bool(
        await session.scalar(
            text("SELECT reasoning_enum_values IS NULL FROM llm_models WHERE model_name = :name"),
            {"name": DEEPSEEK},
        )
    )


@pytest.mark.asyncio
async def test_a_live_model_left_with_the_transcription_kind_becomes_realtime(
    async_session: AsyncSession,
) -> None:
    await _live_row(async_session, LLMModelKindEnum.audio)

    assert await _upgrade(async_session) == (1, 0, 0)

    assert (await _row(async_session, LIVE)).kind is LLMModelKindEnum.realtime


@pytest.mark.asyncio
async def test_a_kind_an_administrator_chose_stands(async_session: AsyncSession) -> None:
    await _live_row(async_session, LLMModelKindEnum.chat)

    assert await _upgrade(async_session) == (0, 0, 0)

    assert (await _row(async_session, LIVE)).kind is LLMModelKindEnum.chat


@pytest.mark.asyncio
@pytest.mark.parametrize("ladder_sql", ["NULL", "'null'::jsonb"])
async def test_a_row_declaring_nothing_takes_the_ladder_and_its_key(
    async_session: AsyncSession, ladder_sql: str
) -> None:
    """SQL NULL, and the JSON null a row made by hand through the ORM carries."""
    await _deepseek_row(async_session, ladder_sql=ladder_sql, doc_key=None)
    assert await _ladder_is_sql_null(async_session) is (ladder_sql == "NULL")

    assert await _upgrade(async_session) == (0, 1, 1)

    row = await _row(async_session, DEEPSEEK)
    assert row.reasoning_enum_values == MIGRATION.LADDER
    assert row.reasoning_doc_i18n_key == MIGRATION.DOC_KEY


@pytest.mark.asyncio
async def test_a_ladder_an_administrator_narrowed_stands_and_gains_only_its_key(
    async_session: AsyncSession,
) -> None:
    await _deepseek_row(async_session, ladder_sql="""'["none", "high"]'::jsonb""", doc_key=None)

    assert await _upgrade(async_session) == (0, 0, 1)

    row = await _row(async_session, DEEPSEEK)
    assert row.reasoning_enum_values == ["none", "high"]
    assert row.reasoning_doc_i18n_key == MIGRATION.DOC_KEY


@pytest.mark.asyncio
async def test_a_documentation_key_an_administrator_chose_stands(
    async_session: AsyncSession,
) -> None:
    await _deepseek_row(async_session, ladder_sql="NULL", doc_key="their_own_key")

    assert await _upgrade(async_session) == (0, 1, 0)

    assert (await _row(async_session, DEEPSEEK)).reasoning_doc_i18n_key == "their_own_key"


@pytest.mark.asyncio
async def test_an_instance_holding_neither_row_is_left_alone(async_session: AsyncSession) -> None:
    assert await _upgrade(async_session) == (0, 0, 0)

    assert await async_session.scalar(select(LLMModel.id).limit(1)) is None


@pytest.mark.asyncio
async def test_a_second_run_changes_nothing(async_session: AsyncSession) -> None:
    await _live_row(async_session, LLMModelKindEnum.audio)
    await _deepseek_row(async_session, ladder_sql="'null'::jsonb", doc_key=None)
    assert await _upgrade(async_session) == (1, 1, 1)

    assert await _upgrade(async_session) == (0, 0, 0)
