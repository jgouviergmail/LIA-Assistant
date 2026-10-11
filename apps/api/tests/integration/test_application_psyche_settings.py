"""Source account locking protects exact confirmed sparse psyche settings."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.psyche_settings import (
    execute_psyche_settings,
    prepare_psyche_settings,
)
from src.domains.agents.application.psyche_settings_schemas import PsycheSettingsPatch
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "change",
        "noop",
        "stale",
        "foreign_actor",
        "expired",
        "operator_off",
        "late_off",
        "lost_ack",
        "committed_lost_ack",
    ],
)
async def test_psyche_settings_exact_scope_refuses_stale_or_revoked_authority(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "psyche_enabled", True)
    owner_id = test_user.id
    test_user.psyche_sensitivity = 50
    test_user.psyche_stability = 55
    await async_session.commit()
    desired = 50 if scenario == "noop" else 0
    draft = await prepare_psyche_settings(
        async_session, test_user.id, PsycheSettingsPatch(psyche_sensitivity=desired)
    )
    assert draft.before == {"psyche_sensitivity": 50} and draft.after == {
        "psyche_sensitivity": desired
    }
    receipt = PreferenceWriteReceipt()
    actor = test_user.id
    if scenario == "stale":
        await async_session.execute(
            update(User).where(User.id == actor).values(psyche_sensitivity=60)
        )
        await async_session.commit()
    elif scenario == "foreign_actor":
        actor = uuid4()
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "operator_off":
        monkeypatch.setattr(settings, "psyche_enabled", False)
    elif scenario == "late_off":
        original_flush = async_session.flush

        async def withdraw(*args, **kwargs):
            await original_flush(*args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)

        monkeypatch.setattr(async_session, "flush", withdraw)
    elif scenario.endswith("lost_ack"):
        original_commit = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await original_commit()
            raise OperationalError("commit", {}, RuntimeError("ack unavailable"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    errors = {
        "stale": ResourceConflictError,
        "foreign_actor": CommandRejected,
        "expired": CommandRejected,
        "operator_off": AuthorizationError,
        "late_off": AuthorizationError,
        "lost_ack": CommandRejected,
        "committed_lost_ack": CommandRejected,
    }
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await execute_psyche_settings(async_session, actor, draft, receipt)
        assert not receipt.committed
        await async_session.rollback()
    else:
        await execute_psyche_settings(async_session, actor, draft, receipt)
        assert receipt.committed and receipt.no_op is (scenario == "noop")
    saved = await async_session.scalar(
        select(User).where(User.id == owner_id).execution_options(populate_existing=True)
    )
    assert saved is not None and saved.psyche_stability == 55
    assert saved.psyche_sensitivity == (
        60
        if scenario == "stale"
        else desired if scenario in {"change", "noop", "committed_lost_ack"} else 50
    )
