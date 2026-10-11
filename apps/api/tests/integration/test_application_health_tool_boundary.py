"""Actual registered tools return only owned public data through the standard envelope."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.tools import application_health_tools
from src.domains.health_metrics.models import HealthMetricToken, HealthSample
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


async def test_health_tools_read_public_fields_and_honor_consent(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    test_user.health_metrics_agents_enabled = False
    now = datetime.now(UTC)
    sample = HealthSample(
        user_id=owner,
        kind="steps",
        date_start=now - timedelta(minutes=1),
        date_end=now,
        value=37,
        source="watch",
    )
    token = HealthMetricToken(
        user_id=owner,
        token_hash=sha256(b"RAW-SECRET").hexdigest(),
        token_prefix="hm_public",
        label="Watch",
    )
    async_session.add_all([sample, token])
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(application_health_tools, "get_db_context", session)
    with installed_runtime_context(user_id=owner, deps=object()):
        runtime = make_tool_runtime(user_id=owner, store=InMemoryStore())
        metadata = await application_health_tools.get_lia_health_ingestion_tokens_tool.coroutine(
            runtime=runtime
        )
        assert metadata.success and "Watch" in str(metadata.structured_data)
        assert "token_hash" not in str(metadata.structured_data) and "RAW-SECRET" not in str(
            metadata.structured_data
        )
        refused = await application_health_tools.get_lia_health_samples_tool.coroutine(
            runtime=runtime
        )
        assert not refused.success and refused.error_code == "FORBIDDEN"
        test_user.health_metrics_agents_enabled = True
        await async_session.commit()
        observed = await application_health_tools.get_lia_health_samples_tool.coroutine(
            runtime=runtime
        )
        assert observed.success and observed.structured_data["samples"][0]["value"] == 37
        chart = await application_health_tools.get_lia_health_chart_tool.coroutine(runtime=runtime)
        assert chart.success and any(point["has_data"] for point in chart.structured_data["points"])
        too_wide = await application_health_tools.get_lia_health_chart_tool.coroutine(
            query={
                "period": "hour",
                "from_ts": "2026-01-01T00:00:00Z",
                "to_ts": "2026-02-01T00:00:00Z",
            },
            runtime=runtime,
        )
        assert not too_wide.success and too_wide.error_code == "INVALID_INPUT"
        malformed = await application_health_tools.get_lia_health_samples_tool.coroutine(
            query={"user_id": str(owner)}, runtime=runtime
        )
        assert not malformed.success and malformed.error_code == "INVALID_INPUT"
