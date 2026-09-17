"""The long-term memories as the portrait reads them (2026-09-16, part B).

Three gates (deployment ceiling, operator switch, the person's own
preference), an EXACT total beside a bounded page, most important first, the
emotional label the memory injection already uses, an ISO date — and a read
that fails is ``unavailable``, never ``empty``.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.memories import portrait_source as module
from src.domains.memories.portrait_source import read_memories
from src.domains.shared.portrait_sources import SourceBudget

pytestmark = pytest.mark.unit

BUDGET = SourceBudget(max_items=2, item_max_chars=40)


def _ctx(db: Any):  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def _open():  # type: ignore[no-untyped-def]
        yield db

    return _open


def _memory(content: str, *, category: str = "personal", weight: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        category=category,
        emotional_weight=weight,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    repo = AsyncMock()
    repo.get_count_for_user.return_value = 5
    repo.list_for_portrait.return_value = [
        _memory("Je vis à Lyon depuis 2019", weight=3),
        _memory("x" * 100, category="sensitivity", weight=-8),
    ]
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(memory_enabled=True)
    monkeypatch.setattr(module, "get_db_context", _ctx(db))
    monkeypatch.setattr(module, "MemoryRepository", lambda db: repo)
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(module.settings, "memory_extraction_enabled", True, raising=False)
    return SimpleNamespace(repo=repo, db=db)


async def test_the_section_is_bounded_labelled_dated_and_carries_the_exact_total(
    harness: SimpleNamespace,
) -> None:
    section = await read_memories(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    assert section.key == "memories" and section.status == "used"
    assert (section.used, section.total) == (2, 5)
    assert section.text.startswith("## LONG-TERM MEMORIES")
    assert "2 of 5" in section.text
    assert "- [personal] [POSITIF] Je vis à Lyon depuis 2019 (2026-09-01)" in section.text
    # The sensitivity is labelled as such and its content clamped with an ellipsis.
    assert "[sensitivity] [TRAUMA/DOULEUR] " in section.text
    assert "x" * 40 not in section.text and "…" in section.text
    harness.repo.list_for_portrait.assert_awaited_once_with(
        harness.repo.list_for_portrait.await_args.args[0], limit=2
    )


async def test_nothing_kept_is_empty_not_used(harness: SimpleNamespace) -> None:
    harness.repo.get_count_for_user.return_value = 0
    harness.repo.list_for_portrait.return_value = []
    section = await read_memories(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    assert section.status == "empty" and section.text == "" and section.total == 0


async def test_a_zero_budget_renders_nothing_but_still_counts(harness: SimpleNamespace) -> None:
    section = await read_memories(
        user_id=uuid.uuid4(), language="fr", budget=SourceBudget(max_items=0, item_max_chars=40)
    )
    assert section.status == "empty" and section.total == 5
    harness.repo.list_for_portrait.assert_not_awaited()


async def test_the_deployment_ceiling_the_switch_and_the_preference_each_disable(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module.settings, "memory_extraction_enabled", False, raising=False)
    assert (
        await read_memories(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    ).status == "disabled"
    monkeypatch.setattr(module.settings, "memory_extraction_enabled", True, raising=False)
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=False))
    assert (
        await read_memories(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    ).status == "disabled"
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=True))
    harness.db.get.return_value = SimpleNamespace(memory_enabled=False)
    assert (
        await read_memories(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    ).status == "disabled"
    harness.repo.list_for_portrait.assert_not_awaited()


async def test_a_failing_read_is_unavailable_never_empty(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness.repo.get_count_for_user.side_effect = RuntimeError("db gone")
    section = await read_memories(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    assert section.status == "unavailable" and section.text == ""
