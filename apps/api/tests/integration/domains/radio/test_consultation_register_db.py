"""From radio adapters to persisted, owner-scoped consultation journal."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.origin import RegisterOrigin
from src.domains.agents.effects.treatments_router import list_treatment_journal
from src.domains.radio.adapters import NewsDesk, NotificationFlashes
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_radio_reads_reach_the_account_journal_even_when_sources_are_empty(
    async_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.radio import repository
    from src.domains.radio.readers import notifications
    from src.infrastructure.database import session as session_module

    @asynccontextmanager
    async def context() -> AsyncIterator[AsyncSession]:
        # The fixture owns an outer transaction: other connections cannot see
        # its users. Keep real SQL/readers/recorder on that isolated connection.
        yield async_session

    monkeypatch.setattr(session_module, "get_db_context", context)
    monkeypatch.setattr(repository, "get_db_context", context)
    monkeypatch.setattr(notifications, "get_db_context", context)
    owner = User(email="radio-register-owner@test.local", hashed_password="x", is_active=True)
    other = User(email="radio-register-other@test.local", hashed_password="x", is_active=True)
    async_session.add_all([owner, other])
    await async_session.commit()
    now = datetime.now(UTC)
    news = NewsDesk(
        user_id=owner.id,
        run_id="radio_register_proof",
        disabled_feeds=frozenset(),
        clock=lambda: now,
    )
    assert await news.candidates(heard_keys=frozenset(), heard_stories=frozenset()) == []
    assert await NotificationFlashes(owner.id, "radio_register_proof").since(now) == []

    async def journal(user: User):
        return await list_treatment_journal(
            limit=20,
            offset=0,
            tool_name=None,
            since=None,
            until=None,
            origin=RegisterOrigin.MINE,
            db=async_session,
            user=user,
        )

    page = await journal(owner)
    assert page.total == 2
    assert {(row.tool_name, row.outcome, row.source, row.run_id) for row in page.entries} == {
        ("radio:news", "ok", "user", "radio_register_proof"),
        ("radio:notifications", "ok", "user", "radio_register_proof"),
    }
    assert (await journal(other)).total == 0
