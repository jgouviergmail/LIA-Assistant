"""Independent SQL transactions prove token authority is rechecked after revocation serialization."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthenticationError
from src.domains.health_metrics.models import HealthMetricToken, HealthSample
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.health_metrics.token_commands import (
    read_owned_health_token,
    revoke_managed_health_token,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)

pytestmark = pytest.mark.integration


async def test_authenticated_ingestion_cannot_cross_confirmed_revocation(
    async_engine, committed_actor
):
    owner, identity = committed_actor, uuid4()
    start = datetime.now(UTC)
    payload = [
        {
            "date_start": start.isoformat(),
            "date_end": (start + timedelta(minutes=1)).isoformat(),
            "steps": 12,
        }
    ]
    async with AsyncSession(async_engine) as seed:
        seed.add(
            HealthMetricToken(
                id=identity,
                user_id=owner,
                token_hash=sha256(str(identity).encode()).hexdigest(),
                token_prefix="hm_public",
                label="Watch",
            )
        )
        await seed.commit()
    async with AsyncSession(async_engine, expire_on_commit=False) as writer:
        preauthenticated = await writer.get(HealthMetricToken, identity)
        writer.expunge(preauthenticated)
        await writer.commit()
        async with AsyncSession(async_engine, expire_on_commit=False) as manager:
            await assert_independent_lock_control(manager, async_engine, owner)
            expected = await read_owned_health_token(manager, owner, identity)
            probes = []

            async def blocked_ingestion():
                assert await writer.scalar(select(func.pg_backend_pid())) != await manager.scalar(
                    select(func.pg_backend_pid())
                )
                await writer.execute(text("SET LOCAL lock_timeout = '150ms'"))
                with pytest.raises(DBAPIError) as refused:
                    await HealthMetricsService(writer).ingest_batch(
                        token_record=preauthenticated, kind="steps", raw_samples=payload
                    )
                assert getattr(refused.value.orig, "sqlstate", None) == "55P03"
                await writer.rollback()
                probes.append(True)

            receipt = PreferenceWriteReceipt()
            await revoke_managed_health_token(manager, owner, expected, receipt, blocked_ingestion)
            assert receipt.committed and len(probes) == 2
        with pytest.raises(AuthenticationError):
            await HealthMetricsService(writer).ingest_batch(
                token_record=preauthenticated, kind="steps", raw_samples=payload
            )
        assert (
            await writer.scalar(
                select(func.count()).select_from(HealthSample).where(HealthSample.user_id == owner)
            )
            == 0
        )
