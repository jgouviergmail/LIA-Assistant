"""The statistics read lists every usage, rows or not, in five statements (ADR-374)."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.llm_config import jev_statistics_read as module
from src.domains.llm_config.jev_gates import JEV_GATES, JUDGEMENT_BUCKETS, OBSERVER_USAGES
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from src.domains.llm_config.jev_settings import JevRouting

pytestmark = pytest.mark.unit


def _empty_session() -> MagicMock:
    session = MagicMock(spec=AsyncSession)
    result = MagicMock()
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    return session


async def test_a_usage_without_rows_reads_zeros_not_an_absence() -> None:
    session = _empty_session()
    routing = JevRouting(flags={}, thresholds={})
    with (
        patch.object(module, "read_routing", AsyncMock(return_value=routing)),
        patch.object(module, "now_utc", return_value=datetime(2026, 11, 8, 23, 59, tzinfo=UTC)),
    ):
        response = await module.read_jev_statistics(session, days=30)
    # Thirty whole UTC days, today included.
    assert response.since == date(2026, 10, 10)
    assert [item.usage for item in response.usages] == list(JEV_USAGES)
    assert session.execute.await_count == 4  # plus read_routing: five statements
    for item in response.usages:
        assert (item.calls, item.cost_eur, item.latency_p50_ms) == (0, 0.0, None)
        assert item.outcomes == {}
        assert [gate.key for gate in item.gates] == [g.key for g in JEV_GATES.get(item.usage, ())]
        assert all(gate.buckets == [0] * JUDGEMENT_BUCKETS for gate in item.gates)
        assert (item.agreement == []) is (item.usage in OBSERVER_USAGES)
        assert (item.agreement is None) is (item.usage not in OBSERVER_USAGES)


async def test_each_gate_reads_the_threshold_the_next_operation_decides_with() -> None:
    routing = JevRouting(
        flags={}, thresholds={JevUsage.EMAIL_CLASSIFICATION.value: '{"priority":"0.60"}'}
    )
    with patch.object(module, "read_routing", AsyncMock(return_value=routing)):
        response = await module.read_jev_statistics(_empty_session(), days=1)
    email = next(i for i in response.usages if i.usage is JevUsage.EMAIL_CLASSIFICATION)
    assert {gate.key: gate.threshold for gate in email.gates} == {
        "category": 0.8,
        "priority": 0.6,
        "alert": 0.8,
        "reply_expected": 0.3,
    }
