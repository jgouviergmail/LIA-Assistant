"""The nightly sync owns the LIFE of a recurring habit — not the chat.

Until 2026-09-11 a ``recurring_request`` row was created by the chat
suggestion alone (behind a 30-day cooldown, the initiative node and two
flags of other features), never refreshed between two fires, never demoted
when its evidence vanished (a ledger that expired still produced « missed
routine » offers — sim C4-b), and its mute lifted only at the next fire
(sim B: an occurrence the very next day left ``muted_until_reproof`` True).

The sync evaluates every signature of the person's ledger once a night:
promotes what locks, refreshes what is still proven, keeps a row whose lock
merely wavered while its evidence remains, and demotes an ACTIVE row whose
request stopped — the person's own statuses (paused, blocked) and the per-kind
cap are honoured, ``offer_dates`` survives, and a Redis that cannot be read
changes NOTHING (never demote on doubt).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.habits.models import HabitKind, HabitStatus
from src.domains.habits.offer_bookkeeping import (
    ignored_offer_count,
    occurrence_after_last_offer,
)
from src.domains.habits.recurrence_sync import (
    RecurringSyncOutcome,
    lock_payload,
    sync_recurring_habits,
)
from src.infrastructure.cache import recurrence_store

pytestmark = pytest.mark.unit

TODAY = date(2026, 9, 11)
USER = uuid.uuid4()


def _settings(**overrides: Any) -> SimpleNamespace:
    base = {
        "recurrence_window_days": 35,
        "recurrence_min_distinct_days": 4,
        "recurrence_ledger_max_entries": 35,
        "recurrence_day_hours_cap": 5,
        "recurrence_lock_min_occurrences": 6,
        "recurrence_lock_min_spread_days": 10,
        "recurrence_lock_r_min": 0.8,
        "recurrence_lock_half_r_min": 0.7,
        "recurrence_lock_half_agree_hours": 2.0,
        "recurrence_shape_min_span_days": 10,
        "recurrence_daily_density_min": 0.6,
        "recurrence_intermittent_r_min": 0.9,
        "recurrence_weekend_tolerance": 1,
        "recurrence_weekly_min_same_dow": 4,
        "recurrence_weekly_dow_fraction": 0.75,
        "habits_max_habits_per_kind": 8,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _daily_payload(days: int = 20, *, hour: float = 9.0, origin: str = "live") -> dict:
    return {
        "days": {(TODAY - timedelta(days=k)).isoformat(): [hour] for k in range(1, days + 1)},
        "suggested_at": None,
        "origin": origin,
    }


class _FakeRedis:
    def __init__(self, payloads: dict[str, dict]) -> None:
        self.data = {
            recurrence_store.redis_key(str(USER), sig): json.dumps(p) for sig, p in payloads.items()
        }

    def scan_iter(self, match: str) -> Any:
        prefix = match[:-1]

        async def _iter() -> Any:
            for key in list(self.data):
                if key.startswith(prefix):
                    yield key

        return _iter()

    async def get(self, key: str) -> str | None:
        return self.data.get(key)


class _FakeRepo:
    """The habits repository surface the sync touches, in memory."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows: list[Any] = list(rows or [])
        self.upserts: list[dict[str, Any]] = []
        self.deleted: list[str] = []

    async def list_habits(self, user_id: uuid.UUID, kind: str | None = None) -> list[Any]:
        return [r for r in self.rows if kind is None or r.kind == kind]

    async def upsert_habit(
        self,
        *,
        user_id: uuid.UUID,
        kind: str,
        key: str,
        payload: dict[str, Any],
        last_observed_at: datetime,
        reset_mute: bool = True,
    ) -> str:
        self.upserts.append(
            {
                "key": key,
                "payload": payload,
                "last_observed_at": last_observed_at,
                "reset_mute": reset_mute,
            }
        )
        for row in self.rows:
            if row.key == key and row.kind == kind:
                if row.status == HabitStatus.BLOCKED.value:
                    return "blocked"
                row.payload = {
                    **{k: v for k, v in row.payload.items() if k == "offer_dates"},
                    **payload,
                }
                row.last_observed_at = last_observed_at
                if reset_mute:
                    row.muted_until_reproof = False
                return "updated"
        self.rows.append(_row(key, payload=payload, last_observed_at=last_observed_at))
        return "created"

    async def touch_habit(self, habit: Any, last_observed_at: datetime) -> None:
        habit.last_observed_at = last_observed_at

    async def delete_habit(self, habit: Any) -> None:
        self.deleted.append(habit.key)
        self.rows.remove(habit)


def _row(
    key: str,
    *,
    status: str = HabitStatus.ACTIVE.value,
    payload: dict | None = None,
    muted: bool = False,
    last_observed_at: datetime | None = None,
) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        kind=HabitKind.RECURRING_REQUEST.value,
        key=key,
        status=status,
        payload=payload
        or {"version": 1, "shape": "daily", "trigger_hour": 9.0, "days_of_week": list(range(7))},
        muted_until_reproof=muted,
        last_observed_at=last_observed_at or datetime(2026, 8, 1, tzinfo=UTC),
    )


def _redis_patch(redis: Any) -> Any:
    return patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=redis))


class TestOfferBookkeeping:
    def test_ignored_offer_count_resets_on_a_later_occurrence(self) -> None:
        assert ignored_offer_count(["2026-09-01", "2026-09-08"], {"2026-09-05"}) == 1
        assert ignored_offer_count(["2026-09-01", "2026-09-08"], set()) == 2
        assert ignored_offer_count([], set()) == 0

    def test_same_day_uptake_is_an_uptake(self) -> None:
        # An offer is only made once today's slot was missed, so an occurrence
        # on the offer's own day can only have followed it.
        assert ignored_offer_count(["2026-09-01", "2026-09-08"], {"2026-09-08"}) == 0

    def test_occurrence_after_last_offer(self) -> None:
        assert occurrence_after_last_offer([], {"2026-09-10"}) is True
        assert occurrence_after_last_offer(["2026-09-08"], {"2026-09-10"}) is True
        assert occurrence_after_last_offer(["2026-09-08"], {"2026-09-08", "2026-09-01"}) is True
        assert occurrence_after_last_offer(["2026-09-08"], {"2026-09-07"}) is False
        assert occurrence_after_last_offer(["2026-09-08"], set()) is False


class TestLockPayload:
    def test_carries_the_learned_schedule_only(self) -> None:
        from src.domains.habits.recurrence_locks import RecurrenceLock

        lock = RecurrenceLock(
            shape="daily", trigger_hour=9.05, modal_weekday=None, distinct_days=20, occurrences=21
        )
        assert lock_payload(lock) == {
            "version": 1,
            "shape": "daily",
            "trigger_hour": 9.05,
            "days_of_week": [0, 1, 2, 3, 4, 5, 6],
            "distinct_days": 20,
            "occurrences": 21,
        }

    def test_names_the_usual_request_only_when_one_is_known(self) -> None:
        """Q4: the descriptor is a field of the payload when the ledger holds
        one, and ABSENT otherwise — never an empty placeholder."""
        from src.domains.habits.recurrence_locks import RecurrenceLock

        lock = RecurrenceLock(
            shape="daily", trigger_hour=9.0, modal_weekday=None, distinct_days=20, occurrences=21
        )
        assert lock_payload(lock, usual_intent="search")["usual_intent"] == "search"
        assert "usual_intent" not in lock_payload(lock, usual_intent=None)
        assert "usual_intent" not in lock_payload(lock, usual_intent="")


class TestSyncRecurringHabits:
    async def test_a_locked_signature_is_promoted_without_any_chat_turn(self) -> None:
        repo = _FakeRepo()
        with _redis_patch(_FakeRedis({"email": _daily_payload()})):
            outcome = await sync_recurring_habits(
                repo, USER, "Europe/Paris", _settings(), local_today=TODAY
            )
        assert outcome == RecurringSyncOutcome(created=1)
        [row] = repo.rows
        assert row.key == "email" and row.payload["shape"] == "daily"
        assert row.last_observed_at.date() == TODAY - timedelta(days=1)

    async def test_the_promoted_row_names_what_the_person_usually_asks(self) -> None:
        payload = {**_daily_payload(), "intents": {"search": 9, "send": 2}}
        repo = _FakeRepo()
        with _redis_patch(_FakeRedis({"email": payload})):
            await sync_recurring_habits(repo, USER, "Europe/Paris", _settings(), local_today=TODAY)
        [row] = repo.rows
        assert row.payload["usual_intent"] == "search"

    async def test_a_seeded_ledger_promotes_without_a_descriptor(self) -> None:
        # ``product_outcomes`` stores no intent: a payload the seed rebuilt
        # carries none, and the row says nothing rather than something made up.
        repo = _FakeRepo()
        with _redis_patch(_FakeRedis({"email": _daily_payload(origin="seed")})):
            await sync_recurring_habits(repo, USER, "Europe/Paris", _settings(), local_today=TODAY)
        [row] = repo.rows
        assert "usual_intent" not in row.payload

    async def test_a_proven_row_is_refreshed_and_offer_dates_survive(self) -> None:
        row = _row(
            "email",
            payload={
                "version": 1,
                "shape": "weekly",
                "trigger_hour": 8.0,
                "offer_dates": ["2026-09-02"],
            },
        )
        repo = _FakeRepo([row])
        with _redis_patch(_FakeRedis({"email": _daily_payload()})):
            outcome = await sync_recurring_habits(
                repo, USER, "Europe/Paris", _settings(), local_today=TODAY
            )
        assert outcome == RecurringSyncOutcome(updated=1)
        assert row.payload["shape"] == "daily"  # the shape followed the evidence
        assert row.payload["offer_dates"] == ["2026-09-02"]  # the bookkeeping survived

    async def test_a_fresh_occurrence_lifts_the_mute(self) -> None:
        muted = _row(
            "email",
            payload={"version": 1, "shape": "daily", "offer_dates": ["2026-09-02"]},
            muted=True,
        )
        repo = _FakeRepo([muted])
        with _redis_patch(_FakeRedis({"email": _daily_payload()})):  # occurrences up to 2026-09-10
            await sync_recurring_habits(repo, USER, "Europe/Paris", _settings(), local_today=TODAY)
        assert muted.muted_until_reproof is False

    async def test_no_occurrence_since_the_offers_keeps_the_mute(self) -> None:
        # occurrences stop on 2026-08-31; the two offers came after → still ignored
        payload = {
            "days": {(TODAY - timedelta(days=k)).isoformat(): [9.0] for k in range(11, 31)},
            "suggested_at": None,
        }
        muted = _row(
            "email",
            payload={"version": 1, "shape": "daily", "offer_dates": ["2026-09-02", "2026-09-09"]},
            muted=True,
        )
        repo = _FakeRepo([muted])
        with _redis_patch(_FakeRedis({"email": payload})):
            await sync_recurring_habits(repo, USER, "Europe/Paris", _settings(), local_today=TODAY)
        assert muted.muted_until_reproof is True
        assert repo.upserts[-1]["reset_mute"] is False

    async def test_a_wavering_lock_keeps_the_row_while_evidence_remains(self) -> None:
        # 5 scattered hours over 12 days: exists (≥4 distinct days) but no lock (R too low)
        payload = {
            "days": {
                (TODAY - timedelta(days=k)).isoformat(): [h]
                for k, h in ((1, 9.0), (3, 15.0), (5, 21.0), (8, 3.0), (12, 12.0))
            },
            "suggested_at": None,
        }
        row = _row("email")
        repo = _FakeRepo([row])
        with _redis_patch(_FakeRedis({"email": payload})):
            outcome = await sync_recurring_habits(
                repo, USER, "Europe/Paris", _settings(), local_today=TODAY
            )
        assert outcome == RecurringSyncOutcome(kept=1)
        assert row in repo.rows and row.payload["shape"] == "daily"  # payload untouched
        assert row.last_observed_at.date() == TODAY - timedelta(days=1)

    async def test_an_active_row_whose_request_stopped_is_demoted(self) -> None:
        row = _row("email")
        gone = _row("weather")  # no ledger key at all: the ledger expired
        repo = _FakeRepo([row, gone])
        thin = {
            "days": {(TODAY - timedelta(days=k)).isoformat(): [9.0] for k in (1, 2)},
            "suggested_at": None,
        }
        with _redis_patch(_FakeRedis({"email": thin})):
            outcome = await sync_recurring_habits(
                repo, USER, "Europe/Paris", _settings(), local_today=TODAY
            )
        assert outcome == RecurringSyncOutcome(demoted=2)
        assert repo.rows == []

    @pytest.mark.parametrize("status", [HabitStatus.PAUSED.value, HabitStatus.BLOCKED.value])
    async def test_the_persons_own_statuses_are_never_demoted(self, status: str) -> None:
        row = _row("email", status=status)
        repo = _FakeRepo([row])
        with _redis_patch(_FakeRedis({})):
            outcome = await sync_recurring_habits(
                repo, USER, "Europe/Paris", _settings(), local_today=TODAY
            )
        assert outcome == RecurringSyncOutcome()
        assert repo.rows == [row]

    async def test_a_blocked_signature_is_never_recreated_nor_refreshed(self) -> None:
        row = _row(
            "email", status=HabitStatus.BLOCKED.value, payload={"version": 1, "shape": "weekly"}
        )
        repo = _FakeRepo([row])
        with _redis_patch(_FakeRedis({"email": _daily_payload()})):
            outcome = await sync_recurring_habits(
                repo, USER, "Europe/Paris", _settings(), local_today=TODAY
            )
        assert outcome == RecurringSyncOutcome(blocked=1)
        assert row.payload["shape"] == "weekly"

    async def test_a_paused_row_follows_the_evidence_but_stays_paused(self) -> None:
        row = _row(
            "email", status=HabitStatus.PAUSED.value, payload={"version": 1, "shape": "weekly"}
        )
        repo = _FakeRepo([row])
        with _redis_patch(_FakeRedis({"email": _daily_payload()})):
            outcome = await sync_recurring_habits(
                repo, USER, "Europe/Paris", _settings(), local_today=TODAY
            )
        assert outcome == RecurringSyncOutcome(updated=1)
        assert row.status == HabitStatus.PAUSED.value and row.payload["shape"] == "daily"

    async def test_the_per_kind_cap_is_enforced_on_new_rows_only(self) -> None:
        existing = [_row(f"d{i}") for i in range(2)]
        repo = _FakeRepo(existing)
        payloads = {"d0": _daily_payload(), "email": _daily_payload(), "weather": _daily_payload()}
        with _redis_patch(_FakeRedis(payloads)):
            outcome = await sync_recurring_habits(
                repo,
                USER,
                "Europe/Paris",
                _settings(habits_max_habits_per_kind=2),
                local_today=TODAY,
            )
        # d0 refreshed; d1 (no ledger) demoted → one slot frees, one new row fits, one is capped
        assert outcome.updated == 1 and outcome.demoted == 1
        assert outcome.created + outcome.capped == 2 and outcome.created == 1

    async def test_redis_down_changes_nothing(self) -> None:
        row = _row("email")
        repo = _FakeRepo([row])
        with _redis_patch(None):
            outcome = await sync_recurring_habits(
                repo, USER, "Europe/Paris", _settings(), local_today=TODAY
            )
        assert outcome == RecurringSyncOutcome(skipped=True)
        assert repo.rows == [row] and repo.deleted == []

    async def test_a_scan_failure_changes_nothing(self) -> None:
        redis = MagicMock()

        async def _boom(match: str) -> Any:
            raise RuntimeError("redis exploded")
            yield  # pragma: no cover

        redis.scan_iter = _boom
        row = _row("email")
        repo = _FakeRepo([row])
        with _redis_patch(redis):
            outcome = await sync_recurring_habits(
                repo, USER, "Europe/Paris", _settings(), local_today=TODAY
            )
        assert outcome == RecurringSyncOutcome(skipped=True)
        assert repo.rows == [row]
