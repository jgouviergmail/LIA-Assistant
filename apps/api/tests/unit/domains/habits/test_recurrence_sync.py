"""Nightly sync of recurring needs with the person's habit rows (ADR-375).

The sync owns the life of a ``recurring_request`` row: a need creates or
refreshes it (payload v2, no locked hour), a need that lapsed demotes an ACTIVE
row, the person's PAUSED and BLOCKED decisions stay theirs, the per-kind cap
keeps the strongest needs, and an unreadable ledger changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from src.domains.habits.models import HabitKind, HabitStatus
from src.domains.habits.needs import NEED_PAYLOAD_VERSION, Need
from src.domains.habits.recurrence_sync import sync_recurring_habits
from src.domains.habits.usage_observations import LedgerView

pytestmark = pytest.mark.unit

TZ = ZoneInfo("Europe/Paris")
TODAY = date(2026, 11, 6)


def _need(domain: str, days: int = 6, last: int = 1) -> Need:
    return Need(
        domain=domain,
        cadence="daily",
        weekday=None,
        usual_hour=9.5,
        prefill_hour=9.0,
        part_of_day="morning",
        distinct_days=days,
        active_days=20,
        occurrences=days,
        at_automation_bar=False,
        last_day=TODAY - timedelta(days=last),
    )


@dataclass
class _Row:
    key: str
    status: str = HabitStatus.ACTIVE.value
    payload: dict[str, Any] = field(default_factory=dict)
    last_observed_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    user_id: UUID = field(default_factory=uuid4)
    kind: str = HabitKind.RECURRING_REQUEST.value


class _Repo:
    def __init__(self, rows: list[_Row] | None = None) -> None:
        self.rows = {row.key: row for row in rows or []}

    async def list_habits(self, user_id: UUID, kind: str | None = None) -> list[_Row]:
        return list(self.rows.values())

    async def upsert_habit(
        self,
        user_id: UUID,
        kind: str,
        key: str,
        payload: dict[str, Any],
        last_observed_at: datetime,
    ) -> str:
        row = self.rows.get(key)
        if row is None:
            self.rows[key] = _Row(key=key, payload=payload, last_observed_at=last_observed_at)
            return "created"
        if row.status == HabitStatus.BLOCKED.value:
            return "blocked"
        row.payload, row.last_observed_at = payload, last_observed_at
        return "updated"

    async def delete_stale_active_habit(self, habit: _Row) -> bool:
        if habit.status != HabitStatus.ACTIVE.value:
            return False
        del self.rows[habit.key]
        return True


def _ledger(**intents: str) -> LedgerView:
    return LedgerView(readable=True, days_by_domain={}, intents=intents)


async def _sync(
    repo: _Repo, needs: list[Need], ledger: LedgerView | None = None, cap: int = 8
) -> Any:
    from types import SimpleNamespace

    return await sync_recurring_habits(
        repo,  # type: ignore[arg-type]
        uuid4(),
        tuple(needs),
        ledger or _ledger(),
        tz=TZ,
        settings=SimpleNamespace(habits_max_habits_per_kind=cap),
    )


async def test_a_need_creates_its_row_with_the_v2_payload() -> None:
    repo = _Repo()
    outcome = await _sync(repo, [_need("event")], _ledger(event="search"))
    assert outcome.created == 1
    row = repo.rows["event"]
    assert row.payload["version"] == NEED_PAYLOAD_VERSION
    assert row.payload["usual_intent"] == "search"
    assert "trigger_hour" not in row.payload


async def test_last_observed_is_the_latest_day_at_local_noon() -> None:
    repo = _Repo()
    await _sync(repo, [_need("event", last=2)])
    assert repo.rows["event"].last_observed_at == datetime(2026, 11, 4, 12, 0, tzinfo=TZ)


async def test_a_paused_row_follows_its_need_and_keeps_its_status() -> None:
    repo = _Repo([_Row(key="event", status=HabitStatus.PAUSED.value, payload={"version": 1})])
    outcome = await _sync(repo, [_need("event")])
    assert outcome.updated == 1
    assert repo.rows["event"].status == HabitStatus.PAUSED.value
    assert repo.rows["event"].payload["version"] == NEED_PAYLOAD_VERSION


async def test_a_blocked_row_is_the_persons_tombstone() -> None:
    repo = _Repo([_Row(key="event", status=HabitStatus.BLOCKED.value, payload={"old": True})])
    outcome = await _sync(repo, [_need("event")])
    assert outcome.blocked == 1
    assert repo.rows["event"].payload == {"old": True}


async def test_a_lapsed_need_demotes_an_active_row_only() -> None:
    repo = _Repo(
        [
            _Row(key="event"),
            _Row(key="email", status=HabitStatus.PAUSED.value),
            _Row(key="task", status=HabitStatus.BLOCKED.value),
        ]
    )
    outcome = await _sync(repo, [])
    assert outcome.demoted == 1
    assert set(repo.rows) == {"email", "task"}


async def test_the_cap_keeps_the_strongest_needs() -> None:
    repo = _Repo()
    outcome = await _sync(
        repo, [_need("weather", days=5), _need("event", days=15), _need("email", days=9)], cap=2
    )
    assert (outcome.created, outcome.capped) == (2, 1)
    assert set(repo.rows) == {"event", "email"}


async def test_a_demotion_frees_its_slot_the_same_night() -> None:
    repo = _Repo([_Row(key="place"), _Row(key="event")])
    outcome = await _sync(repo, [_need("event"), _need("email")], cap=2)
    assert (outcome.demoted, outcome.created, outcome.capped) == (1, 1, 0)
    assert set(repo.rows) == {"event", "email"}


async def test_an_unreadable_ledger_changes_nothing() -> None:
    repo = _Repo([_Row(key="event")])
    outcome = await _sync(repo, [], LedgerView(readable=False, days_by_domain={}, intents={}))
    assert outcome.skipped is True
    assert set(repo.rows) == {"event"}
