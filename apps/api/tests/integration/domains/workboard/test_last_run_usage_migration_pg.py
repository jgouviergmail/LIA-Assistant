"""A ticket's last run gets back its cache reads and Google requests — real PostgreSQL.

Migration ``1173db815a53`` copies what the settle read at the time: the run's own
summary row first (``message_token_summary``, the authority the settle reads), then,
for a run only its per-node rows still describe (``token_usage_logs``), the cache
reads alone — the Google count those rows do not carry stays NULL, never a zero
nobody measured. A ticket that never settled a run gets nothing. What is proven is
the migration's own statements, in their order.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.chat.models import MessageTokenSummary, TokenUsageLog
from src.domains.users.models import User
from src.domains.workboard.constants import ActorKind, AssigneeKind, TicketPriority, TicketStatus
from src.domains.workboard.models import WorkboardTicket

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)
_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_10_21_2330-1173db815a53_workboard_last_run_cache_and_google.py"
)


def _load_migration() -> ModuleType:
    """The migration module itself, so its backfill SQL is what gets proven."""
    spec = importlib.util.spec_from_file_location("workboard_last_run_usage", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ticket(owner: User, **overrides: Any) -> WorkboardTicket:
    values: dict[str, Any] = {
        "owner_user_id": owner.id,
        "title": "Book the venue",
        "status": TicketStatus.DONE.value,
        "priority": TicketPriority.MEDIUM.value,
        "assignee_kind": AssigneeKind.LIA.value,
        "assignee_user_id": None,
        "position": 0,
        "created_by": ActorKind.USER.value,
        "status_changed_at": NOW,
        "run_attempts": 0,
        "run_count": 1,
        "nudge_count": 0,
    }
    values.update(overrides)
    return WorkboardTicket(**values)


def _log(owner: User, run_id: str, cached: int) -> TokenUsageLog:
    return TokenUsageLog(
        user_id=owner.id,
        run_id=run_id,
        node_name="response",
        model_name="fictional-model",
        prompt_tokens=10,
        completion_tokens=5,
        cached_tokens=cached,
        created_at=NOW,
    )


async def test_the_last_run_reads_back_what_its_ledger_rows_said(
    async_session: AsyncSession,
) -> None:
    owner = User(
        email=f"tickets-{uuid4().hex[:8]}@example.test",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name="Fictional owner",
    )
    async_session.add(owner)
    await async_session.flush()
    summarized = _ticket(owner, last_run_id="run-summary", last_run_tokens_in=100)
    logged = _ticket(owner, last_run_id="run-logs", last_run_tokens_in=50, position=1)
    unsettled = _ticket(owner, last_run_id="run-unsettled", last_run_tokens_in=None, position=2)
    async_session.add_all([summarized, logged, unsettled])
    async_session.add(
        MessageTokenSummary(
            user_id=owner.id,
            session_id="ticket",
            run_id="run-summary",
            total_cached_tokens=40,
            google_api_requests=2,
        )
    )
    async_session.add_all(
        [
            _log(owner, "run-logs", 7),
            _log(owner, "run-logs", 3),
            # The summarized run's per-node rows never override its summary.
            _log(owner, "run-summary", 999),
            _log(owner, "run-unsettled", 5),
            _log(owner, "run-of-no-ticket", 11),
        ]
    )
    await async_session.flush()
    migration = _load_migration()

    for statement in migration.BACKFILL_STATEMENTS:
        await async_session.execute(text(statement))
    for ticket in (summarized, logged, unsettled):
        await async_session.refresh(ticket)

    assert (summarized.last_run_tokens_cache, summarized.last_run_google_requests) == (40, 2)
    assert (logged.last_run_tokens_cache, logged.last_run_google_requests) == (10, None)
    assert (unsettled.last_run_tokens_cache, unsettled.last_run_google_requests) == (None, None)
