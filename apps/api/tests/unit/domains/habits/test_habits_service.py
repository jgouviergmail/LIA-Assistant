"""Unit tests for HabitsService orchestration (ADR-214).

The detector is covered table-driven in ``test_rhythm_detector.py``; here we
pin the ORCHESTRATION contract: delta-skip semantics (an abandoned account
must still decay its claims), window→habit-row sync with stable part-of-day
identity, blocked-key respect, and the no-activity short-circuit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.habits.models import HabitKind
from src.domains.habits.rhythm import PROFILE_PAYLOAD_VERSION
from src.domains.habits.service import HabitsService, part_of_day


class _StubRepo:
    """In-memory repository double capturing every call."""

    def __init__(self) -> None:
        self.bounds: tuple[datetime | None, datetime | None] = (None, None)
        self.profile: Any = None
        self.day_activity: dict = {}
        self.upserted_profiles: list[dict[str, Any]] = []
        self.upserted_habits: list[dict[str, Any]] = []
        self.stale_calls: list[tuple[str, set[str]]] = []
        self.rollup: dict = {}
        self.run_activity: dict = {}
        self.reset_activity: dict = {}
        self.upserted_rollup: dict | None = None
        self.pruned = False

    async def fetch_activity_bounds(self, user_id):  # noqa: ANN001, ANN201
        return self.bounds

    async def get_profile(self, user_id):  # noqa: ANN001, ANN201
        return self.profile

    async def fetch_day_activity(self, user_id, tz, since):  # noqa: ANN001, ANN201
        return dict(self.day_activity)

    async def upsert_profile(self, **kwargs):  # noqa: ANN003, ANN201
        self.upserted_profiles.append(kwargs)

    async def fetch_activity_rollup(self, user_id):  # noqa: ANN001, ANN201
        return dict(self.rollup)

    async def fetch_run_activity(self, user_id, tz, since):  # noqa: ANN001, ANN201
        return dict(self.run_activity)

    async def fetch_reset_activity(self, user_id, tz, since):  # noqa: ANN001, ANN201
        return dict(self.reset_activity)

    async def upsert_activity_days(self, user_id, days):  # noqa: ANN001, ANN201
        self.upserted_rollup = dict(days)

    async def prune_activity_days(self, user_id, keep_after):  # noqa: ANN001, ANN201
        self.pruned = True

    async def upsert_habit(self, **kwargs):  # noqa: ANN003, ANN201
        self.upserted_habits.append(kwargs)
        return "created"

    async def remove_stale_active_habits(self, user_id, kind, live_keys):  # noqa: ANN001, ANN201
        self.stale_calls.append((kind, set(live_keys)))
        return 0


def _service_with(repo: _StubRepo) -> HabitsService:
    service = HabitsService.__new__(HabitsService)
    service.db = MagicMock()
    service.repository = repo  # type: ignore[assignment]
    return service


def _user(tz: str = "Europe/Paris") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.timezone = tz
    return user


def _regular_days() -> dict:
    """56 days of a two-peak weekday + weekend-morning routine."""
    from datetime import date

    today = datetime.now(UTC).date()
    days: dict[date, dict[int, int]] = {}
    for k in range(1, 60):
        d = today - timedelta(days=k)
        if d.weekday() < 5:
            days[d] = {8: 2, 9: 1, 21: 3}
        else:
            days[d] = {10: 3}
    return days


@pytest.mark.unit
class TestRecompute:
    async def test_no_activity_short_circuits(self) -> None:
        repo = _StubRepo()
        service = _service_with(repo)
        outcome = await service.recompute_user_profile(_user())
        assert outcome == "skipped_no_activity"
        assert repo.upserted_profiles == []

    async def test_computes_and_syncs_window_habits(self) -> None:
        repo = _StubRepo()
        now = datetime.now(UTC)
        repo.bounds = (now - timedelta(days=100), now - timedelta(hours=3))
        repo.day_activity = _regular_days()
        service = _service_with(repo)

        outcome = await service.recompute_user_profile(_user())

        assert outcome == "computed"
        assert len(repo.upserted_profiles) == 1
        payload = repo.upserted_profiles[0]["payload"]
        assert payload["version"] == PROFILE_PAYLOAD_VERSION
        assert payload["classes"]["weekday"]["verdict"] == "windows"

        keys = {h["key"] for h in repo.upserted_habits}
        # Stable part-of-day identity, never exact hours.
        assert "weekday:morning" in keys
        assert "weekday:evening" in keys
        assert "weekend:morning" in keys
        assert all(h["kind"] == HabitKind.ACTIVE_WINDOW.value for h in repo.upserted_habits)
        # Stale active rows outside the live keys are removed.
        assert repo.stale_calls == [(HabitKind.ACTIVE_WINDOW.value, keys)]

    async def test_delta_skip_only_when_nothing_left_to_decay(self) -> None:
        """No new messages + no claimed windows → skip; claimed windows →
        MUST recompute (an abandoned account may not keep stale claims)."""
        repo = _StubRepo()
        last = datetime.now(UTC) - timedelta(days=10)
        repo.bounds = (last - timedelta(days=90), last)

        profile_row = MagicMock()
        profile_row.source_max_created_at = last
        profile_row.payload = {
            "version": PROFILE_PAYLOAD_VERSION,
            "active_days_fraction": 0.1,
            "sparse": True,
            "classes": {
                "weekday": {
                    "verdict": "sparse",
                    "windows": [],
                    "n_eff": 0.0,
                    "bin_presence": [0.0] * 24,
                },
                "weekend": {
                    "verdict": "sparse",
                    "windows": [],
                    "n_eff": 0.0,
                    "bin_presence": [0.0] * 24,
                },
            },
        }
        repo.profile = profile_row
        repo.day_activity = {datetime.now(UTC).date() - timedelta(days=3): {9: 2}}
        service = _service_with(repo)
        assert await service.recompute_user_profile(_user()) == "skipped_no_delta"
        # The durability invariant is UNCONDITIONAL: even a skipped recompute
        # feeds the rollup first — otherwise a reset arriving before the next
        # "computed" run would erase days the rollup never saw (live-proof
        # regression, owner account 2026-08-05).
        assert repo.upserted_rollup is not None
        assert repo.pruned is True

        # Same staleness but a window is still claimed → recompute runs.
        profile_row.payload = {
            **profile_row.payload,
            "classes": {
                **profile_row.payload["classes"],
                "weekday": {
                    "verdict": "windows",
                    "windows": [{"start_hour": 8, "end_hour": 10, "presence": 0.9}],
                    "n_eff": 20.0,
                    "bin_presence": [0.0] * 24,
                },
            },
        }
        assert await service.recompute_user_profile(_user()) == "computed"
        assert len(repo.upserted_profiles) == 1


@pytest.mark.unit
class TestPartOfDay:
    @pytest.mark.parametrize(
        ("hour", "expected"),
        [
            (4.9, "night"),
            (5.0, "morning"),
            (11.9, "morning"),
            (12.0, "afternoon"),
            (16.9, "afternoon"),
            (17.0, "evening"),
            (21.9, "evening"),
            (22.0, "night"),
            (23.5, "night"),
            (0.0, "night"),
        ],
    )
    def test_parts_cover_the_circle(self, hour: float, expected: str) -> None:
        assert part_of_day(hour) == expected


@pytest.mark.unit
class TestRepositoryUpsertHabit:
    """The status contract of upsert_habit (stubbed session)."""

    def _repo_with_row(self, row: Any):  # noqa: ANN201
        from src.domains.habits.repository import HabitsRepository

        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = row
        db.execute = AsyncMock(return_value=result)
        db.add = MagicMock()
        return HabitsRepository(db), db

    async def test_blocked_row_is_never_touched(self) -> None:
        row = MagicMock()
        row.status = "blocked"
        row.payload = {"old": True}
        repo, _db = self._repo_with_row(row)
        outcome = await repo.upsert_habit(
            user_id=uuid.uuid4(),
            kind="active_window",
            key="weekday:morning",
            payload={"new": True},
            last_observed_at=datetime.now(UTC),
        )
        assert outcome == "blocked"
        assert row.payload == {"old": True}

    async def test_existing_row_updated_with_new_dict(self) -> None:
        row = MagicMock()
        row.status = "paused"
        original_payload = {"old": True}
        row.payload = original_payload
        repo, _db = self._repo_with_row(row)
        new_payload = {"new": True}
        outcome = await repo.upsert_habit(
            user_id=uuid.uuid4(),
            kind="active_window",
            key="weekday:morning",
            payload=new_payload,
            last_observed_at=datetime.now(UTC),
        )
        assert outcome == "updated"
        # JSONB rule: a NEW dict object, never the same reference mutated.
        assert row.payload == {"new": True}
        assert row.payload is not new_payload
        assert row.muted_until_reproof is False

    async def test_missing_row_created(self) -> None:
        repo, db = self._repo_with_row(None)
        outcome = await repo.upsert_habit(
            user_id=uuid.uuid4(),
            kind="active_window",
            key="weekend:morning",
            payload={"v": 1},
            last_observed_at=datetime.now(UTC),
        )
        assert outcome == "created"
        db.add.assert_called_once()


@pytest.mark.unit
class TestActivityRollup:
    """The rhythm source must survive conversation resets (owner forensics
    2026-08-05: 961 resets on the primary account — each one deletes the
    messages, so raw conversation_messages is NOT a durable activity source).
    The per-day rollup is merged with MAX per hour: a reset can only shrink
    the live counts, so max preserves the pre-reset truth."""

    def test_merge_max_preserves_pre_reset_days(self) -> None:
        from datetime import date

        from src.domains.habits.service import merge_activity_days

        rollup = {date(2026, 8, 1): {8: 3, 21: 2}, date(2026, 8, 2): {9: 1}}
        # After a reset, day 1 vanished from live and day 2 shrank; day 3 is new.
        live = {date(2026, 8, 2): {9: 0, 10: 2}, date(2026, 8, 3): {8: 1}}
        merged = merge_activity_days(rollup, live)
        assert merged[date(2026, 8, 1)] == {8: 3, 21: 2}  # survived the reset
        assert merged[date(2026, 8, 2)] == {9: 1, 10: 2}  # per-hour max
        assert merged[date(2026, 8, 3)] == {8: 1}

    async def test_recompute_feeds_and_reads_the_rollup(self) -> None:

        repo = _StubRepo()
        now = datetime.now(UTC)
        repo.bounds = (now - timedelta(days=2), now - timedelta(hours=3))
        # Live source: only 2 recent days (post-reset)…
        today = now.date()
        repo.day_activity = {
            today - timedelta(days=1): {8: 2, 21: 3},
            today - timedelta(days=2): {8: 2, 21: 3},
        }
        # …but the rollup remembers 8 weeks of the same routine.
        repo.rollup = {}
        for k in range(1, 57):
            day = today - timedelta(days=k)
            repo.rollup[day] = {8: 2, 21: 3} if day.weekday() < 5 else {10: 3}
        service = _service_with(repo)

        outcome = await service.recompute_user_profile(_user())

        assert outcome == "computed"
        # The rollup was persisted (merged) and pruned.
        assert repo.upserted_rollup is not None
        assert repo.pruned is True
        # The profile computed from the ROLLUP, not the 2 surviving days:
        # weekday windows exist despite the reset.
        payload = repo.upserted_profiles[0]["payload"]
        assert payload["classes"]["weekday"]["verdict"] == "windows"


@pytest.mark.unit
class TestDurableRunSource:
    """The token summaries are the RETROACTIVE rhythm source (ADR-214, owner
    finding 2026-08-05): conversation messages die on reset, the summaries
    do not. The service unions live messages ∪ durable runs ∪ rollup with
    per-hour MAX — the same event seen through two sources never counts
    twice beyond the max."""

    async def test_run_source_restores_days_the_reset_destroyed(self) -> None:

        repo = _StubRepo()
        now = datetime.now(UTC)
        today = now.date()
        repo.bounds = (now - timedelta(days=60), now - timedelta(hours=3))
        # Live messages: only 2 post-reset days survive…
        repo.day_activity = {
            today - timedelta(days=1): {8: 2, 21: 3},
            today - timedelta(days=2): {8: 2, 21: 3},
        }
        # …but the durable summaries remember 8 weeks of the same routine.
        repo.run_activity = {}
        for k in range(1, 57):
            day = today - timedelta(days=k)
            repo.run_activity[day] = {8: 2, 21: 3} if day.weekday() < 5 else {10: 3}
        service = _service_with(repo)

        outcome = await service.recompute_user_profile(_user())

        assert outcome == "computed"
        payload = repo.upserted_profiles[0]["payload"]
        # The reset destroyed the messages, not the rhythm: windows exist.
        assert payload["classes"]["weekday"]["verdict"] == "windows"

    async def test_overlapping_sources_never_double_count(self) -> None:
        from datetime import date

        from src.domains.habits.service import merge_activity_days

        d = date(2026, 8, 3)
        # The same 2 events at 08h seen as messages AND as run summaries.
        merged = merge_activity_days({d: {8: 2}}, {d: {8: 2}})
        assert merged[d] == {8: 2}  # max, not sum


@pytest.mark.unit
class TestResetPresenceSource:
    """Conversation resets are a presence source (ADR-214 amendment, prod
    forensics 2026-08-05): the primary account showed 124 distinct reset
    days against ≤4 days through messages/summaries — for a reset-heavy
    user the audit trail IS the durable trace, and without it the profile
    reads SPARSE for someone who is present nearly every day."""

    async def test_reset_source_turns_an_empty_profile_into_a_measured_one(self) -> None:
        repo = _StubRepo()
        now = datetime.now(UTC)
        today = now.date()
        repo.bounds = (now - timedelta(days=60), now - timedelta(hours=3))
        # Messages and summaries: nothing (every conversation was reset,
        # human runs predate the summary retention) …
        repo.day_activity = {}
        repo.run_activity = {}
        # …but the reset audit trail shows a steady evening routine.
        repo.reset_activity = {}
        for k in range(1, 57):
            day = today - timedelta(days=k)
            repo.reset_activity[day] = {21: 2, 22: 1} if day.weekday() < 5 else {10: 1}
        service = _service_with(repo)

        outcome = await service.recompute_user_profile(_user())

        assert outcome == "computed"
        payload = repo.upserted_profiles[0]["payload"]
        assert payload["classes"]["weekday"]["verdict"] == "windows"

    async def test_force_bypasses_the_delta_skip(self) -> None:
        """The manual /recompute must never be a silent no-op (live-proof
        catch 2026-08-05): adding a source extends history BACKWARD, which
        the last_at delta cannot see — the user's 'recompute now' forces
        the detector pass, the nightly job keeps the skip economy."""
        from src.domains.habits.rhythm import RhythmProfile

        repo = _StubRepo()
        now = datetime.now(UTC)
        today = now.date()
        repo.bounds = (now - timedelta(days=60), now - timedelta(hours=3))
        repo.reset_activity = {
            today
            - timedelta(days=k): {21: 2} if (today - timedelta(days=k)).weekday() < 5 else {10: 1}
            for k in range(1, 57)
        }
        # Stored profile already covers last_at, with no windows to decay:
        # the nightly path would skip.
        empty_payload = RhythmProfile.from_payload({}).to_payload()
        stored = MagicMock()
        stored.payload = empty_payload
        stored.source_max_created_at = now  # newer than bounds last_at
        repo.profile = stored
        service = _service_with(repo)

        assert await service.recompute_user_profile(_user()) == "skipped_no_delta"
        assert await service.recompute_user_profile(_user(), force=True) == "computed"
        assert repo.upserted_profiles  # the detector actually ran

    async def test_three_way_union_is_per_hour_max(self) -> None:
        from datetime import date

        from src.domains.habits.service import merge_activity_days

        d = date(2026, 8, 3)
        # One human run seen as message AND summary AND followed by a reset
        # in the same hour: the union must read max, never 3.
        union = merge_activity_days({d: {8: 1}}, merge_activity_days({d: {8: 1}}, {d: {8: 1}}))
        assert union[d] == {8: 1}
