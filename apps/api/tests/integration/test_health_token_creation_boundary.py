"""Actual source issuance is conditional, atomic and never supplies a lost secret twice."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from src.core.exceptions import AuthorizationError
from src.domains.health_metrics.models import HealthMetricToken
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.health_metrics.token_creation_commands import (
    HealthTokenCreationCompletionUnknown,
    create_managed_health_token,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["valid", "late_withdrawal", "wrong_label", "lost_uncommitted", "lost_committed"]
)
async def test_source_issuance_postcondition_and_lost_ack(
    async_session, test_user, monkeypatch, scenario
):
    owner, identity = test_user.id, uuid4()
    await async_session.commit()
    checks = []

    async def check():
        checks.append(datetime.now(UTC))
        if scenario == "late_withdrawal" and len(checks) == 2:
            raise AuthorizationError()

    if scenario == "wrong_label":
        original_create = HealthMetricsService.create_token

        async def substitution(service, actor, label=None, *, token_id=None):
            return await original_create(
                service, actor, label="Substituted label", token_id=token_id
            )

        monkeypatch.setattr(HealthMetricsService, "create_token", substitution)
    if scenario in {"lost_uncommitted", "lost_committed"}:
        original_commit = async_session.commit

        async def unknown():
            if scenario == "lost_committed":
                await original_commit()
            raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgement"))

        monkeypatch.setattr(async_session, "commit", unknown)
    receipt = PreferenceWriteReceipt()
    errors = {
        "late_withdrawal": AuthorizationError,
        "wrong_label": ValueError,
        "lost_uncommitted": HealthTokenCreationCompletionUnknown,
        "lost_committed": HealthTokenCreationCompletionUnknown,
    }
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await create_managed_health_token(
                async_session, owner, identity, "Watch", receipt, check
            )
        assert not receipt.committed and receipt.values is None
        await async_session.rollback()
        stored = await async_session.scalar(
            select(HealthMetricToken.id).where(HealthMetricToken.id == identity)
        )
        assert (stored is not None) == (scenario == "lost_committed")
        return
    secret = await create_managed_health_token(
        async_session, owner, identity, "Watch", receipt, check
    )
    assert receipt.committed and len(checks) == 2
    assert secret.token not in str(receipt.values)
