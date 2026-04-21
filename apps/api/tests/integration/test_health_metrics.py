"""Integration tests for the Health Metrics domain.

Covers:
- Token generation + revocation via session-authenticated endpoints
- Batch ingestion end-to-end: per-kind endpoints, auth success/failure,
  upsert idempotency, mixed validation
- Aggregation endpoint over freshly-ingested polymorphic rows
- Deletion: scope=kind, scope=all
- Ownership isolation

Requires ``HEALTH_METRICS_ENABLED=true`` in the test environment (guaranteed
by the base ``.env.test``). Uses the shared ``async_client`` + ``test_user``
fixtures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.models import User
from src.domains.health_metrics.models import HealthMetricToken, HealthSample
from src.domains.health_metrics.service import _hash_token

# =============================================================================
# Helpers
# =============================================================================


def _steps_payload(count: int, offset_hours: int = 0) -> dict[str, object]:
    """Build a single ``steps`` sample dict with tz-aware dates."""
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(hours=offset_hours + 1)
    end = now - timedelta(hours=offset_hours)
    return {
        "date_start": start.isoformat(),
        "date_end": end.isoformat(),
        "steps": count,
        "o": "iphone",
    }


def _hr_payload(bpm: int, offset_hours: int = 0) -> dict[str, object]:
    """Build a single ``heart_rate`` sample dict with tz-aware dates."""
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(hours=offset_hours + 1)
    end = now - timedelta(hours=offset_hours)
    return {
        "date_start": start.isoformat(),
        "date_end": end.isoformat(),
        "heart_rate": bpm,
        "o": "iphone",
    }


# =============================================================================
# Ingestion — auth failures
# =============================================================================


@pytest.mark.integration
class TestHealthMetricsIngestionAuth:
    """Authentication failures on the public ingest endpoints."""

    @pytest.mark.asyncio
    async def test_ingest_steps_rejects_missing_token(self, async_client: AsyncClient) -> None:
        """No Authorization header → 401 missing_or_malformed_header."""
        response = await async_client.post(
            "/api/v1/ingest/health/steps",
            json=[_steps_payload(1000)],
        )
        assert response.status_code == 401
        assert "Missing" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_ingest_heart_rate_rejects_unknown_token(self, async_client: AsyncClient) -> None:
        """An unknown hm_ token → 401 unknown_or_revoked."""
        response = await async_client.post(
            "/api/v1/ingest/health/heart_rate",
            headers={"Authorization": "Bearer hm_nonexistent_abcdef123456"},
            json=[_hr_payload(72)],
        )
        assert response.status_code == 401
        assert "Invalid" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_ingest_rejects_revoked_token(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User,
    ) -> None:
        """A revoked token must be rejected with 401."""
        raw = "hm_integration_revoked_123456789"
        token = HealthMetricToken(
            user_id=test_user.id,
            token_hash=_hash_token(raw),
            token_prefix=raw[:11],
            label="integration-revoked",
            revoked_at=datetime.now(UTC),
        )
        async_session.add(token)
        await async_session.commit()

        response = await async_client.post(
            "/api/v1/ingest/health/steps",
            headers={"Authorization": f"Bearer {raw}"},
            json=[_steps_payload(1000)],
        )
        assert response.status_code == 401


# =============================================================================
# Ingestion — happy path + upsert + mixed validation
# =============================================================================


@pytest.mark.integration
class TestHealthMetricsBatchIngestion:
    """Batch ingestion semantics (happy path, upsert, mixed validation)."""

    @pytest.mark.asyncio
    async def test_ingest_steps_batch_accepted(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User,
    ) -> None:
        """A steps batch is fully inserted; counts match the batch size."""
        raw = "hm_integration_steps_ok_012345678"
        token = HealthMetricToken(
            user_id=test_user.id,
            token_hash=_hash_token(raw),
            token_prefix=raw[:11],
            label="integration-steps-ok",
        )
        async_session.add(token)
        await async_session.commit()

        samples = [_steps_payload(1000, i) for i in range(3)]
        response = await async_client.post(
            "/api/v1/ingest/health/steps",
            headers={"Authorization": f"Bearer {raw}"},
            json=samples,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["received"] == 3
        assert body["inserted"] == 3
        assert body["updated"] == 0
        assert body["rejected"] == []

    @pytest.mark.asyncio
    async def test_ingest_idempotent_upsert(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Re-sending the same batch yields 0 insert + N update (last-wins)."""
        raw = "hm_integration_upsert_0123456789"
        token = HealthMetricToken(
            user_id=test_user.id,
            token_hash=_hash_token(raw),
            token_prefix=raw[:11],
            label="integration-upsert",
        )
        async_session.add(token)
        await async_session.commit()

        samples = [_hr_payload(70, i) for i in range(2)]
        first = await async_client.post(
            "/api/v1/ingest/health/heart_rate",
            headers={"Authorization": f"Bearer {raw}"},
            json=samples,
        )
        assert first.status_code == 200
        assert first.json()["inserted"] == 2

        # Same date range, different value → must update, not duplicate.
        updated_samples = [{**s, "heart_rate": 85} for s in samples]
        second = await async_client.post(
            "/api/v1/ingest/health/heart_rate",
            headers={"Authorization": f"Bearer {raw}"},
            json=updated_samples,
        )
        assert second.status_code == 200
        body = second.json()
        assert body["inserted"] == 0
        assert body["updated"] == 2

        # Verify the last value wins.
        rows = (
            (
                await async_session.execute(
                    select(HealthSample).where(
                        HealthSample.user_id == test_user.id,
                        HealthSample.kind == "heart_rate",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2
        assert all(row.value == 85 for row in rows)

    @pytest.mark.asyncio
    async def test_ingest_mixed_validation(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Valid samples persist even when siblings are rejected."""
        raw = "hm_integration_mixed_0123456789"
        token = HealthMetricToken(
            user_id=test_user.id,
            token_hash=_hash_token(raw),
            token_prefix=raw[:11],
            label="integration-mixed",
        )
        async_session.add(token)
        await async_session.commit()

        samples = [
            _hr_payload(72, 0),  # valid
            _hr_payload(0, 1),  # out_of_range (below min)
            _hr_payload(80, 2),  # valid
        ]
        response = await async_client.post(
            "/api/v1/ingest/health/heart_rate",
            headers={"Authorization": f"Bearer {raw}"},
            json=samples,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["received"] == 3
        assert body["inserted"] == 2
        assert body["updated"] == 0
        assert len(body["rejected"]) == 1
        assert body["rejected"][0]["index"] == 1
        assert "out_of_range" in body["rejected"][0]["reason"]

    @pytest.mark.asyncio
    async def test_ingest_heart_rate_intra_batch_duplicates_averaged(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User,
    ) -> None:
        """HR duplicates on the same time range are averaged before upsert.

        Regression test for the ``CardinalityViolationError`` raised by
        PostgreSQL when ``ON CONFLICT ... DO UPDATE`` is asked to touch the
        same target row twice in a single statement. iOS Shortcuts can
        legitimately emit overlapping samples (Apple Watch + iPhone
        producing identical intervals). For heart_rate we fuse them via
        arithmetic mean (rounded to nearest int).
        """
        raw = "hm_integration_dupes_hr_01234567"
        token = HealthMetricToken(
            user_id=test_user.id,
            token_hash=_hash_token(raw),
            token_prefix=raw[:11],
            label="integration-dupes-hr",
        )
        async_session.add(token)
        await async_session.commit()

        base = _hr_payload(70, 0)
        # Three samples sharing the same (date_start, date_end); avg = 78.
        samples = [
            base,
            {**base, "heart_rate": 80},
            {**base, "heart_rate": 85},
            _hr_payload(72, 1),  # distinct sample
        ]
        response = await async_client.post(
            "/api/v1/ingest/health/heart_rate",
            headers={"Authorization": f"Bearer {raw}"},
            json=samples,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["received"] == 4
        # After dedupe: 2 distinct rows, both new.
        assert body["inserted"] == 2
        # Two duplicates were collapsed → reported as updates.
        assert body["updated"] == 2
        assert body["rejected"] == []

        rows = (
            (
                await async_session.execute(
                    select(HealthSample).where(
                        HealthSample.user_id == test_user.id,
                        HealthSample.kind == "heart_rate",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2
        # AVG(70, 80, 85) = round(78.33) = 78 for the duplicated slot,
        # 72 for the distinct slot.
        values = sorted(row.value for row in rows)
        assert values == [72, 78]

    @pytest.mark.asyncio
    async def test_ingest_steps_intra_batch_duplicates_max(
        self,
        async_client: AsyncClient,
        async_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Steps duplicates on the same time range collapse to MAX.

        Watch and iPhone count complementary subsets of movement; MAX
        approximates ground truth better than SUM (double-count) or AVG
        (under-count).
        """
        raw = "hm_integration_dupes_steps_0123"
        token = HealthMetricToken(
            user_id=test_user.id,
            token_hash=_hash_token(raw),
            token_prefix=raw[:11],
            label="integration-dupes-steps",
        )
        async_session.add(token)
        await async_session.commit()

        base = _steps_payload(500, 0)
        samples = [
            base,
            {**base, "steps": 1200},
            {**base, "steps": 800},
            _steps_payload(300, 1),  # distinct sample
        ]
        response = await async_client.post(
            "/api/v1/ingest/health/steps",
            headers={"Authorization": f"Bearer {raw}"},
            json=samples,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["received"] == 4
        assert body["inserted"] == 2
        assert body["updated"] == 2  # 2 duplicates collapsed
        assert body["rejected"] == []

        rows = (
            (
                await async_session.execute(
                    select(HealthSample).where(
                        HealthSample.user_id == test_user.id,
                        HealthSample.kind == "steps",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2
        # MAX(500, 1200, 800) = 1200 for the duplicated slot, 300 for distinct.
        values = sorted(row.value for row in rows)
        assert values == [300, 1200]


# =============================================================================
# Aggregation
# =============================================================================


@pytest.mark.integration
class TestHealthMetricsAggregate:
    """Aggregation endpoint on freshly-persisted polymorphic rows."""

    @pytest.mark.asyncio
    async def test_aggregate_returns_points_with_gaps(
        self,
        authenticated_client: tuple[AsyncClient, User],
        async_session: AsyncSession,
    ) -> None:
        """Rows scattered across buckets yield has_data True/False accordingly."""
        client, user = authenticated_client

        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        async_session.add_all(
            [
                HealthSample(
                    user_id=user.id,
                    kind="heart_rate",
                    date_start=now - timedelta(hours=2),
                    date_end=now - timedelta(hours=2) + timedelta(minutes=5),
                    value=70,
                    source="test",
                ),
                HealthSample(
                    user_id=user.id,
                    kind="heart_rate",
                    date_start=now,
                    date_end=now + timedelta(minutes=5),
                    value=80,
                    source="test",
                ),
            ]
        )
        await async_session.commit()

        response = await client.get(
            "/api/v1/health-metrics/aggregate",
            params={
                "period": "hour",
                "from_ts": (now - timedelta(hours=3)).isoformat(),
                "to_ts": (now + timedelta(hours=1)).isoformat(),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["period"] == "hour"
        # 4 buckets expected: now-3h, now-2h (hit), now-1h (gap), now (hit).
        assert len(body["points"]) == 4
        flags = [p["has_data"] for p in body["points"]]
        assert flags.count(True) >= 2
        assert body["averages"]["heart_rate_avg"] == 75.0


# =============================================================================
# Deletion
# =============================================================================


@pytest.mark.integration
class TestHealthMetricsDeletion:
    """Selective (kind) and full deletion from the authenticated endpoints."""

    @pytest.mark.asyncio
    async def test_delete_by_kind_removes_only_that_kind(
        self,
        authenticated_client: tuple[AsyncClient, User],
        async_session: AsyncSession,
    ) -> None:
        """DELETE ?kind=heart_rate removes HR rows, preserves steps rows."""
        client, user = authenticated_client
        now = datetime.now(UTC).replace(microsecond=0)
        async_session.add_all(
            [
                HealthSample(
                    user_id=user.id,
                    kind="heart_rate",
                    date_start=now - timedelta(hours=1),
                    date_end=now,
                    value=72,
                    source="test",
                ),
                HealthSample(
                    user_id=user.id,
                    kind="steps",
                    date_start=now - timedelta(hours=1),
                    date_end=now,
                    value=4000,
                    source="test",
                ),
            ]
        )
        await async_session.commit()

        response = await client.delete(
            "/api/v1/health-metrics",
            params={"kind": "heart_rate"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["scope"] == "kind"
        assert body["kind"] == "heart_rate"
        assert body["affected_rows"] >= 1

        remaining = (
            (
                await async_session.execute(
                    select(HealthSample).where(HealthSample.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(remaining) == 1
        assert remaining[0].kind == "steps"

    @pytest.mark.asyncio
    async def test_delete_by_kind_rejects_unknown_kind(
        self,
        authenticated_client: tuple[AsyncClient, User],
    ) -> None:
        """DELETE with an unsupported kind yields 400."""
        client, _user = authenticated_client
        response = await client.delete(
            "/api/v1/health-metrics",
            params={"kind": "blood_pressure"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_all_removes_every_sample(
        self,
        authenticated_client: tuple[AsyncClient, User],
        async_session: AsyncSession,
    ) -> None:
        """DELETE /all removes every sample row for the user."""
        client, user = authenticated_client
        now = datetime.now(UTC).replace(microsecond=0)
        async_session.add_all(
            [
                HealthSample(
                    user_id=user.id,
                    kind="heart_rate" if i % 2 == 0 else "steps",
                    date_start=now - timedelta(hours=i + 1),
                    date_end=now - timedelta(hours=i),
                    value=70 + i if i % 2 == 0 else 1000 * (i + 1),
                    source="test",
                )
                for i in range(3)
            ]
        )
        await async_session.commit()

        response = await client.delete("/api/v1/health-metrics/all")
        assert response.status_code == 200
        body = response.json()
        assert body["scope"] == "all"
        assert body["affected_rows"] >= 3


# =============================================================================
# Token lifecycle
# =============================================================================


@pytest.mark.integration
class TestHealthMetricsTokens:
    """Token lifecycle via the authenticated endpoints."""

    @pytest.mark.asyncio
    async def test_create_list_revoke_token_round_trip(
        self,
        authenticated_client: tuple[AsyncClient, User],
    ) -> None:
        """POST → raw value returned once, GET lists it, DELETE revokes."""
        client, _user = authenticated_client

        create_response = await client.post(
            "/api/v1/health-metrics/tokens",
            json={"label": "round-trip"},
        )
        assert create_response.status_code == 201
        created = create_response.json()
        raw = created["token"]
        assert raw.startswith("hm_")
        token_id = created["id"]

        list_response = await client.get("/api/v1/health-metrics/tokens")
        assert list_response.status_code == 200
        listed = list_response.json()
        assert any(t["id"] == token_id for t in listed["tokens"])
        assert all(
            "token" not in t for t in listed["tokens"]
        ), "raw token must never appear in listings"

        revoke_response = await client.delete(f"/api/v1/health-metrics/tokens/{token_id}")
        assert revoke_response.status_code == 204

        # Subsequent ingestion with the now-revoked token must fail.
        ingest_response = await client.post(
            "/api/v1/ingest/health/steps",
            headers={"Authorization": f"Bearer {raw}"},
            json=[_steps_payload(1000)],
        )
        assert ingest_response.status_code == 401


# =============================================================================
# Ownership isolation
# =============================================================================


@pytest.mark.integration
class TestHealthMetricsOwnership:
    """Ownership isolation: a user cannot act on another user's data."""

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_token_is_idempotent(
        self,
        authenticated_client: tuple[AsyncClient, User],
    ) -> None:
        """Revoking a token that does not belong to the user is a no-op 204."""
        client, _user = authenticated_client
        response = await client.delete(f"/api/v1/health-metrics/tokens/{uuid4()}")
        assert response.status_code == 204
