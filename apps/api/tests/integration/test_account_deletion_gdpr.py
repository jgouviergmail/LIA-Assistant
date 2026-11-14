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
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.conversations import cleanup_port
from src.domains.health_metrics.models import HealthMetricToken, HealthSample
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.users import account_cleanup_port
from src.domains.users.account_deletion_service import AccountDeletionService
from src.domains.users.models import User
from src.infrastructure.account_cleanup_runtime import NativeAccountCleanup
from src.infrastructure.conversation_cleanup_runtime import NativeRuntimeCleanup
from tests.helpers.committed_account_session import async_session as async_session

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def native_cleanup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Install production cleanup ports on the disposable database and file roots."""
    monkeypatch.setattr(account_cleanup_port, "_cleanup", NativeAccountCleanup())
    monkeypatch.setattr(cleanup_port, "_runtime_cleanup", NativeRuntimeCleanup())
    for name in (
        "attachments_storage_path",
        "rag_spaces_storage_path",
        "skills_users_path",
        "plugins_users_path",
        "meetings_storage_path",
    ):
        monkeypatch.setattr(settings, name, str(tmp_path / name))


async def _seed_health_data(db: AsyncSession, user: User) -> str:
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


async def _prepare_deletable_user(db: AsyncSession, user: User) -> None:
    """Deactivate the user and give it a last-known location (PII)."""
    user.is_active = False
    user.last_known_location_encrypted = "encrypted-location-blob"
    user.last_known_location_updated_at = datetime.now(UTC)
    await db.commit()


async def test_account_deletion_purges_health_data_and_location(
    async_session: AsyncSession, test_user: User, test_superuser: User
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


async def test_account_deletion_erases_the_voices_chosen_for_lia(
    async_session: AsyncSession, test_user: User, test_superuser: User
) -> None:
    """A setting that serves nothing once the account is gone: SQL NULL, never a JSON null."""
    test_user.lia_voices = {"fishaudio/s2.1-pro": {"male": "voice-id"}}
    await _prepare_deletable_user(async_session, test_user)

    await AccountDeletionService(async_session).delete_account(
        user_id=test_user.id,
        admin_user_id=test_superuser.id,
        reason="gdpr-erasure-test",
    )

    erased = await async_session.scalar(
        text("SELECT lia_voices IS NULL FROM users WHERE id = :id"), {"id": test_user.id}
    )
    assert erased is True, "lia_voices survived account deletion"


async def test_ingestion_token_rejected_for_deleted_user_defense_in_depth(
    async_session: AsyncSession, test_user: User
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
    async_session: AsyncSession, test_user: User
) -> None:
    """A deactivated (not yet deleted) account must not ingest either."""
    service = HealthMetricsService(async_session)
    created = await service.create_token(user_id=test_user.id, label="deactivated-test")
    test_user.is_active = False
    await async_session.commit()

    assert await service.authenticate_token(created.token) is None


async def test_ingestion_token_still_works_for_active_user(
    async_session: AsyncSession, test_user: User
) -> None:
    """Sanity: the active-user path keeps authenticating (no regression)."""
    service = HealthMetricsService(async_session)
    created = await service.create_token(user_id=test_user.id, label="active-test")
    await async_session.commit()

    token = await service.authenticate_token(created.token)
    assert token is not None
    assert token.user_id == test_user.id


async def test_delete_account_counts_report_health_tables(
    async_session: AsyncSession, test_user: User, test_superuser: User
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
    async_session: AsyncSession, test_user: User, test_superuser: User
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
    async_session: AsyncSession, test_user: User, test_superuser: User
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
