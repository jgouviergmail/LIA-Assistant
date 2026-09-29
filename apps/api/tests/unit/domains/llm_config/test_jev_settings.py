"""Routing is default-off, operation-scoped and independent of Redis."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm.pricing_service import ModelPrice
from src.domains.llm_config import jev_settings as module
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import DecisionConfiguration, load_jev_snapshot

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("global_on,local_on", [(False, False), (False, True), (True, False)])
async def test_off_never_even_loads_credentials(global_on: bool, local_on: bool) -> None:
    with (
        patch.object(
            module,
            "read_flags",
            AsyncMock(return_value={"global": global_on, "meeting_template": local_on}),
        ),
        patch.object(module, "read_configuration", AsyncMock()) as configuration,
        patch("src.infrastructure.database.get_db_context", _session),
    ):
        snapshot = await load_jev_snapshot(JevUsage.MEETING_TEMPLATE)
    assert not snapshot.requested
    assert snapshot.configuration is None
    configuration.assert_not_awaited()


@asynccontextmanager
async def _session() -> AsyncIterator[AsyncSession]:
    yield AsyncMock(spec=AsyncSession)


async def test_next_operation_reads_the_new_switch_and_old_snapshot_is_stable() -> None:
    config = DecisionConfiguration(
        "jev-1.13.0",
        2,
        SecretStr("test-secret"),
        ModelPrice(
            "jev-1.13.0", Decimal(".042"), None, Decimal(0), "per_1m_tokens", datetime.now(UTC)
        ),
    )
    flags = AsyncMock(
        side_effect=[
            {"global": True, "meeting_template": True},
            {"global": False, "meeting_template": True},
        ]
    )
    with (
        patch.object(module, "read_flags", flags),
        patch.object(module, "read_configuration", AsyncMock(return_value=("ready", config))),
        patch("src.infrastructure.database.get_db_context", _session),
    ):
        first = await load_jev_snapshot(JevUsage.MEETING_TEMPLATE)
        second = await load_jev_snapshot(JevUsage.MEETING_TEMPLATE)
    assert first.configuration == config and first.requested
    assert not second.requested and second.configuration is None
    assert "test-secret" not in repr(first)


async def test_database_outage_chooses_existing_path() -> None:
    with (
        patch.object(module, "read_flags", AsyncMock(side_effect=OSError("database unavailable"))),
        patch("src.infrastructure.database.get_db_context", _session),
    ):
        snapshot = await load_jev_snapshot(JevUsage.MEETING_TEMPLATE)
    assert not snapshot.requested
    assert snapshot.configuration is None
    assert snapshot.readiness == "unavailable"


async def test_slow_configuration_read_is_bounded() -> None:
    async def slow_flags(db: AsyncSession) -> dict[str, bool]:
        await asyncio.sleep(10)
        return {}

    with (
        patch.object(module, "read_flags", slow_flags),
        patch.object(module, "CONFIGURATION_TIMEOUT_SECONDS", 0.01, create=True),
        patch("src.infrastructure.database.get_db_context", _session),
    ):
        snapshot = await asyncio.wait_for(load_jev_snapshot(JevUsage.MEETING_TEMPLATE), 0.2)
    assert snapshot.readiness == "unavailable"
