"""Nightly habit-profile job (ADR-214) — gating and error isolation.

What must hold:
- the global flag OFF short-circuits before any DB access;
- one failing user never starves the rest (per-user error boundary);
- each user runs in his OWN session (sessions are never shared).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.infrastructure.database as db_module
from src.core.config import settings
from src.infrastructure.scheduler import habit_profile_job as job_module
from src.infrastructure.scheduler.habit_profile_job import run_habit_profile_job


@pytest.fixture
def flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "habits_enabled", True, raising=False)


async def test_flag_off_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "habits_enabled", False, raising=False)

    def _boom() -> None:
        raise AssertionError("DB touched with flag off")

    monkeypatch.setattr(db_module, "get_db_context", _boom)
    monkeypatch.setattr(job_module, "get_db_context", _boom)
    await run_habit_profile_job()


async def test_one_failing_user_never_starves_the_rest(
    monkeypatch: pytest.MonkeyPatch, flag_on: None
) -> None:
    ids = [uuid.uuid4(), uuid.uuid4()]
    sessions_opened: list[MagicMock] = []
    recomputed: list[uuid.UUID] = []

    id_rows = MagicMock()
    id_rows.all.return_value = [(ids[0],), (ids[1],)]

    def _make_session() -> MagicMock:
        session = MagicMock()
        session.execute = AsyncMock(return_value=id_rows)
        session.commit = AsyncMock()
        user = MagicMock()
        user.habits_enabled = True
        session.get = AsyncMock(return_value=user)
        sessions_opened.append(session)
        return session

    @asynccontextmanager
    async def _fake_ctx():  # noqa: ANN202
        yield _make_session()

    monkeypatch.setattr(job_module, "get_db_context", _fake_ctx)

    class _Service:
        def __init__(self, db: Any) -> None:
            self.db = db

        async def recompute_user_profile(self, user: Any) -> str:
            index = len(recomputed)
            recomputed.append(user)
            if index == 0:
                raise RuntimeError("boom")
            return "computed"

    import src.domains.habits.service as service_module

    monkeypatch.setattr(service_module, "HabitsService", _Service)

    await run_habit_profile_job()

    # Both users were attempted despite the first one exploding.
    assert len(recomputed) == 2
    # One session for the id snapshot + one per user — never shared.
    assert len(sessions_opened) == 3
