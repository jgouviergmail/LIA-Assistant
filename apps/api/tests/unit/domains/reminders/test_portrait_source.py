"""The pending reminders as the portrait reads them (2026-10-12).

Every PENDING reminder, whole, with its trigger instant on the person's clock
and its recurrence in the person's language when it repeats; a failed read is
``unavailable``.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from src.domains.journals.portrait_catalogue import eligible_source_items
from src.domains.reminders import portrait_source as module
from src.domains.reminders.portrait_source import read_reminders

pytestmark = pytest.mark.unit

ONCE = {
    "freq": "once",
    "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}]},
    "anchor_date": "2026-10-14",
}
DAILY = {
    "freq": "daily",
    "times": {"mode": "at", "at": [{"hour": 22, "minute": 30}]},
    "anchor_date": "2026-10-01",
}


def _ctx(db: Any):  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def _open():  # type: ignore[no-untyped-def]
        yield db

    return _open


def _reminder(content: str, trigger: datetime, recurrence: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(content=content, trigger_at=trigger, recurrence=recurrence)


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    rows = [
        _reminder(
            "Appeler le fournisseur\nde vernis", datetime(2026, 10, 14, 7, 0, tzinfo=UTC), ONCE
        ),
        _reminder("Étirements du soir", datetime(2026, 10, 12, 20, 30, tzinfo=UTC), DAILY),
    ]
    reader = AsyncMock(return_value=(rows, ZoneInfo("Europe/Paris")))
    monkeypatch.setattr(module, "get_db_context", _ctx(AsyncMock()))
    monkeypatch.setattr(module, "_rows", reader)
    monkeypatch.setattr(module, "describe", lambda spec, language: "tous les jours à 22:30")
    return SimpleNamespace(rows=reader)


async def test_every_pending_reminder_is_rendered_on_the_persons_clock(
    harness: SimpleNamespace,
) -> None:
    section = await read_reminders(user_id=uuid.uuid4(), language="fr")
    assert section.key == "reminders" and section.status == "used"
    assert (section.used, section.total) == (2, 2)
    assert section.text.startswith("## PENDING REMINDERS")
    assert "- Appeler le fournisseur de vernis (2026-10-14 09:00)" in section.text
    # A repeating reminder is its schedule, never its next instant (which moves at
    # every firing and would reopen the consolidation each time).
    assert "- Étirements du soir (tous les jours à 22:30)" in section.text
    assert "2026-10-12" not in section.text
    assert len(eligible_source_items("reminders", section.text)) == 2


async def test_no_pending_reminder_is_empty(harness: SimpleNamespace) -> None:
    harness.rows.return_value = ([], ZoneInfo("Europe/Paris"))
    section = await read_reminders(user_id=uuid.uuid4(), language="fr")
    assert section.status == "empty" and section.total == 0


async def test_a_failed_read_is_named_never_read_as_empty(harness: SimpleNamespace) -> None:
    harness.rows.side_effect = RuntimeError("db gone")
    assert (await read_reminders(user_id=uuid.uuid4(), language="fr")).status == "unavailable"


def test_the_probe_ignores_the_next_instant_of_a_reminder() -> None:
    from src.domains.reminders.portrait_source import FRESHNESS

    assert "trigger_at" not in (FRESHNESS.semantic_columns or ())
