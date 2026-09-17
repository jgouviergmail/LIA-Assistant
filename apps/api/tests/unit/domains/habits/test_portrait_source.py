"""The learned habits as the portrait reads them (2026-09-16, part B).

Three gates (deployment ceiling, the capability read at the act, the person's
own preference); the rhythm through ``load_consumable_profile`` so a paused or
blocked window never colours the portrait either (ADR-214 c); the recurring
requests ACTIVE only, with their shape, hour and usual intent — never a date.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.habits import portrait_source as module
from src.domains.habits.portrait_source import read_habits
from src.domains.habits.rhythm import ClaimedWindow, ClassRhythm, RhythmProfile
from src.domains.shared.portrait_sources import SourceBudget

pytestmark = pytest.mark.unit

BUDGET = SourceBudget(max_items=2, item_max_chars=40)


def _ctx(db: Any):  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def _open():  # type: ignore[no-untyped-def]
        yield db

    return _open


def _profile(
    windows: tuple[ClaimedWindow, ...], *, sparse: bool = False, fraction: float = 0.8
) -> RhythmProfile:
    weekday = ClassRhythm(
        verdict="windows" if windows else "none",
        windows=windows,
        n_eff=20.0,
        bin_presence=tuple([0.0] * 24),
    )
    weekend = ClassRhythm(verdict="none", windows=(), n_eff=8.0, bin_presence=tuple([0.0] * 24))
    return RhythmProfile(
        weekday=weekday, weekend=weekend, active_days_fraction=fraction, sparse=sparse
    )


def _habit(
    key: str,
    *,
    status: str = "active",
    shape: str = "weekly",
    hour: float | None = 9.5,
    intent: str | None = "weekly report",
) -> SimpleNamespace:
    payload: dict[str, Any] = {"shape": shape, "trigger_hour": hour}
    if intent:
        payload["usual_intent"] = intent
    return SimpleNamespace(key=key, status=status, payload=payload)


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    repo = AsyncMock()
    repo.list_habits.return_value = [
        _habit("email+contact"),
        _habit("weather", status="blocked"),
        _habit("task", shape="daily", hour=None, intent=None),
    ]
    profile = _profile(
        (
            ClaimedWindow(start_hour=8, end_hour=10, presence=0.9),
            ClaimedWindow(start_hour=18, end_hour=22, presence=0.7),
        )
    )
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(habits_enabled=True)
    monkeypatch.setattr(module, "get_db_context", _ctx(db))
    monkeypatch.setattr(module, "HabitsRepository", lambda db: repo)
    monkeypatch.setattr(module, "load_consumable_profile", AsyncMock(return_value=profile))
    monkeypatch.setattr(module, "habits_capability_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(module.settings, "habits_enabled", True, raising=False)
    return SimpleNamespace(repo=repo, db=db)


async def test_the_section_carries_the_consumable_windows_and_the_active_recurrences(
    harness: SimpleNamespace,
) -> None:
    section = await read_habits(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    assert section.status == "used"
    assert "## LEARNED HABITS" in section.text
    assert (
        "- Usual activity: weekdays 08:00-10:00, 18:00-22:00; active on 80% of observed days"
        in section.text
    )
    assert (
        "- Recurring request: email+contact — weekly around 09:30 (weekly report)" in section.text
    )
    assert "- Recurring request: task — daily" in section.text
    assert "weather" not in section.text  # blocked: the person's tombstone
    # One rhythm line + two recurrences, and nothing here is capped by items.
    assert (section.used, section.total) == (3, 3)


async def test_an_occasional_use_says_so_instead_of_a_window(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        module,
        "load_consumable_profile",
        AsyncMock(return_value=_profile((), sparse=True, fraction=0.2)),
    )
    harness.repo.list_habits.return_value = []
    section = await read_habits(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    assert section.status == "used"
    assert "active on 20% of observed days (occasional use: no window claimed)" in section.text
    assert "Usual activity: ;" not in section.text


async def test_nothing_learned_is_empty(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "load_consumable_profile", AsyncMock(return_value=None))
    harness.repo.list_habits.return_value = []
    section = await read_habits(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    assert section.status == "empty" and section.total == 0


async def test_the_three_gates_each_disable(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module.settings, "habits_enabled", False, raising=False)
    assert (
        await read_habits(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    ).status == "disabled"
    monkeypatch.setattr(module.settings, "habits_enabled", True, raising=False)
    monkeypatch.setattr(module, "habits_capability_enabled", AsyncMock(return_value=False))
    assert (
        await read_habits(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    ).status == "disabled"
    monkeypatch.setattr(module, "habits_capability_enabled", AsyncMock(return_value=True))
    harness.db.get.return_value = SimpleNamespace(habits_enabled=False)
    assert (
        await read_habits(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    ).status == "disabled"


async def test_a_failing_read_is_unavailable(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        module, "load_consumable_profile", AsyncMock(side_effect=RuntimeError("redis"))
    )
    assert (
        await read_habits(user_id=uuid.uuid4(), language="fr", budget=BUDGET)
    ).status == "unavailable"
