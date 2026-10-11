"""Native relationship cards reuse the exact local source identities and totals."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import update

from src.core.config import settings
from src.domains.agents.application.relation_data import read_relation_data
from src.domains.agents.application.relation_data_schemas import RelationDataRead
from src.domains.agents.tools import application_relation_tools
from src.domains.open_loops.models import OpenLoop
from src.domains.relations.models import RelationAlias, RelationFavorite
from src.domains.relations.service import RelationsService
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["overview", "detail", "late_native_off", "late_actor_off"])
async def test_relation_cards_reuse_owned_source_and_exact_totals(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    async_session.add_all(
        [
            RelationFavorite(user_id=owner, name_key=f"person {i}", display_name=f"Person {i}")
            for i in range(3)
        ]
    )
    foreign = User(
        id=uuid4(), email=f"foreign-rel-{uuid4()}@example.test", full_name="Foreign", is_active=True
    )
    async_session.add(foreign)
    await async_session.flush()
    async_session.add(
        RelationFavorite(
            user_id=foreign.id, name_key="foreign person", display_name="FOREIGN SECRET"
        )
    )
    async_session.add_all(
        [
            OpenLoop(
                user_id=owner,
                counterparty="Person 0",
                subject=f"Owned promise {i}",
                direction="user_owes",
            )
            for i in range(5)
        ]
    )
    async_session.add_all(
        [
            RelationAlias(
                user_id=owner,
                alias_key=f"alias {i}",
                canonical_key="person 0",
                alias_display_name=f"Alias {i}",
            )
            for i in range(53)
        ]
    )
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr("src.domains.relations.service.get_db_context", session)
    monkeypatch.setattr("src.domains.relations.peer_messages.get_db_context", session)
    monkeypatch.setattr(application_relation_tools, "get_db_context", session)
    monkeypatch.setattr(
        "src.domains.relations.service.fetch_peer_message_activity", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "src.domains.relations.providers.service.RelationContextService.build",
        AsyncMock(side_effect=AssertionError("Local card must not read providers")),
    )
    monkeypatch.setattr(
        "src.domains.relations.debrief.service.RelationDebriefService.build",
        AsyncMock(side_effect=AssertionError("Local card must not build a debrief")),
    )
    expected = await RelationsService(owner).build_overview()
    if scenario.startswith("late_"):
        original = RelationsService.build_overview

        async def withdraw(service):
            observed = await original(service)
            if scenario == "late_native_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            else:
                await async_session.execute(
                    update(User).where(User.id == owner).values(is_active=False)
                )
                await async_session.commit()
            return observed

        monkeypatch.setattr(RelationsService, "build_overview", withdraw)
    with installed_runtime_context(user_id=owner, deps=object()):
        result = await application_relation_tools.get_lia_relations_tool.coroutine(
            query={"limit": 2, "name": "Person 0"} if scenario == "detail" else {"limit": 2},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
    if scenario.startswith("late_"):
        assert not result.success and result.error_code == (
            "CAPABILITY_DISABLED" if scenario == "late_native_off" else "FORBIDDEN"
        )
        assert not result.structured_data
        return
    assert result.success and "FOREIGN SECRET" not in str(result.structured_data)
    actual = result.structured_data
    if scenario == "detail":
        assert actual["detail"]["open_loops_total"] == 5
        assert len(actual["detail"]["open_loops"]) == 2
        assert (
            actual["detail"]["merged_from_total"] == 53
            and len(actual["detail"]["merged_from"]) == 2
        )
        assert actual["detail_truncated"] and actual["overview"] is None
        continuation = await read_relation_data(
            async_session, owner, RelationDataRead(name="Person 0", limit=50, offset=2)
        )
        assert len(continuation.detail.merged_from) == 50
        assert continuation.next_offset == 52 and continuation.detail.merged_from_total == 53
    else:
        assert actual["overview"]["relations_total"] == 3
        assert actual["overview"]["relations"] == [
            row.model_dump(mode="json") for row in expected.relations[:2]
        ]
        assert actual["detail"] is None and actual["overview_truncated"]
        last = await read_relation_data(async_session, owner, RelationDataRead(limit=2, offset=2))
        assert last.overview.relations == expected.relations[2:]
        assert last.overview.relations_total == 3 and last.next_offset is None
