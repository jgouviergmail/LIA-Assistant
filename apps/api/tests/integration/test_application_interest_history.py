"""Notification audit reads are owned, bounded, complete-counted and stably paged."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.tools import application_interest_tools
from src.domains.interests.management_history import read_interest_history_page
from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "page",
        "ties",
        "empty",
        "foreign_cursor",
        "foreign_topic",
        "disabled",
        "last_page",
        "unknown_cursor",
        "late_disabled",
        "late_actor_off",
    ],
)
async def test_notification_history_counts_and_topics_are_owned_and_pages_stable(
    async_session: AsyncSession,
    test_user: User,
    test_superuser: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    tool = getattr(application_interest_tools, "get_lia_interest_history_tool", None)
    assert tool is not None, "Interest notification audit history needs its native explicit read"
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = test_user.id
    now = datetime.now(UTC)
    target = UserInterest(
        user_id=test_superuser.id if scenario == "foreign_topic" else owner,
        topic="Foreign secret" if scenario == "foreign_topic" else "Owned topic",
        category="science",
        last_mentioned_at=now,
    )
    async_session.add(target)
    await async_session.flush()
    identities = [] if scenario == "empty" else sorted([uuid4() for _ in range(23)], reverse=True)
    async_session.add_all(
        [
            InterestNotification(
                id=identity,
                user_id=owner,
                interest_id=target.id,
                created_at=now,
                run_id=str(uuid4()),
                content_hash="a" * 64,
                content=None if index == 0 else f"Owned notification {index}",
                source="llm",
            )
            for index, identity in enumerate(identities)
        ]
    )
    foreign_id = uuid4()
    async_session.add(
        InterestNotification(
            id=foreign_id,
            user_id=test_superuser.id,
            interest_id=target.id,
            created_at=now,
            run_id=str(uuid4()),
            content_hash="b" * 64,
            content="Foreign notification",
            source="llm",
        )
    )
    await async_session.commit()
    if scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    query: dict[str, object] = {"limit": 5}
    if scenario == "foreign_cursor":
        query["after_id"] = str(foreign_id)
    elif scenario == "unknown_cursor":
        query["after_id"] = str(uuid4())
    elif scenario == "last_page":
        query["after_id"] = str(min(identities))

    async def changed_during_read(*args, **kwargs):
        page = await read_interest_history_page(*args, **kwargs)
        if scenario == "late_disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif scenario == "late_actor_off":
            await async_session.execute(
                update(User).where(User.id == owner).values(is_active=False)
            )
            await async_session.commit()
        return page

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=owner),
        patch("src.domains.agents.tools.application_interest_tools.get_db_context", session),
        patch(
            "src.domains.agents.application.interest_history.read_interest_history_page",
            changed_during_read,
        ),
    ):
        output = await tool.coroutine(
            query=query,
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert output.success is (
            scenario
            not in {
                "foreign_cursor",
                "unknown_cursor",
                "disabled",
                "late_disabled",
                "late_actor_off",
            }
        )
        if not output.success:
            assert output.error_code == (
                "CAPABILITY_DISABLED"
                if scenario in {"disabled", "late_disabled"}
                else "FORBIDDEN" if scenario == "late_actor_off" else "NOT_FOUND"
            )
            return
        data = output.structured_data
        assert data["total"] == len(identities)
        assert len(data["notifications"]) == (
            0 if scenario == "last_page" else min(5, len(identities))
        )
        if scenario in {"last_page", "empty"}:
            assert not data["truncated"] and data["next_cursor"] is None
        else:
            assert data["notifications"][0]["content"] is None
        assert "Foreign secret" not in str(data) and "Foreign notification" not in str(data)
        assert (
            "content_hash" not in str(data)
            and "content_embedding" not in str(data)
            and "run_id" not in str(data)
        )
        if scenario == "foreign_topic":
            assert all(item["topic"] is None for item in data["notifications"])
        if scenario == "ties":
            expected = sorted(identities, reverse=True)
            assert [row["id"] for row in data["notifications"]] == list(map(str, expected[:5]))
            second = await tool.coroutine(
                query={"limit": 5, "after_id": data["next_cursor"]},
                runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
            )
            assert second.success and second.structured_data["total"] == 23
            assert [row["id"] for row in second.structured_data["notifications"]] == list(
                map(str, expected[5:10])
            )
