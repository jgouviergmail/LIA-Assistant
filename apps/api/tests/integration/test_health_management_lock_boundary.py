"""Distinct PostgreSQL connections prove ingestion cannot update samples during erasure."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.health_metrics.models import HealthSample
from src.domains.health_metrics.removal_commands import remove_health_samples
from src.domains.health_metrics.removal_snapshot import health_removal_snapshot
from src.domains.health_metrics.repository import HealthSampleRepository
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)

pytestmark = pytest.mark.integration


async def test_source_ingestion_is_serialized_at_owner_before_sample_rows(
    async_engine, committed_actor
):
    owner = committed_actor
    start = datetime.now(UTC)
    async with AsyncSession(async_engine) as seed:
        seed.add(
            HealthSample(
                user_id=owner,
                kind="steps",
                date_start=start,
                date_end=start + timedelta(minutes=1),
                value=1,
                source="watch",
            )
        )
        await seed.commit()
    async with AsyncSession(async_engine, expire_on_commit=False) as manager:
        await assert_independent_lock_control(manager, async_engine, owner)
        expected = await health_removal_snapshot(manager, owner, None)
        probes = []

        async def blocked_writer():
            async with AsyncSession(async_engine) as writer:
                assert await writer.scalar(select(func.pg_backend_pid())) != await manager.scalar(
                    select(func.pg_backend_pid())
                )
                await writer.execute(text("SET LOCAL lock_timeout = '150ms'"))
                with pytest.raises(DBAPIError) as refused:
                    await HealthSampleRepository(writer).upsert_samples(
                        owner,
                        "steps",
                        [
                            {
                                "date_start": start,
                                "date_end": start + timedelta(minutes=1),
                                "value": 2,
                                "source": "watch",
                            }
                        ],
                    )
                assert getattr(refused.value.orig, "sqlstate", None) == "55P03"
                await writer.rollback()
                probes.append(True)

        receipt = PreferenceWriteReceipt()
        await remove_health_samples(
            manager, owner, None, expected=expected, receipt=receipt, check=blocked_writer
        )
        assert receipt.committed and len(probes) == 2
    # Tokens may ingest anew after an acknowledged erasure; the fence is transactional.
    async with AsyncSession(async_engine) as writer:
        result = await HealthSampleRepository(writer).upsert_samples(
            owner,
            "steps",
            [
                {
                    "date_start": start,
                    "date_end": start + timedelta(minutes=1),
                    "value": 2,
                    "source": "watch",
                }
            ],
        )
        await writer.commit()
        assert result[0] == 1
