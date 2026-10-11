"""Confirmed token revocation preserves measurements and rejects pre-authenticated late ingestion."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from src.core.config import settings
from src.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ResourceConflictError,
    ResourceNotFoundError,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.health_token_revocation import (
    execute_health_token_revocation,
    prepare_health_token_revocation,
)
from src.domains.agents.application.health_token_schemas import HealthTokenRevokeRequest
from src.domains.health_metrics.models import HealthMetricToken, HealthSample
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("inactive", [False, True])
async def test_source_revocation_rechecks_account_under_owner_lock(
    async_session, test_user, inactive
):
    owner, identity = test_user.id, uuid4()
    async_session.add(
        HealthMetricToken(
            id=identity,
            user_id=owner,
            token_hash=sha256(str(identity).encode()).hexdigest(),
            token_prefix="hm_public",
            label="Watch",
        )
    )
    await async_session.commit()
    await async_session.execute(
        update(User)
        .where(User.id == owner)
        .values(**({"is_active": False} if inactive else {"deleted_at": datetime.now(UTC)}))
    )
    await async_session.commit()
    with pytest.raises(AuthorizationError):
        await HealthMetricsService(async_session).revoke_token(owner, identity)
    assert (
        await async_session.scalar(
            select(HealthMetricToken.revoked_at).where(HealthMetricToken.id == identity)
        )
        is None
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "revoked",
        "already_revoked",
        "foreign",
        "changed",
        "used",
        "late_ingestion",
        "expired",
        "withdrawn",
        "late_withdrawal",
        "missing_effect",
        "retargeted_effect",
    ],
)
async def test_token_revocation_is_owned_conditional_and_blocks_old_auth(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    foreign = User(id=uuid4(), email=f"health-token-foreign-{uuid4()}@example.test", is_active=True)
    async_session.add(foreign)
    await async_session.flush()
    raw = f"hm_private-{uuid4()}"
    token = HealthMetricToken(
        user_id=foreign.id if scenario == "foreign" else owner,
        token_hash=sha256(raw.encode()).hexdigest(),
        token_prefix="hm_public",
        label="Watch",
        revoked_at=datetime.now(UTC) if scenario == "already_revoked" else None,
    )
    async_session.add(token)
    now = datetime.now(UTC)
    sample = HealthSample(
        user_id=owner,
        kind="steps",
        date_start=now,
        date_end=now + timedelta(minutes=1),
        value=1,
        source="watch",
    )
    async_session.add(sample)
    await async_session.commit()
    token_id, sample_id = token.id, sample.id
    if scenario == "foreign":
        with pytest.raises(ResourceNotFoundError):
            await prepare_health_token_revocation(
                async_session, owner, HealthTokenRevokeRequest(token_id=token_id)
            )
        return
    draft = await prepare_health_token_revocation(
        async_session, owner, HealthTokenRevokeRequest(token_id=token_id)
    )
    assert raw not in str(draft.model_dump()) and token.token_hash not in str(draft.model_dump())
    if scenario == "changed":
        await async_session.execute(
            update(HealthMetricToken)
            .where(HealthMetricToken.id == token_id)
            .values(label="Different")
        )
        await async_session.commit()
    if scenario == "used":
        await async_session.execute(
            update(HealthMetricToken)
            .where(HealthMetricToken.id == token_id)
            .values(last_used_at=datetime.now(UTC))
        )
        await async_session.commit()
    receipt = PreferenceWriteReceipt()
    errors = {
        "expired": CommandRejected,
        "withdrawn": AuthorizationError,
        "late_withdrawal": AuthorizationError,
        "missing_effect": ValueError,
        "retargeted_effect": ValueError,
    }
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "withdrawn":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario in {"late_withdrawal", "missing_effect", "retargeted_effect"}:
        original = HealthMetricsService.revoke_token

        async def effect(service, actor, selected_id):
            if scenario == "missing_effect":
                return True
            changed = await original(service, actor, selected_id)
            if scenario == "late_withdrawal":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            else:
                await service.db.execute(
                    update(HealthMetricToken)
                    .where(HealthMetricToken.id == selected_id)
                    .values(label="Substituted")
                )
            return changed

        monkeypatch.setattr(HealthMetricsService, "revoke_token", effect)
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await execute_health_token_revocation(async_session, owner, draft, receipt)
        assert not receipt.committed
        await async_session.rollback()
        assert (
            await async_session.scalar(
                select(HealthMetricToken.revoked_at).where(HealthMetricToken.id == token_id)
            )
            is None
        )
        return
    if scenario == "changed":
        with pytest.raises(ResourceConflictError):
            await execute_health_token_revocation(async_session, owner, draft, receipt)
        assert not receipt.committed
        return
    await execute_health_token_revocation(async_session, owner, draft, receipt)
    assert receipt.committed and receipt.no_op == (scenario == "already_revoked")
    assert (
        await async_session.scalar(select(HealthSample.id).where(HealthSample.id == sample_id))
        is not None
    )
    saved = await async_session.scalar(
        select(HealthMetricToken.revoked_at).where(HealthMetricToken.id == token_id)
    )
    assert saved is not None
    if scenario == "late_ingestion":
        with pytest.raises(AuthenticationError):
            await HealthMetricsService(async_session).ingest_batch(
                token_record=token,
                kind="steps",
                raw_samples=[
                    {
                        "date_start": (now + timedelta(hours=1)).isoformat(),
                        "date_end": (now + timedelta(hours=1, minutes=1)).isoformat(),
                        "steps": 12,
                    }
                ],
            )


@pytest.mark.parametrize("committed", [False, True])
async def test_token_revocation_lost_ack_does_not_claim_success(
    async_session, test_user, monkeypatch, committed
):
    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    token_id = uuid4()
    async_session.add(
        HealthMetricToken(
            id=token_id,
            user_id=owner,
            token_hash=sha256(str(uuid4()).encode()).hexdigest(),
            token_prefix="hm_public",
            label="Watch",
        )
    )
    await async_session.commit()
    draft = await prepare_health_token_revocation(
        async_session, owner, HealthTokenRevokeRequest(token_id=token_id)
    )
    original = async_session.commit

    async def unknown():
        if committed:
            await original()
        raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgement"))

    monkeypatch.setattr(async_session, "commit", unknown)
    receipt = PreferenceWriteReceipt()
    with pytest.raises(CommandRejected) as refused:
        await execute_health_token_revocation(async_session, owner, draft, receipt)
    assert refused.value.code == "COMPLETION_UNKNOWN" and not receipt.committed
    await async_session.rollback()
    saved = await async_session.scalar(
        select(HealthMetricToken.revoked_at).where(HealthMetricToken.id == token_id)
    )
    assert (saved is not None) == committed
