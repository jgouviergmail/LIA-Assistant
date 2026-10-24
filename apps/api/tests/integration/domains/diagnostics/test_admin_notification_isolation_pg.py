"""One admin's notification failing in the database starves nobody (audit AC-003).

An archive whose statement fails aborts the transaction it ran on, and the
dispatcher absorbs the exception but not its effect. Shared, that transaction was
every later admin's and the caller's: their statements failed (25P02), and the
caller's COMMIT rolled back in silence. Each admin is now notified on a session
of its own; this proves it on real PostgreSQL, sessions and all.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.diagnostics import notifications as notif_module
from src.domains.diagnostics.models import INCIDENT_SOURCE_SELF_CHECK, Incident
from src.domains.diagnostics.repository import DiagnosticsRepository
from src.domains.users.models import User
from tests.helpers.notifications import ScriptedChannels, ScriptedDispatcher

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def two_admins(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> AsyncIterator[tuple[UUID, UUID]]:
    admins = (uuid4(), uuid4())
    async with AsyncSession(async_engine) as db:
        for admin in admins:
            db.add(
                User(
                    id=admin,
                    email=f"admin-{admin}@example.test",
                    full_name="Fictional administrator",
                    is_active=True,
                    is_verified=True,
                    is_superuser=True,
                    timezone="UTC",
                )
            )
        await db.flush()
        committed_user_ids.extend(admins)
        await db.commit()
    yield admins


class _ArchiveFailsInSQLFor(ScriptedDispatcher):
    """One admin's archive statement fails on its session; every other one is kept."""

    def __init__(self, failing: UUID, channels: ScriptedChannels, **flags: bool) -> None:
        super().__init__(channels, **flags)
        self.failing = failing

    async def _archive_message(
        self, user: User, content: str, metadata: Mapping[str, object], db: AsyncSession
    ) -> dict[str, object]:
        if user.id == self.failing:
            await db.execute(text("SELECT 1 / 0"))
        return await super()._archive_message(user, content, metadata, db)


async def test_an_admin_whose_archive_failed_in_sql_starves_nobody(
    async_engine: AsyncEngine, two_admins: tuple[UUID, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    failing, _reached = two_admins
    channels = ScriptedChannels(archived=True)
    monkeypatch.setattr(notif_module, "_cooldown_acquired", AsyncMock(return_value=True))
    monkeypatch.setattr(
        notif_module,
        "NotificationDispatcher",
        lambda **flags: _ArchiveFailsInSQLFor(failing, channels, **flags),
    )
    correlation_key = f"isolation-{uuid4()}"

    try:
        async with AsyncSession(async_engine) as caller:
            repo = DiagnosticsRepository(caller)
            incident_id, created, _ = await repo.open_or_touch_incident(
                correlation_key=correlation_key,
                source=INCIDENT_SOURCE_SELF_CHECK,
                severity="critical",
                title="Isolation proof",
            )
            await caller.commit()  # durable first, as both callers do
            admin_ids = {admin.id for admin in await notif_module._active_superusers(caller)}

            sent = await notif_module.notify_admins_of_incident(
                incident_id=incident_id,
                correlation_key=correlation_key,
                severity="critical",
                title="Isolation proof",
                db=caller,
            )
            await caller.commit()  # the caller's session survived every admin's dispatch

        assert created
        assert failing in admin_ids
        assert sent == len(admin_ids) - 1
        async with AsyncSession(async_engine) as reader:
            incident = await reader.get(Incident, incident_id)
            assert incident is not None and incident.notified_at is not None
    finally:
        async with AsyncSession(async_engine) as cleanup:
            await cleanup.execute(
                delete(Incident).where(Incident.correlation_key == correlation_key)
            )
            await cleanup.commit()
