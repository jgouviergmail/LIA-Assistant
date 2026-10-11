"""Relations settings use an exact source owner transaction and original approval snapshot."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.relation_settings import (
    execute_relation_settings,
    prepare_relation_settings,
)
from src.domains.agents.application.relation_settings_schemas import RelationSettingsPatch
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "change",
        "noop",
        "stale",
        "foreign",
        "expired",
        "native_off",
        "late_off",
        "lost_ack",
        "committed_lost_ack",
        "scope",
    ],
)
async def test_relation_preferences_preserve_exact_scope_and_truthful_commit(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    test_user.relation_debrief_enabled = True
    test_user.relation_overview_scope = None
    await async_session.commit()
    monkeypatch.setattr(
        "src.domains.relations.debrief.service.RelationDebriefService.build",
        AsyncMock(side_effect=AssertionError("Preference write cannot generate a debrief")),
    )
    patch = RelationSettingsPatch.model_validate(
        {"relation_overview_scope": {"sections": [], "max_items": 3}}
        if scenario == "scope"
        else {"relation_debrief_enabled": scenario == "noop"}
    )
    draft = await prepare_relation_settings(async_session, owner, patch)
    receipt = PreferenceWriteReceipt()
    actor = owner
    if scenario == "stale":
        await async_session.execute(
            update(User).where(User.id == owner).values(relation_debrief_enabled=False)
        )
        await async_session.commit()
    elif scenario == "foreign":
        actor = uuid4()
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
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
            raise OperationalError("commit", {}, RuntimeError("lost ACK"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    errors = {
        "stale": ResourceConflictError,
        "foreign": CommandRejected,
        "expired": CommandRejected,
        "native_off": AuthorizationError,
        "late_off": AuthorizationError,
        "lost_ack": CommandRejected,
        "committed_lost_ack": CommandRejected,
    }
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await execute_relation_settings(async_session, actor, draft, receipt)
        assert not receipt.committed
        await async_session.rollback()
    else:
        await execute_relation_settings(async_session, actor, draft, receipt)
        assert receipt.committed and receipt.no_op is (scenario == "noop")
    saved = await async_session.scalar(
        select(User).where(User.id == owner).execution_options(populate_existing=True)
    )
    assert saved.relation_debrief_enabled is (
        scenario not in {"change", "stale", "committed_lost_ack"}
    )
    assert saved.relation_overview_scope == (
        patch.relation_overview_scope.model_dump(mode="json") if scenario == "scope" else None
    )
