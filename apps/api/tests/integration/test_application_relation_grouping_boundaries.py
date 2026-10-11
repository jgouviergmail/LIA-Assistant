"""Grouping authority and unknown commit outcomes never return a false receipt."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.relation_grouping import (
    execute_relation_grouping,
    prepare_relation_grouping,
)
from src.domains.agents.application.relation_grouping_schemas import RelationGroupingRequest
from src.domains.relations.models import RelationAlias
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["foreign", "expired", "native_off", "late_off", "lost_ack", "committed_lost_ack"]
)
async def test_grouping_authority_and_ack_boundaries(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    await async_session.commit()
    draft = await prepare_relation_grouping(
        async_session, owner, RelationGroupingRequest(action="merge", source="Alice", target="Bob")
    )
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
    else:
        commit = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await commit()
            raise OperationalError("commit", {}, RuntimeError("lost ACK"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    expected = AuthorizationError if scenario in {"native_off", "late_off"} else CommandRejected
    with pytest.raises(expected):
        await execute_relation_grouping(async_session, actor, draft, receipt)
    assert not receipt.committed
    await async_session.rollback()
    alias = await async_session.scalar(
        select(RelationAlias.canonical_key).where(RelationAlias.user_id == owner)
    )
    assert alias == ("bob" if scenario == "committed_lost_ack" else None)
