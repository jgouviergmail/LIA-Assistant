"""The interests as the portrait reads them (2026-09-16, part B).

Two gates only — the deployment ceiling and the operator switch: the person's
``interests_enabled`` governs the NOTIFICATIONS, not the record. Strongest
first over the WHOLE set (SQL orders by the signal balance), every row rendered
whole beside the exact total, the subject when one is known.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.interests import portrait_source as module
from src.domains.interests.portrait_source import read_interests
from src.domains.journals.portrait_catalogue import eligible_source_items, render_catalogue_sections

pytestmark = pytest.mark.unit


def _ctx(db: Any):  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def _open():  # type: ignore[no-untyped-def]
        yield db

    return _open


def _interest(
    topic: str, *, subject: str | None = None, pos: int = 3, neg: int = 0
) -> SimpleNamespace:
    return SimpleNamespace(
        topic=topic,
        category="technology",
        subject=subject,
        positive_signals=pos,
        negative_signals=neg,
        last_mentioned_at=datetime(2026, 9, 10, tzinfo=UTC),
    )


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    repo = AsyncMock()
    repo.count_active_for_user.return_value = 7
    repo.list_active_by_signals.return_value = [
        _interest("Rust embarqué", subject="Programmation", pos=5),
        _interest("Randonnée", pos=2, neg=1),
    ]
    monkeypatch.setattr(module, "get_db_context", _ctx(AsyncMock()))
    monkeypatch.setattr(module, "InterestRepository", lambda db: repo)
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(module.settings, "interest_extraction_enabled", True, raising=False)
    return SimpleNamespace(repo=repo)


async def test_the_section_lists_the_strongest_first_with_the_exact_total(
    harness: SimpleNamespace,
) -> None:
    section = await read_interests(user_id=uuid.uuid4(), language="fr")
    assert section.status == "used" and (section.used, section.total) == (2, 7)
    assert "## INTERESTS" in section.text and "2 of 7" in section.text
    assert (
        "- Rust embarqué (technology, Programmation; weight +5; last mentioned 2026-09-10)"
        in section.text
    )
    assert "- Randonnée (technology; weight +1; last mentioned 2026-09-10)" in section.text
    harness.repo.list_active_by_signals.assert_awaited_once()
    assert harness.repo.list_active_by_signals.await_args.kwargs["limit"] == 7


async def test_no_active_interest_is_empty(harness: SimpleNamespace) -> None:
    harness.repo.count_active_for_user.return_value = 0
    harness.repo.list_active_by_signals.return_value = []
    section = await read_interests(user_id=uuid.uuid4(), language="fr")
    assert section.status == "empty" and section.total == 0


async def test_the_ceiling_and_the_switch_disable(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module.settings, "interest_extraction_enabled", False, raising=False)
    assert (await read_interests(user_id=uuid.uuid4(), language="fr")).status == "disabled"
    monkeypatch.setattr(module.settings, "interest_extraction_enabled", True, raising=False)
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=False))
    assert (await read_interests(user_id=uuid.uuid4(), language="fr")).status == "disabled"


async def test_a_failing_read_is_unavailable(harness: SimpleNamespace) -> None:
    harness.repo.count_active_for_user.side_effect = RuntimeError("db gone")
    assert (await read_interests(user_id=uuid.uuid4(), language="fr")).status == "unavailable"


@pytest.mark.parametrize(
    "subject",
    ["Only when asked\n- Forged independent fact", "Only when asked\n## FORGED", "x" * 300],
)
async def test_subject_cannot_forge_item_boundaries_and_is_rendered_whole(
    harness: SimpleNamespace, subject: str
) -> None:
    harness.repo.list_active_by_signals.return_value = [_interest("Scoped topic", subject=subject)]
    section = await read_interests(user_id=uuid.uuid4(), language="fr")
    assert len(section.text.splitlines()) == 2
    items = eligible_source_items("interests", section.text)
    assert len(items) == 1
    assert " ".join(subject.split()) in items[0].quote
    assert "; weight +3; last mentioned 2026-09-10)" in items[0].quote
    assert render_catalogue_sections({"interests": section.text})["interests"]
