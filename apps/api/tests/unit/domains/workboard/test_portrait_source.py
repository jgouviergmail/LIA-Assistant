"""The workboard as the portrait reads it (2026-10-12): the tickets the person owns or holds.

Every visible ticket, whole, with its status, priority, due date, holder and
description; two gates read at call time; a failed read is ``unavailable``.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.journals.portrait_catalogue import eligible_source_items
from src.domains.workboard import portrait_source as module
from src.domains.workboard.portrait_source import read_workboard

pytestmark = pytest.mark.unit


def _ctx(db: Any):  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def _open():  # type: ignore[no-untyped-def]
        yield db

    return _open


def _ticket(
    title: str,
    *,
    description: str | None = None,
    status: str = "todo",
    priority: str = "medium",
    due: datetime | None = None,
    assignee_kind: str = "human",
) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        description=description,
        status=status,
        priority=priority,
        due_at=due,
        assignee_kind=assignee_kind,
    )


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    rows = [
        _ticket(
            "Préparer la grille",
            description="Compiler les disponibilités\nde l'équipe.",
            status="in_progress",
            priority="high",
            due=datetime(2026, 10, 18, tzinfo=UTC),
            assignee_kind="lia",
        ),
        _ticket("Classer les tickets"),
    ]
    reader = AsyncMock(return_value=rows)
    monkeypatch.setattr(module, "get_db_context", _ctx(AsyncMock()))
    monkeypatch.setattr(module, "_rows", reader)
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(module.settings, "workboard_enabled", True, raising=False)
    return SimpleNamespace(rows=reader)


async def test_every_visible_ticket_is_rendered_whole(harness: SimpleNamespace) -> None:
    section = await read_workboard(user_id=uuid.uuid4(), language="fr")
    assert section.key == "workboard" and section.status == "used"
    assert (section.used, section.total) == (2, 2)
    assert section.text.startswith("## WORKBOARD")
    assert (
        "- Préparer la grille [in_progress, priority high, due 2026-10-18, delegated to LIA]: "
        "Compiler les disponibilités de l'équipe." in section.text
    )
    assert "- Classer les tickets [todo, priority medium]" in section.text
    assert len(eligible_source_items("workboard", section.text)) == 2


async def test_no_ticket_is_empty(harness: SimpleNamespace) -> None:
    harness.rows.return_value = []
    section = await read_workboard(user_id=uuid.uuid4(), language="fr")
    assert section.status == "empty" and section.total == 0


async def test_a_closed_gate_answers_disabled(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module.settings, "workboard_enabled", False, raising=False)
    assert (await read_workboard(user_id=uuid.uuid4(), language="fr")).status == "disabled"
    monkeypatch.setattr(module.settings, "workboard_enabled", True, raising=False)
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=False))
    assert (await read_workboard(user_id=uuid.uuid4(), language="fr")).status == "disabled"
    harness.rows.assert_not_awaited()


async def test_a_failed_read_is_named_never_read_as_empty(harness: SimpleNamespace) -> None:
    harness.rows.side_effect = RuntimeError("db gone")
    assert (await read_workboard(user_id=uuid.uuid4(), language="fr")).status == "unavailable"
