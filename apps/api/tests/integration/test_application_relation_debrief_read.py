"""Stored debrief reading exposes source provenance and never buys a build."""

from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import update

from src.core.config import settings
from src.core.constants import RELATION_DEBRIEF_BODY_VERSION
from src.domains.agents.tools import application_relation_tools
from src.domains.relations.debrief.models import DebriefState, RelationDebrief
from src.domains.relations.debrief.service import RelationDebriefService
from src.domains.relations.models import RelationAlias
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "ready",
        "absent",
        "disabled",
        "failed",
        "building",
        "empty",
        "unreadable",
        "oversized",
        "late_native_off",
        "late_actor_off",
        "late_personal_off",
        "late_platform_off",
    ],
)
async def test_stored_debrief_read_is_owned_and_has_no_build(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    async_session.add(
        RelationAlias(
            user_id=owner, alias_key="papa", canonical_key="bob", alias_display_name="Papa"
        )
    )
    foreign = User(id=uuid4(), email=f"debrief-other-{uuid4()}@example.test", is_active=True)
    async_session.add(foreign)
    await async_session.flush()
    for user_id, key, text in ((owner, "bob", "OWNED BODY"), (foreign.id, "bob", "FOREIGN SECRET")):
        async_session.add(
            RelationDebrief(
                user_id=user_id,
                name_key=key,
                display_name="Bob",
                generated_for=date.today(),
                language="fr",
                scope_digest="a" * 64,
                state=(
                    DebriefState(scenario)
                    if scenario in {"failed", "building", "empty"}
                    else DebriefState.READY
                ),
                body={
                    "version": RELATION_DEBRIEF_BODY_VERSION + (scenario == "unreadable"),
                    "headline": text,
                    "where_we_stand": text,
                    "open_points": ["X" * 70_000] if scenario == "oversized" else [],
                },
                sections_used=["open_loops"],
                unavailable=["emails"],
            )
        )
    if scenario == "disabled":
        test_user.relation_debrief_enabled = False
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_relation_tools, "get_db_context", session)
    monkeypatch.setattr("src.domains.relations.debrief.service.get_db_context", session)
    monkeypatch.setattr(
        RelationDebriefService, "build", AsyncMock(side_effect=AssertionError("Read cannot build"))
    )
    if scenario.startswith("late_"):
        source_read = RelationDebriefService.read

        async def withdraw(service, name):
            result = await source_read(service, name)
            if scenario == "late_native_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            elif scenario == "late_platform_off":
                monkeypatch.setattr(settings, "relation_debrief_enabled", False)
            else:
                await async_session.execute(
                    update(User)
                    .where(User.id == owner)
                    .values(
                        {"relation_debrief_enabled": False}
                        if scenario == "late_personal_off"
                        else {"is_active": False}
                    )
                )
                await async_session.commit()
            return result

        monkeypatch.setattr(RelationDebriefService, "read", withdraw)
    with installed_runtime_context(user_id=owner, deps=object()):
        result = await application_relation_tools.get_lia_relation_debrief_tool.coroutine(
            query={"name": "Unknown" if scenario == "absent" else "Papa"},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
    if scenario in {"late_native_off", "late_actor_off", "oversized"}:
        assert not result.success and not result.structured_data
        return
    assert result.success and "FOREIGN SECRET" not in str(result.structured_data)
    expected = (
        "disabled"
        if scenario in {"disabled", "late_personal_off", "late_platform_off"}
        else (
            "absent"
            if scenario in {"absent", "unreadable"}
            else scenario if scenario in {"failed", "building", "empty"} else "ready"
        )
    )
    assert result.structured_data["status"] == expected
    if scenario in {"ready", "failed"}:
        assert result.structured_data["body"]["headline"] == "OWNED BODY"
        assert result.structured_data["unavailable"] == ["emails"]
        assert result.structured_data["usage"] is None
    if expected in {"disabled", "absent"}:
        assert result.structured_data["body"] is None
    RelationDebriefService.build.assert_not_awaited()
