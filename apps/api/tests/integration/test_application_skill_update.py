"""An exact confirmed personal state never toggles accidentally or changes global visibility."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.skill_update import execute_skill_update, prepare_skill_update
from src.domains.agents.application.skill_update_schemas import SkillUpdateInput
from src.domains.skills.models import UserSkillState
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.skills.test_per_account_skill_names import _skill

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "own",
        "system",
        "no_op",
        "stale",
        "hidden",
        "shadowed",
        "revoked",
        "expired",
        "skills_off",
        "lost_ack",
        "cancelled_ack",
    ],
)
async def test_exact_skill_state_is_personal_fresh_and_explicit(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "skills_enabled", True)
    owner = test_user.id
    row = await _skill(
        async_session,
        "native-card",
        None if scenario in {"system", "hidden", "shadowed"} else owner,
    )
    await async_session.commit()
    desired = scenario == "no_op"
    draft = await prepare_skill_update(
        async_session, owner, SkillUpdateInput(skill_id=row.id, enabled=desired)
    )
    state = await async_session.scalar(
        select(UserSkillState).where(
            UserSkillState.user_id == owner, UserSkillState.skill_id == row.id
        )
    )
    assert state.is_active
    if scenario == "stale":
        state.is_active = False
    elif scenario == "hidden":
        row.admin_enabled = False
    elif scenario == "shadowed":
        await _skill(async_session, "native-card", owner)
    elif scenario == "revoked":
        test_user.is_active = False
    await async_session.commit()
    if scenario == "expired":
        draft.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif scenario == "skills_off":
        monkeypatch.setattr(settings, "skills_enabled", False)
    elif scenario in {"lost_ack", "cancelled_ack"}:

        async def unknown_commit():
            raise (
                asyncio.CancelledError()
                if scenario == "cancelled_ack"
                else OSError("lost acknowledgement")
            )

        monkeypatch.setattr(async_session, "commit", unknown_commit)
    receipt = PreferenceWriteReceipt()
    if scenario in {
        "stale",
        "hidden",
        "shadowed",
        "revoked",
        "expired",
        "skills_off",
        "lost_ack",
        "cancelled_ack",
    }:
        with pytest.raises((CommandRejected, ValueError, BaseAPIException)):
            await execute_skill_update(async_session, owner, draft, receipt)
        assert not receipt.committed
    else:
        await execute_skill_update(async_session, owner, draft, receipt)
        await async_session.refresh(state)
        assert state.is_active == desired and row.admin_enabled
        assert receipt.committed and receipt.no_op == desired
