"""The assistant reads complete owned totals and stable pages of the source commitment ledger."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.open_loop_queries import read_open_loops
from src.domains.agents.application.open_loop_schemas import OpenLoopRead
from src.domains.open_loops.management_read import OpenLoopPage
from src.domains.open_loops.models import OpenLoop, OpenLoopStatus
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "complete",
        "filtered",
        "empty",
        "foreign_cursor",
        "native_off",
        "source_off",
        "late_native_off",
        "late_source_off",
        "late_actor_off",
    ],
)
async def test_open_loop_reader_covers_complete_owned_scope_without_source_reference_leaks(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "open_loops_enabled", True)
    owner = test_user.id
    foreign = User(
        id=uuid4(),
        email=f"loop-read-{uuid4()}@example.test",
        full_name="Other",
        is_active=True,
        is_verified=True,
    )
    async_session.add(foreign)
    await async_session.flush()
    now = datetime.now(UTC)
    count = 0 if scenario == "empty" else 103
    rows = [
        OpenLoop(
            user_id=owner,
            subject=f"Commitment {index}",
            direction="user_owes",
            status="closed" if index == 0 else "open",
            created_at=now,
            source_ref="private-conversation",
        )
        for index in range(count)
    ]
    other = OpenLoop(
        user_id=foreign.id, subject="Foreign commitment secret", direction="waiting_on_other"
    )
    async_session.add_all([*rows, other])
    await async_session.commit()
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    if scenario == "source_off":
        monkeypatch.setattr(settings, "open_loops_enabled", False)
    request = OpenLoopRead(
        status="open" if scenario == "filtered" else None,
        limit=5,
        after_id=other.id if scenario == "foreign_cursor" else None,
    )
    if scenario.startswith("late_"):
        from src.domains.agents.application import open_loop_queries

        source_read = open_loop_queries.read_open_loop_page

        async def changed_after_read(
            db: AsyncSession,
            actor_id: UUID,
            *,
            status: OpenLoopStatus | None,
            limit: int,
            after_id: UUID | None,
        ) -> OpenLoopPage:
            result = await source_read(db, actor_id, status=status, limit=limit, after_id=after_id)
            if scenario == "late_native_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            elif scenario == "late_source_off":
                monkeypatch.setattr(settings, "open_loops_enabled", False)
            else:
                await db.execute(update(User).where(User.id == actor_id).values(is_active=False))
            return result

        monkeypatch.setattr(open_loop_queries, "read_open_loop_page", changed_after_read)
        with pytest.raises(AuthorizationError):
            await read_open_loops(async_session, owner, request)
        return
    if scenario in {"native_off", "source_off"}:
        with pytest.raises(AuthorizationError):
            await read_open_loops(async_session, owner, request)
        return
    if scenario == "foreign_cursor":
        with pytest.raises(ResourceNotFoundError):
            await read_open_loops(async_session, owner, request)
        return
    seen = []
    while True:
        page = await read_open_loops(async_session, owner, request)
        assert page.total == (102 if scenario == "filtered" else count)
        assert page.returned_count == len(page.items) <= 5
        assert "private-conversation" not in str(page.model_dump())
        assert "Foreign commitment secret" not in str(page.model_dump())
        seen.extend(item.id for item in page.items)
        if page.next_cursor is None:
            break
        request = request.model_copy(update={"after_id": page.next_cursor})
    assert len(seen) == len(set(seen)) == (102 if scenario == "filtered" else count)
    assert len(seen) <= 103
