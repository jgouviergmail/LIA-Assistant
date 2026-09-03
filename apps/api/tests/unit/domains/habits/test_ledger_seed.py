"""Recurrence-ledger seed from ``product_outcomes`` (ADR-214 rebuild lot).

The ledger is advisory Redis — a flush costs ~a week of recurrence
relearning. Since the domain seam ships, ``product_outcomes`` holds the
durable (user, domain, produced_at) truth, so an EMPTY ledger can be
reseeded. Contract under test:

- seed only when the user's ledger is EMPTY (live data always wins), and
  per-key NX as belt-and-braces;
- the same human-run whitelist as every other durable source (an outcome
  whose run maps to an automated session family must never seed — the
  scheduled-action metronome class, proven on prod 2026-08-05);
- store caps and format come from the SHARED recurrence store (end-to-end:
  what the seed writes, the agents lock evaluation can read);
- gated on the recurrence flag, best-effort on any failure.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.habits.ledger_seed import _SEED_ACTIVITY_SQL, seed_ledger_from_outcomes
from src.infrastructure.cache import recurrence_store

pytestmark = pytest.mark.unit


def _settings(**overrides: object) -> SimpleNamespace:
    base = {
        "recurrence_suggestion_enabled": True,
        "recurrence_window_days": 28,
        "recurrence_day_hours_cap": 4,
        "recurrence_ledger_max_entries": 28,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeRedis:
    """NX-faithful in-memory double."""

    def __init__(self, preexisting: dict[str, str] | None = None) -> None:
        self.data: dict[str, str] = dict(preexisting or {})

    async def set(self, key: str, value: str, ex: int, nx: bool = False) -> bool | None:
        if nx and key in self.data:
            return None
        self.data[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    def scan_iter(self, match: str) -> object:
        prefix = match[:-1]

        async def _iter() -> object:
            for key in list(self.data):
                if key.startswith(prefix):
                    yield key

        return _iter()


def _db_with_rows(rows: list[tuple[str, str, float]]) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = rows
    db.execute = AsyncMock(return_value=result)
    nested = MagicMock()
    nested.__aenter__ = AsyncMock(return_value=MagicMock())
    nested.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=nested)
    return db


def _patch_redis(redis: _FakeRedis | None) -> object:
    return patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        AsyncMock(return_value=redis),
    )


class TestSeedLedgerFromOutcomes:
    async def test_seeds_per_domain_days_readable_by_the_store(self) -> None:
        user_id = uuid4()
        redis = _FakeRedis()
        db = _db_with_rows(
            [
                ("email", "2026-08-01", 9.0),
                ("email", "2026-08-01", 9.5),
                ("email", "2026-08-02", 9.25),
                ("calendar", "2026-08-02", 14.0),
            ]
        )
        with _patch_redis(redis):
            seeded = await seed_ledger_from_outcomes(db, user_id, "Europe/Paris", _settings())

        assert seeded == 2
        # End-to-end: what the seed wrote, the shared store reads back.
        data = await recurrence_store.load(redis, recurrence_store.redis_key(str(user_id), "email"))
        days = recurrence_store.parse_days(data)
        assert days == {date(2026, 8, 1): [9.0, 9.5], date(2026, 8, 2): [9.25]}
        assert data["suggested_at"] is None

    async def test_non_empty_ledger_is_never_touched(self) -> None:
        user_id = uuid4()
        live_key = recurrence_store.redis_key(str(user_id), "email")
        redis = _FakeRedis({live_key: '{"days": {"2026-08-03": [10.0]}, "suggested_at": null}'})
        db = _db_with_rows([("email", "2026-08-01", 9.0)])
        with _patch_redis(redis):
            seeded = await seed_ledger_from_outcomes(db, user_id, "Europe/Paris", _settings())
        assert seeded == 0
        db.execute.assert_not_awaited()  # no SQL when the ledger is alive
        assert "2026-08-01" not in redis.data[live_key]

    async def test_flag_off_short_circuits_before_any_io(self) -> None:
        db = _db_with_rows([])
        with _patch_redis(_FakeRedis()) as redis_mock:
            seeded = await seed_ledger_from_outcomes(
                db, uuid4(), "Europe/Paris", _settings(recurrence_suggestion_enabled=False)
            )
        assert seeded == 0
        redis_mock.assert_not_called()
        db.execute.assert_not_awaited()

    async def test_redis_down_is_best_effort(self) -> None:
        db = _db_with_rows([("email", "2026-08-01", 9.0)])
        with _patch_redis(None):
            assert await seed_ledger_from_outcomes(db, uuid4(), "Europe/Paris", _settings()) == 0

    async def test_sql_failure_is_contained_in_a_savepoint(self) -> None:
        """A failed statement poisons the shared transaction: the seed wraps
        its SELECT in a savepoint so the caller's profile COMMIT survives
        (code-review catch — ADR-204 poisoned-session trap)."""
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("relation gone"))
        nested = MagicMock()
        nested.__aenter__ = AsyncMock(return_value=MagicMock())
        nested.__aexit__ = AsyncMock(return_value=False)
        db.begin_nested = MagicMock(return_value=nested)
        with _patch_redis(_FakeRedis()):
            assert await seed_ledger_from_outcomes(db, uuid4(), "Europe/Paris", _settings()) == 0
        db.begin_nested.assert_called_once()  # the savepoint is the containment

    async def test_caps_apply_hours_per_day_and_day_entries(self) -> None:
        user_id = uuid4()
        redis = _FakeRedis()
        rows = [("email", "2026-08-01", float(h)) for h in range(9, 19)]  # 10 hours, cap 4
        rows += [("email", f"2026-07-{d:02d}", 9.0) for d in range(1, 31)]  # 31 days, cap 28
        db = _db_with_rows(rows)
        with _patch_redis(redis):
            await seed_ledger_from_outcomes(db, user_id, "Europe/Paris", _settings())
        data = await recurrence_store.load(redis, recurrence_store.redis_key(str(user_id), "email"))
        days = recurrence_store.parse_days(data)
        assert len(days[date(2026, 8, 1)]) == 4  # hours-per-day cap
        assert len(days) == 28  # newest day entries kept (store trim)

    async def test_sql_uses_the_shared_human_predicate_and_domain_filter(self) -> None:
        """One definition of "human" for the seed AND the rhythm repository
        (2026-09-03: the summary whitelist read "no summary" as "human" and
        seeded 183 scheduler outcomes as the user's recurrences)."""
        from src.domains.habits.human_turns import HUMAN_OUTCOME_PREDICATE_SQL

        sql = str(_SEED_ACTIVITY_SQL)
        assert "product_outcomes" in sql
        assert HUMAN_OUTCOME_PREDICATE_SQL in sql
        assert "message_token_summary" not in sql
        assert "'unknown'" in sql  # unlabeled history never seeds
        assert ":uuid_regex" not in sql

    async def test_seeded_payload_states_its_provenance(self) -> None:
        """A candidate rebuilt from history says so (``origin: seed``) — the
        settings screen states provenance, it never applies a different bar."""
        user_id = uuid4()
        redis = _FakeRedis()
        db = _db_with_rows([("email", "2026-08-01", 9.0)])
        with _patch_redis(redis):
            await seed_ledger_from_outcomes(db, user_id, "Europe/Paris", _settings())
        data = await recurrence_store.load(redis, recurrence_store.redis_key(str(user_id), "email"))
        assert data["origin"] == recurrence_store.ORIGIN_SEED


class TestRecomputeTriggersSeed:
    async def test_recompute_seeds_before_the_delta_skip(self) -> None:
        """The seed is banked like the rollup: a delta-skip must not starve
        it, and the manual recompute button gets recurrence retroactivity
        for free (same code path)."""
        from tests.unit.domains.habits.test_habits_service import (
            _service_with,
            _StubRepo,
            _user,
        )

        repo = _StubRepo()
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        repo.bounds = (now - timedelta(days=10), now - timedelta(hours=3))
        repo.day_activity = {now.date() - timedelta(days=1): {9: 1}}
        service = _service_with(repo)
        seed = AsyncMock(return_value=0)
        with patch("src.domains.habits.service.seed_ledger_from_outcomes", seed):
            await service.recompute_user_profile(_user())
        seed.assert_awaited_once()
