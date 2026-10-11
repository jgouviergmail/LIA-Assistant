"""Explicit management reads have complete counts, bounded rows and fresh ownership."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import INTEREST_USER_LIST_LIMIT
from src.domains.agents.application.interest_read_schemas import InterestRead
from src.domains.agents.tools.application_interest_tools import get_lia_interests_tool
from src.domains.interests.management_queries import read_interest_management_page
from src.domains.interests.models import UserInterest
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "all",
        "filtered",
        "selected",
        "foreign",
        "unknown",
        "foreign_cursor",
        "ties",
        "fresh",
        "disabled",
        "late_disabled",
        "late_actor_off",
        "fresh_settings",
        "last_page",
        "empty",
    ],
)
async def test_interest_read_counts_are_not_the_ui_page_and_fields_are_source_owned(
    async_session: AsyncSession,
    test_user: User,
    test_superuser: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = test_user.id
    test_user.interests_enabled = False
    now = datetime.now(UTC)
    count = INTEREST_USER_LIST_LIMIT + 5
    identities = [uuid4() for _ in range(count)]
    rows = [
        UserInterest(
            id=identity,
            user_id=owner,
            topic=f"Owned topic {index}",
            category="technology" if index % 2 == 0 else "science",
            status=["active", "blocked", "dormant"][index % 3],
            subject="Shared subject",
            positive_signals=3,
            negative_signals=0,
            last_mentioned_at=now,
            created_at=now,
        )
        for index, identity in enumerate(identities)
    ]
    foreign_id = uuid4()
    async_session.add_all(
        [
            *rows,
            UserInterest(
                id=foreign_id,
                user_id=test_superuser.id,
                topic="Foreign secret",
                category="other",
                last_mentioned_at=now,
            ),
        ]
    )
    await async_session.commit()
    values: dict[str, object] = {"limit": 5}
    if scenario == "filtered":
        values.update(category="technology", status="active")
    elif scenario in {"selected", "foreign", "unknown"}:
        values["interest_id"] = (
            identities[0]
            if scenario == "selected"
            else foreign_id if scenario == "foreign" else uuid4()
        )
    elif scenario == "foreign_cursor":
        values["after_id"] = foreign_id
    elif scenario == "fresh":
        await async_session.execute(
            update(UserInterest)
            .where(UserInterest.id == identities[0])
            .values(topic="Fresh corrected topic")
        )
        await async_session.commit()
        values["interest_id"] = identities[0]
    elif scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "last_page":
        values["after_id"] = min(identities)
    elif scenario == "empty":
        await async_session.execute(delete(UserInterest).where(UserInterest.user_id == owner))
        await async_session.commit()
        count = 0

    async def changed_during_read(*args: object, **kwargs: object):
        page = await read_interest_management_page(*args, **kwargs)
        if scenario == "late_disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif scenario in {"late_actor_off", "fresh_settings"}:
            change = (
                {"is_active": False}
                if scenario == "late_actor_off"
                else {"interests_enabled": True}
            )
            await async_session.execute(update(User).where(User.id == owner).values(**change))
            await async_session.commit()
        return page

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=owner),
        patch("src.domains.agents.tools.application_interest_tools.get_db_context", session),
        patch(
            "src.domains.agents.application.interest_queries.read_interest_management_page",
            changed_during_read,
        ),
    ):
        output = await get_lia_interests_tool.coroutine(
            query=InterestRead.model_validate(values),
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        success = scenario not in {
            "foreign",
            "unknown",
            "foreign_cursor",
            "disabled",
            "late_disabled",
            "late_actor_off",
        }
        assert output.success is success
        if not success:
            assert output.error_code == (
                "CAPABILITY_DISABLED"
                if scenario in {"disabled", "late_disabled"}
                else "FORBIDDEN" if scenario == "late_actor_off" else "NOT_FOUND"
            )
            assert "Foreign secret" not in str(output)
            return
        data = output.structured_data
        assert data["total"] == count
        assert data["active_count"] + data["blocked_count"] + data["dormant_count"] == count
        assert data["settings"]["interests_enabled"] is (scenario == "fresh_settings")
        assert all(row["subject"] == "Shared subject" for row in data["interests"])
        assert "embedding" not in str(data) and "Foreign secret" not in str(data)
        assert len(data["interests"]) <= 5
        if scenario in {"empty", "last_page"}:
            assert data["interests"] == [] and data["returned_count"] == 0
            assert not data["truncated"] and data["next_cursor"] is None
            assert data["total_available"] == count
        elif scenario == "filtered":
            assert all(
                row["category"] == "technology" and row["status"] == "active"
                for row in data["interests"]
            )
            assert data["total_available"] == sum(index % 6 == 0 for index in range(count))
        elif scenario == "fresh":
            assert data["interests"][0]["topic"] == "Fresh corrected topic"
        elif scenario == "ties":
            expected = sorted(identities, reverse=True)
            assert [row["id"] for row in data["interests"]] == list(map(str, expected[:5]))
            second = await get_lia_interests_tool.coroutine(
                query=InterestRead(after_id=data["next_cursor"], limit=5),
                runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
            )
            assert second.success
            assert [row["id"] for row in second.structured_data["interests"]] == list(
                map(str, expected[5:10])
            )
