"""Exact favorite commands refuse revoked authority, expiry and lost commit acknowledgements."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.relation_favorite import (
    execute_relation_favorite,
    prepare_relation_favorite,
)
from src.domains.agents.application.relation_favorite_schemas import RelationFavoriteRequest
from src.domains.relations.models import RelationFavorite
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    ["valid", "foreign", "expired", "native_off", "late_off", "lost_ack", "committed_lost_ack"],
)
async def test_favorite_authority_and_commit_boundaries(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    await async_session.commit()
    draft = await prepare_relation_favorite(
        async_session, owner, RelationFavoriteRequest(name="Alice", starred=True)
    )
    receipt = PreferenceWriteReceipt()
    actor = owner
    if scenario == "foreign":
        actor = uuid4()
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "late_off":
        flush = async_session.flush

        async def withdraw(*args, **kwargs):
            await flush(*args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)

        monkeypatch.setattr(async_session, "flush", withdraw)
    elif scenario.endswith("lost_ack"):
        commit = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await commit()
            raise OperationalError("commit", {}, RuntimeError("lost ACK"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    errors = {
        "foreign": CommandRejected,
        "expired": CommandRejected,
        "native_off": AuthorizationError,
        "late_off": AuthorizationError,
        "lost_ack": CommandRejected,
        "committed_lost_ack": CommandRejected,
    }
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await execute_relation_favorite(async_session, actor, draft, receipt)
        assert not receipt.committed
        await async_session.rollback()
    else:
        await execute_relation_favorite(async_session, actor, draft, receipt)
        assert receipt.committed
    saved = await async_session.scalar(
        select(RelationFavorite.id).where(RelationFavorite.user_id == owner)
    )
    assert (saved is not None) == (scenario in {"valid", "committed_lost_ack"})
