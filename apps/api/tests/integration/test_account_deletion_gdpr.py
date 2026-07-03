"""GDPR account-deletion completeness for health data (audit A5b, N-207.1/2).

``AccountDeletionService.delete_account`` promises to purge ALL personal data,
but health rows are among the most sensitive (physiological data) and the user
row is soft-deleted — FK CASCADEs never fire. Reproduced defects:

- ``health_samples`` and ``health_metric_tokens`` survive deletion;
- ``last_known_location_encrypted`` / ``last_known_location_updated_at``
  survive PII scrubbing;
- an ingestion token still authenticates after the account is deleted
  (the deleted user's iPhone keeps writing samples).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.health_metrics.models import HealthMetricToken, HealthSample
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.users.account_deletion_service import AccountDeletionService

pytestmark = pytest.mark.integration


async def _seed_health_data(db: AsyncSession, user) -> str:
    """Create an ingestion token + two samples for the user; return raw token."""
    service = HealthMetricsService(db)
    created = await service.create_token(user_id=user.id, label="gdpr-test")
    token_record = await service.authenticate_token(created.token)
    assert token_record is not None

    now = datetime.now(UTC).replace(microsecond=0)
    await service.ingest_batch(
        token_record=token_record,
        kind="steps",
        raw_samples=[
            {
                "date_start": (now - timedelta(hours=2)).isoformat(),
                "date_end": (now - timedelta(hours=1)).isoformat(),
                "steps": 1200,
                "o": "iphone",
            },
            {
                "date_start": (now - timedelta(hours=1)).isoformat(),
                "date_end": now.isoformat(),
                "steps": 800,
                "o": "iphone",
            },
        ],
    )
    await db.commit()
    return created.token


async def _prepare_deletable_user(db: AsyncSession, user) -> None:
    """Deactivate the user and give it a last-known location (PII)."""
    user.is_active = False
    user.last_known_location_encrypted = "encrypted-location-blob"
    user.last_known_location_updated_at = datetime.now(UTC)
    await db.commit()

    # delete_account purges the LangGraph store with raw SQL; that table is
    # owned by LangGraph setup (not ORM metadata), so create a minimal stand-in.
    await db.execute(text("CREATE TABLE IF NOT EXISTS store (prefix TEXT)"))
    await db.commit()


async def test_account_deletion_purges_health_data_and_location(
    async_session: AsyncSession, test_user, test_superuser
) -> None:
    """After deletion: zero health/location data remains, token no longer authenticates."""
    raw_token = await _seed_health_data(async_session, test_user)
    await _prepare_deletable_user(async_session, test_user)

    deletion = AccountDeletionService(async_session)
    deleted_user, counts = await deletion.delete_account(
        user_id=test_user.id,
        admin_user_id=test_superuser.id,
        reason="gdpr-erasure-test",
    )

    samples = (
        (
            await async_session.execute(
                select(HealthSample).where(HealthSample.user_id == test_user.id)
            )
        )
        .scalars()
        .all()
    )
    assert samples == [], "health_samples survived account deletion (GDPR)"

    tokens = (
        (
            await async_session.execute(
                select(HealthMetricToken).where(HealthMetricToken.user_id == test_user.id)
            )
        )
        .scalars()
        .all()
    )
    assert tokens == [], "health_metric_tokens survived account deletion (GDPR)"

    assert (
        deleted_user.last_known_location_encrypted is None
    ), "last_known_location_encrypted survived PII scrubbing"
    assert (
        deleted_user.last_known_location_updated_at is None
    ), "last_known_location_updated_at survived PII scrubbing"

    # The deleted user's device must no longer be able to ingest anything.
    service = HealthMetricsService(async_session)
    assert (
        await service.authenticate_token(raw_token) is None
    ), "ingestion token still authenticates after account deletion"


async def test_ingestion_token_rejected_for_deleted_user_defense_in_depth(
    async_session: AsyncSession, test_user
) -> None:
    """Even an un-revoked token must not authenticate once its owner is deleted.

    Defense in depth for the ingest path: if any future deletion/erasure flow
    forgets to revoke health tokens, authentication itself must check the
    owner's account state (is_active / deleted_at), not just ``revoked_at``.
    """
    service = HealthMetricsService(async_session)
    created = await service.create_token(user_id=test_user.id, label="defense-test")
    await async_session.commit()

    # Simulate a deleted owner WITHOUT touching the token row.
    test_user.is_active = False
    test_user.deleted_at = datetime.now(UTC)
    await async_session.commit()

    assert (
        await service.authenticate_token(created.token) is None
    ), "token of a deleted user still authenticates (revoked_at is the only check)"


async def test_ingestion_token_rejected_for_deactivated_user(
    async_session: AsyncSession, test_user
) -> None:
    """A deactivated (not yet deleted) account must not ingest either."""
    service = HealthMetricsService(async_session)
    created = await service.create_token(user_id=test_user.id, label="deactivated-test")
    test_user.is_active = False
    await async_session.commit()

    assert await service.authenticate_token(created.token) is None


async def test_ingestion_token_still_works_for_active_user(
    async_session: AsyncSession, test_user
) -> None:
    """Sanity: the active-user path keeps authenticating (no regression)."""
    service = HealthMetricsService(async_session)
    created = await service.create_token(user_id=test_user.id, label="active-test")
    await async_session.commit()

    token = await service.authenticate_token(created.token)
    assert token is not None
    assert token.user_id == test_user.id


async def test_delete_account_counts_report_health_tables(
    async_session: AsyncSession, test_user, test_superuser
) -> None:
    """The per-table deletion report must include the health tables."""
    await _seed_health_data(async_session, test_user)
    await _prepare_deletable_user(async_session, test_user)

    deletion = AccountDeletionService(async_session)
    _, counts = await deletion.delete_account(
        user_id=test_user.id,
        admin_user_id=test_superuser.id,
        reason="gdpr-count-test",
    )

    assert counts.get("health_samples", 0) == 2
    assert counts.get("health_metric_tokens", 0) == 1


async def test_delete_account_with_no_health_data_still_works(
    async_session: AsyncSession, test_user, test_superuser
) -> None:
    """Deletion of an account without any health rows must not regress."""
    await _prepare_deletable_user(async_session, test_user)

    deletion = AccountDeletionService(async_session)
    deleted_user, counts = await deletion.delete_account(
        user_id=test_user.id,
        admin_user_id=test_superuser.id,
        reason="gdpr-empty-test",
    )

    assert deleted_user.deleted_at is not None
    assert counts.get("health_samples", 0) == 0


async def test_deleted_user_ingest_write_is_refused_end_to_end(
    async_session: AsyncSession, test_user, test_superuser
) -> None:
    """Acceptance criterion: an ingestion WRITE after deletion is refused.

    Exercises the service-level write path exactly as the router does
    (authenticate then ingest): after deletion the authenticate step must
    yield None, which the router maps to HTTP 401.
    """
    raw_token = await _seed_health_data(async_session, test_user)
    await _prepare_deletable_user(async_session, test_user)

    deletion = AccountDeletionService(async_session)
    await deletion.delete_account(
        user_id=test_user.id,
        admin_user_id=test_superuser.id,
        reason="gdpr-write-test",
    )

    service = HealthMetricsService(async_session)
    token_record = await service.authenticate_token(raw_token)
    assert token_record is None, "post-deletion ingestion write would be accepted"

    # And no sample row may exist afterwards either way.
    remaining = (
        (
            await async_session.execute(
                select(HealthSample).where(HealthSample.user_id == test_user.id)
            )
        )
        .scalars()
        .all()
    )
    assert remaining == []
