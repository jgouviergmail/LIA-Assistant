"""Independent consent fields change only after exact fresh source confirmation."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import update
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.peer_preference_schemas import PeerPreferencePatch
from src.domains.agents.application.peer_preferences import (
    execute_peer_preferences,
    prepare_peer_preferences,
)
from src.domains.peers.service import PeersService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "update",
        "no_op",
        "stale",
        "expired",
        "native_off",
        "peers_off",
        "lost_ack",
        "committed_lost_ack",
        "false_source",
        "late_off",
    ],
)
async def test_peer_consent_fields_exact_comparison_and_ack(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    test_user.discovery_enabled = False
    test_user.peer_email_visible = True
    await async_session.commit()
    desired = False if scenario == "no_op" else True
    draft = await prepare_peer_preferences(
        async_session, owner, PeerPreferencePatch(discovery_enabled=desired)
    )
    assert draft.before == {"discovery_enabled": False} and draft.after == {
        "discovery_enabled": desired
    }
    assert not test_user.discovery_enabled and test_user.peer_email_visible
    if scenario == "stale":
        await async_session.execute(
            update(User)
            .where(User.id == owner)
            .values(discovery_enabled=True)
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario in {"native_off", "peers_off"}:
        monkeypatch.setattr(
            settings,
            "application_tools_enabled" if scenario == "native_off" else "peers_enabled",
            False,
        )
    if scenario.endswith("lost_ack"):
        original = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await original()
            raise OperationalError("commit", {}, RuntimeError("Lost ACK"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    if scenario == "false_source":
        monkeypatch.setattr(PeersService, "set_discovery", AsyncMock(return_value=None))
    if scenario == "late_off":
        source = PeersService.set_discovery

        async def withdraw(service, actor_id, enabled):
            await source(service, actor_id, enabled)
            monkeypatch.setattr(settings, "application_tools_enabled", False)

        monkeypatch.setattr(PeersService, "set_discovery", withdraw)
    errors = {
        "stale": ResourceConflictError,
        "expired": CommandRejected,
        "native_off": AuthorizationError,
        "peers_off": AuthorizationError,
        "lost_ack": CommandRejected,
        "committed_lost_ack": CommandRejected,
        "false_source": ValueError,
        "late_off": AuthorizationError,
    }
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await execute_peer_preferences(async_session, owner, draft, receipt)
        assert not receipt.committed
        if scenario.endswith("lost_ack") or scenario == "late_off":
            await async_session.rollback()
    else:
        await execute_peer_preferences(async_session, owner, draft, receipt)
        assert receipt.committed and receipt.no_op == (scenario == "no_op")
    await async_session.refresh(test_user)
    assert test_user.peer_email_visible
    assert bool(test_user.discovery_enabled) == (
        scenario in {"update", "stale", "committed_lost_ack"}
    )
