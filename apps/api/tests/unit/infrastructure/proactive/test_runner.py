"""
Unit tests for infrastructure/proactive/runner.py.

Tests RunnerStats tracking, _process_user stats recording,
time-aware probabilistic logic, and elapsed hours calculation.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.infrastructure.proactive.eligibility import EligibilityChecker
from src.infrastructure.proactive.runner import ProactiveTaskRunner, RunnerStats

# ---------------------------------------------------------------------------
# RunnerStats unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunnerStats:
    """Tests for RunnerStats dataclass."""

    def test_initial_values(self):
        """Test that default values are all zero/empty."""
        stats = RunnerStats()
        assert stats.processed == 0
        assert stats.success == 0
        assert stats.failed == 0
        assert stats.skipped == 0
        assert stats.skip_reasons == {}
        assert stats.failure_reasons == {}

    def test_record_skip_increments_and_tracks_reason(self):
        """Test record_skip increments skipped and records reason."""
        stats = RunnerStats()
        stats.record_skip("feature_disabled")
        assert stats.skipped == 1
        assert stats.skip_reasons == {"feature_disabled": 1}

    def test_record_skip_accumulates_same_reason(self):
        """Test record_skip accumulates counts for the same reason."""
        stats = RunnerStats()
        stats.record_skip("probabilistic_skip")
        stats.record_skip("probabilistic_skip")
        stats.record_skip("no_target")
        assert stats.skipped == 3
        assert stats.skip_reasons == {"probabilistic_skip": 2, "no_target": 1}

    def test_record_failure_increments_and_tracks_reason(self):
        """Test record_failure increments failed and records reason."""
        stats = RunnerStats()
        stats.record_failure("content_generation_failed")
        assert stats.failed == 1
        assert stats.failure_reasons == {"content_generation_failed": 1}

    def test_record_failure_accumulates_same_reason(self):
        """Test record_failure accumulates counts for the same reason."""
        stats = RunnerStats()
        stats.record_failure("dispatch_failed")
        stats.record_failure("dispatch_failed")
        stats.record_failure("unexpected_exception")
        assert stats.failed == 3
        assert stats.failure_reasons == {"dispatch_failed": 2, "unexpected_exception": 1}

    def test_to_dict_includes_all_fields(self):
        """Test to_dict includes all fields including reasons."""
        stats = RunnerStats(processed=5, success=2, failed=1, skipped=2)
        stats.skip_reasons = {"no_target": 2}
        stats.failure_reasons = {"dispatch_failed": 1}
        stats.duration_seconds = 1.5678

        result = stats.to_dict()

        assert result["processed"] == 5
        assert result["success"] == 2
        assert result["failed"] == 1
        assert result["skipped"] == 2
        assert result["duration_seconds"] == 1.568
        assert result["skip_reasons"] == {"no_target": 2}
        assert result["failure_reasons"] == {"dispatch_failed": 1}

    def test_arithmetic_invariant(self):
        """Test that processed == success + skipped + failed."""
        stats = RunnerStats()
        stats.processed = 6
        stats.success = 2
        stats.record_skip("feature_disabled")
        stats.record_skip("probabilistic_skip")
        stats.record_failure("content_generation_failed")
        stats.record_failure("dispatch_failed")

        assert stats.processed == stats.success + stats.skipped + stats.failed


# ---------------------------------------------------------------------------
# _process_user stats recording tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _ledger_stays_out_of_reach():  # type: ignore[no-untyped-def]
    """No unit test in this module reaches a database.

    Delivering a notification now CLAIMS an action row (ADR-270), so the real
    ledger opens a session on every success path — including the ones written
    long before, which is exactly how a unit suite acquires an environment.
    The claim door answers None here: the wiring still runs for real, it simply
    writes nowhere.
    """
    with patch(
        "src.domains.agents.effects.runtime._LEDGER.claim",
        new=AsyncMock(return_value=None),
    ):
        yield


def _make_mock_user(**overrides: Any) -> MagicMock:
    """Create a mock user with default attributes."""
    user = MagicMock()
    user.id = overrides.get("id", uuid4())
    user.language = overrides.get("language", "fr")
    user.timezone = overrides.get("timezone", "Europe/Paris")
    user.interests_enabled = overrides.get("interests_enabled", True)
    user.interests_notify_start_hour = overrides.get("interests_notify_start_hour", 8)
    user.interests_notify_end_hour = overrides.get("interests_notify_end_hour", 22)
    user.interests_notify_min_per_day = overrides.get("interests_notify_min_per_day", 5)
    user.interests_notify_max_per_day = overrides.get("interests_notify_max_per_day", 10)
    user.is_verified = True
    return user


def _make_runner(
    eligibility_checker: Any = None,
    task: Any = None,
) -> ProactiveTaskRunner:
    """Create a ProactiveTaskRunner with mocked dependencies."""
    mock_task = task or MagicMock()
    mock_task.task_type = "interest"
    return ProactiveTaskRunner(
        task=mock_task,
        eligibility_checker=eligibility_checker,
    )


@pytest.mark.unit
class TestProcessUserStats:
    """Tests for _process_user stats recording."""

    @pytest.mark.asyncio
    async def test_eligibility_skip_records_reason(self):
        """Test that eligibility failure records skip with reason."""
        from src.infrastructure.proactive.eligibility import (
            EligibilityReason,
            EligibilityResult,
        )

        checker = AsyncMock()
        checker.check = AsyncMock(
            return_value=EligibilityResult(
                eligible=False,
                reason=EligibilityReason.OUTSIDE_TIME_WINDOW,
            )
        )

        runner = _make_runner(eligibility_checker=checker)
        stats = RunnerStats()
        user = _make_mock_user()
        db = AsyncMock()

        result = await runner._process_user(user, db, stats)

        assert result is False
        assert stats.skipped == 1
        assert stats.skip_reasons == {"outside_time_window": 1}
        assert stats.failed == 0

    @pytest.mark.asyncio
    async def test_probabilistic_skip_records_reason(self):
        """Test that probabilistic skip records correct reason."""
        from src.infrastructure.proactive.eligibility import EligibilityResult

        checker = AsyncMock()
        checker.check = AsyncMock(return_value=EligibilityResult.success())
        checker.should_send_notification = MagicMock(
            return_value=(False, {"decision": "probabilistic_skip", "probability": 0.02})
        )
        checker.notification_model = None
        checker.start_hour_field = "interests_notify_start_hour"
        checker.end_hour_field = "interests_notify_end_hour"

        runner = _make_runner(eligibility_checker=checker)
        stats = RunnerStats()
        user = _make_mock_user()
        db = AsyncMock()

        # Mock _get_today_notification_count
        runner._get_today_notification_count = AsyncMock(return_value=3)

        result = await runner._process_user(user, db, stats)

        assert result is False
        assert stats.skipped == 1
        assert stats.skip_reasons == {"probabilistic_skip": 1}

    @pytest.mark.asyncio
    async def test_task_eligibility_skip_records_reason(self):
        """Test that task eligibility failure records skip reason."""
        from src.infrastructure.proactive.eligibility import EligibilityResult

        checker = AsyncMock()
        checker.check = AsyncMock(return_value=EligibilityResult.success())
        checker.should_send_notification = MagicMock(return_value=(True, {"decision": "send"}))
        checker.notification_model = None
        checker.start_hour_field = "interests_notify_start_hour"
        checker.end_hour_field = "interests_notify_end_hour"

        mock_task = AsyncMock()
        mock_task.task_type = "interest"
        mock_task.check_eligibility = AsyncMock(return_value=False)

        runner = _make_runner(eligibility_checker=checker, task=mock_task)
        runner._get_today_notification_count = AsyncMock(return_value=0)
        stats = RunnerStats()
        user = _make_mock_user()
        db = AsyncMock()

        result = await runner._process_user(user, db, stats)

        assert result is False
        assert stats.skipped == 1
        assert stats.skip_reasons == {"task_eligibility_failed": 1}

    @pytest.mark.asyncio
    async def test_no_target_skip_records_reason(self):
        """Test that no target records skip reason."""
        from src.infrastructure.proactive.eligibility import EligibilityResult

        checker = AsyncMock()
        checker.check = AsyncMock(return_value=EligibilityResult.success())
        checker.should_send_notification = MagicMock(return_value=(True, {"decision": "send"}))
        checker.notification_model = None
        checker.start_hour_field = "interests_notify_start_hour"
        checker.end_hour_field = "interests_notify_end_hour"

        mock_task = AsyncMock()
        mock_task.task_type = "interest"
        mock_task.check_eligibility = AsyncMock(return_value=True)
        mock_task.select_target = AsyncMock(return_value=None)

        runner = _make_runner(eligibility_checker=checker, task=mock_task)
        runner._get_today_notification_count = AsyncMock(return_value=0)
        stats = RunnerStats()
        user = _make_mock_user()
        db = AsyncMock()

        result = await runner._process_user(user, db, stats)

        assert result is False
        assert stats.skipped == 1
        assert stats.skip_reasons == {"no_target": 1}

    @pytest.mark.asyncio
    async def test_content_generation_failure_records_reason(self):
        """Test that content generation failure records failure reason."""
        from src.infrastructure.proactive.eligibility import EligibilityResult

        checker = AsyncMock()
        checker.check = AsyncMock(return_value=EligibilityResult.success())
        checker.should_send_notification = MagicMock(return_value=(True, {"decision": "send"}))
        checker.notification_model = None
        checker.start_hour_field = "interests_notify_start_hour"
        checker.end_hour_field = "interests_notify_end_hour"

        @dataclass
        class FakeResult:
            success: bool = False
            content: str | None = None
            target_id: str | None = "interest-1"
            error: str | None = "generation failed"

        mock_task = AsyncMock()
        mock_task.task_type = "interest"
        mock_task.check_eligibility = AsyncMock(return_value=True)
        mock_task.select_target = AsyncMock(return_value=MagicMock())
        mock_task.generate_content = AsyncMock(return_value=FakeResult())

        runner = _make_runner(eligibility_checker=checker, task=mock_task)
        runner._get_today_notification_count = AsyncMock(return_value=0)
        stats = RunnerStats()
        user = _make_mock_user()
        db = AsyncMock()

        result = await runner._process_user(user, db, stats)

        assert result is False
        assert stats.failed == 1
        assert stats.failure_reasons == {"content_generation_failed": 1}

    @pytest.mark.asyncio
    async def test_dispatch_failure_records_reason(self):
        """Test that dispatch failure records failure reason."""
        from src.infrastructure.proactive.eligibility import EligibilityResult
        from src.infrastructure.proactive.notification import NotificationResult

        checker = AsyncMock()
        checker.check = AsyncMock(return_value=EligibilityResult.success())
        checker.should_send_notification = MagicMock(return_value=(True, {"decision": "send"}))
        checker.notification_model = None
        checker.start_hour_field = "interests_notify_start_hour"
        checker.end_hour_field = "interests_notify_end_hour"

        @dataclass
        class FakeTaskResult:
            success: bool = True
            content: str = "Test content"
            target_id: str = "interest-1"
            error: str | None = None
            model_name: str | None = None
            tokens_in: int = 0
            tokens_out: int = 0
            tokens_cache: int = 0
            metadata: dict = field(default_factory=dict)

        mock_task = AsyncMock()
        mock_task.task_type = "interest"
        mock_task.check_eligibility = AsyncMock(return_value=True)
        mock_task.select_target = AsyncMock(return_value=MagicMock())
        mock_task.generate_content = AsyncMock(return_value=FakeTaskResult())

        runner = _make_runner(eligibility_checker=checker, task=mock_task)
        runner._get_today_notification_count = AsyncMock(return_value=0)
        runner._dispatch_notification = AsyncMock(
            return_value=NotificationResult(success=False, error="FCM failed")
        )
        stats = RunnerStats()
        user = _make_mock_user()
        db = AsyncMock()

        result = await runner._process_user(user, db, stats)

        assert result is False
        assert stats.failed == 1
        assert stats.failure_reasons == {"dispatch_failed": 1}

    @pytest.mark.asyncio
    async def test_execute_exception_records_failure(self):
        """Test that unexpected exception in execute loop records failure."""
        checker = AsyncMock()
        checker.check = AsyncMock(side_effect=RuntimeError("boom"))

        mock_task = AsyncMock()
        mock_task.task_type = "interest"

        runner = _make_runner(eligibility_checker=checker, task=mock_task)

        user = _make_mock_user()
        stats = RunnerStats()

        # Simulate what execute() does for one user
        stats.processed += 1
        try:
            await runner._process_user(user, AsyncMock(), stats)
        except Exception:
            stats.record_failure("unexpected_exception")

        assert stats.failed == 1
        assert stats.failure_reasons == {"unexpected_exception": 1}


# ---------------------------------------------------------------------------
# should_send_notification time-aware algorithm tests
# ---------------------------------------------------------------------------


def _make_checker(**kwargs: Any) -> EligibilityChecker:
    """Create an EligibilityChecker with interest defaults."""
    return EligibilityChecker(
        task_type="interest",
        enabled_field="interests_enabled",
        start_hour_field="interests_notify_start_hour",
        end_hour_field="interests_notify_end_hour",
        min_per_day_field="interests_notify_min_per_day",
        max_per_day_field="interests_notify_max_per_day",
        **kwargs,
    )


@pytest.mark.unit
class TestShouldSendNotification:
    """Tests for the time-aware probabilistic algorithm."""

    def test_quota_reached_returns_false(self):
        """When today_count >= max_per_day, always returns False."""
        checker = _make_checker()
        user = _make_mock_user(interests_notify_min_per_day=2, interests_notify_max_per_day=5)

        result, info = checker.should_send_notification(
            user=user,
            today_count=5,
            window_hours=13,
            elapsed_hours=6.0,
        )

        assert result is False
        assert info["decision"] == "quota_reached"

    def test_guarantee_zone_forces_send_when_below_minimum(self):
        """In last 20% of window, if below min_per_day, forces True."""
        checker = _make_checker()
        user = _make_mock_user(interests_notify_min_per_day=2, interests_notify_max_per_day=5)

        # At 90% through window (remaining 10% < 20% threshold), 0 sent
        result, info = checker.should_send_notification(
            user=user,
            today_count=0,
            window_hours=13,
            elapsed_hours=11.7,
        )

        assert result is True
        assert info["decision"] == "guarantee_zone"

    def test_guarantee_zone_not_triggered_when_minimum_met(self):
        """Guarantee zone should NOT trigger when min_per_day already met."""
        checker = _make_checker()
        user = _make_mock_user(interests_notify_min_per_day=2, interests_notify_max_per_day=5)

        # At 90% through window, but already sent 3 (>= min 2)
        result, info = checker.should_send_notification(
            user=user,
            today_count=3,
            window_hours=13,
            elapsed_hours=11.7,
        )

        # Should NOT be in guarantee zone — probability might still trigger
        assert info["decision"] != "guarantee_zone"

    def test_probability_increases_as_window_progresses(self):
        """Probability should increase as more of the window elapses."""
        checker = _make_checker()
        user = _make_mock_user(interests_notify_min_per_day=2, interests_notify_max_per_day=5)

        _, info_early = checker.should_send_notification(
            user=user,
            today_count=0,
            window_hours=13,
            elapsed_hours=1.0,
        )
        _, info_late = checker.should_send_notification(
            user=user,
            today_count=0,
            window_hours=13,
            elapsed_hours=9.0,
        )

        # Late probability should be higher than early probability
        assert info_late["probability"] > info_early["probability"]

    def test_deficit_boost_increases_probability(self):
        """When behind schedule, probability should be boosted."""
        checker = _make_checker()
        user = _make_mock_user(interests_notify_min_per_day=2, interests_notify_max_per_day=5)

        # At 50% through window with target ~3.5, expected ~1.75 by now
        # 0 sent → behind schedule
        _, info_behind = checker.should_send_notification(
            user=user,
            today_count=0,
            window_hours=13,
            elapsed_hours=6.5,
        )
        # 2 sent → closer to expected
        _, info_on_track = checker.should_send_notification(
            user=user,
            today_count=2,
            window_hours=13,
            elapsed_hours=6.5,
        )

        assert info_behind["probability"] > info_on_track["probability"]

    def test_zero_window_hours_returns_false(self):
        """Edge case: zero or negative window hours should safely return False."""
        checker = _make_checker()
        user = _make_mock_user()

        result, info = checker.should_send_notification(
            user=user,
            today_count=0,
            window_hours=0,
            elapsed_hours=0.0,
        )

        assert result is False
        assert info["decision"] == "invalid_window"

    def test_returns_debug_info_with_key_values(self):
        """Verify debug_info contains all expected diagnostic fields."""
        checker = _make_checker()
        user = _make_mock_user(interests_notify_min_per_day=2, interests_notify_max_per_day=5)

        _, info = checker.should_send_notification(
            user=user,
            today_count=0,
            window_hours=13,
            elapsed_hours=5.0,
        )

        assert "min_per_day" in info
        assert "max_per_day" in info
        assert "probability" in info
        assert "time_fraction" in info
        assert "decision" in info


# ---------------------------------------------------------------------------
# _calculate_elapsed_hours tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCalculateElapsedHours:
    """Tests for _calculate_elapsed_hours static method."""

    def test_middle_of_window(self):
        """At hour 15 with start_hour 9, elapsed should be 6."""
        user = _make_mock_user(timezone="Europe/Paris")
        # 14:00 UTC = 15:00 CET (winter)
        now = datetime(2026, 3, 2, 14, 0, tzinfo=UTC)

        elapsed = ProactiveTaskRunner._calculate_elapsed_hours(
            user=user,
            now=now,
            start_hour=9,
            window_hours=13,
        )

        assert 5.5 < elapsed < 6.5  # ~6h elapsed

    def test_start_of_window(self):
        """At window start, elapsed should be ~0."""
        user = _make_mock_user(timezone="Europe/Paris")
        # 08:00 UTC = 09:00 CET (winter) = start of window
        now = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)

        elapsed = ProactiveTaskRunner._calculate_elapsed_hours(
            user=user,
            now=now,
            start_hour=9,
            window_hours=13,
        )

        assert elapsed < 0.5

    def test_end_of_window(self):
        """At window end, elapsed should be clamped to window_hours."""
        user = _make_mock_user(timezone="Europe/Paris")
        # 21:30 UTC = 22:30 CET — past end of 9-22 window
        now = datetime(2026, 3, 2, 21, 30, tzinfo=UTC)

        elapsed = ProactiveTaskRunner._calculate_elapsed_hours(
            user=user,
            now=now,
            start_hour=9,
            window_hours=13,
        )

        assert elapsed == 13.0  # Clamped to window_hours

    def test_utc_timezone_fallback(self):
        """Users without timezone should default to UTC."""
        user = _make_mock_user(timezone="UTC")
        now = datetime(2026, 3, 2, 12, 30, tzinfo=UTC)

        elapsed = ProactiveTaskRunner._calculate_elapsed_hours(
            user=user,
            now=now,
            start_hour=9,
            window_hours=13,
        )

        assert 3.0 < elapsed < 4.0  # ~3.5h elapsed


@pytest.mark.unit
class TestWakeGateBypass:
    """ADR-261: a push wake skips ONLY the probabilistic smoothing — the hard
    eligibility check still runs first and still refuses."""

    @pytest.mark.asyncio
    async def test_skip_probabilistic_gate_never_consults_should_send(self):
        from src.infrastructure.proactive.eligibility import EligibilityResult

        checker = AsyncMock()
        checker.check = AsyncMock(return_value=EligibilityResult.success())
        checker.should_send_notification = MagicMock(return_value=(False, {}))
        checker.notification_model = None
        checker.start_hour_field = "interests_notify_start_hour"
        checker.end_hour_field = "interests_notify_end_hour"
        task = MagicMock()
        task.task_type = "heartbeat"
        task.check_eligibility = AsyncMock(return_value=False)  # stop right after the gate
        runner = ProactiveTaskRunner(
            task=task, eligibility_checker=checker, skip_probabilistic_gate=True
        )
        runner._get_today_notification_count = AsyncMock(return_value=3)
        stats = RunnerStats()

        result = await runner._process_user(_make_mock_user(), AsyncMock(), stats)

        assert result is False
        checker.check.assert_awaited_once()
        checker.should_send_notification.assert_not_called()
        task.check_eligibility.assert_awaited_once()
        assert "probabilistic_skip" not in stats.skip_reasons

    @pytest.mark.asyncio
    async def test_hard_eligibility_still_refuses_a_wake(self):
        from src.infrastructure.proactive.eligibility import (
            EligibilityReason,
            EligibilityResult,
        )

        checker = AsyncMock()
        checker.check = AsyncMock(
            return_value=EligibilityResult(
                eligible=False, reason=EligibilityReason.OUTSIDE_TIME_WINDOW
            )
        )
        task = MagicMock()
        task.task_type = "heartbeat"
        runner = ProactiveTaskRunner(
            task=task, eligibility_checker=checker, skip_probabilistic_gate=True
        )
        stats = RunnerStats()
        assert await runner._process_user(_make_mock_user(), AsyncMock(), stats) is False
        assert stats.skip_reasons == {"outside_time_window": 1}


@pytest.mark.unit
class TestTheSuccessPathIsAccountedAndRecorded:
    """The one path where a sweep spends, and the one nothing exercised.

    Every existing test of ``_process_user`` stops at a skip or a failure, so
    the branch that bills the account, publishes the consultation collector and
    files the turn in the decision register ran in no test at all — measured
    2026-09-07, and it is exactly the wiring that was found missing in
    production (824 sweeps, no consultation row).

    A helper covered by a test whose caller is not is the same green-by-absence
    trap the register itself was built to end.
    """

    @staticmethod
    def _no_register():  # type: ignore[no-untyped-def]
        """Keep the consultation flush off any database.

        The subject here is « the collector was published and collected the
        row », never « the write succeeded ». Stubbing the write keeps the test
        hermetic and avoids the coroutine a fake session synthesises on every
        nested attribute access (F028).
        """
        return patch(
            "src.domains.agents.effects.treatment_recorder._flush",
            new=AsyncMock(),
        )

    @staticmethod
    def _successful_runner(task_type: str = "interest") -> Any:
        from src.infrastructure.proactive.eligibility import EligibilityResult
        from src.infrastructure.proactive.notification import NotificationResult

        checker = AsyncMock()
        checker.check = AsyncMock(return_value=EligibilityResult.success())
        checker.should_send_notification = MagicMock(return_value=(True, {"decision": "send"}))
        checker.notification_model = None
        checker.start_hour_field = "interests_notify_start_hour"
        checker.end_hour_field = "interests_notify_end_hour"

        @dataclass
        class FakeTaskResult:
            success: bool = True
            content: str = "Test content"
            target_id: str = "interest-1"
            error: str | None = None
            model_name: str | None = "gpt-test"
            tokens_in: int = 120
            tokens_out: int = 30
            tokens_cache: int = 0
            metadata: dict = field(default_factory=dict)
            source_name: str = "test-source"
            total_tokens: int = 150

        mock_task = AsyncMock()
        mock_task.task_type = task_type
        mock_task.check_eligibility = AsyncMock(return_value=True)
        mock_task.select_target = AsyncMock(return_value=MagicMock())
        mock_task.generate_content = AsyncMock(return_value=FakeTaskResult())

        runner = _make_runner(eligibility_checker=checker, task=mock_task)
        runner._get_today_notification_count = AsyncMock(return_value=0)
        runner._dispatch_notification = AsyncMock(
            return_value=NotificationResult(success=True, fcm_success=1, sse_sent=True)
        )
        return runner

    @pytest.mark.asyncio
    async def test_a_delivered_sweep_bills_the_account_it_served(self) -> None:
        runner = self._successful_runner()
        user = _make_mock_user()

        with patch(
            "src.infrastructure.proactive.runner.track_proactive_tokens",
            new=AsyncMock(return_value="run-x"),
        ) as tracked:
            assert await runner._process_user(user, AsyncMock(), RunnerStats()) is True

        assert tracked.await_count == 1
        call = tracked.await_args.kwargs
        assert call["user_id"] == user.id
        assert call["tokens_in"] == 120
        assert call["tokens_out"] == 30
        assert call["model_name"] == "gpt-test"

    @pytest.mark.asyncio
    async def test_a_sweep_is_filed_as_lias_own_initiative(self) -> None:
        """Nobody asked for it. Filing it as the person's would hide it in
        the list of things they set in motion themselves."""
        runner = self._successful_runner()

        with patch(
            "src.infrastructure.proactive.runner.track_proactive_tokens",
            new=AsyncMock(return_value="run-x"),
        ) as tracked:
            await runner._process_user(_make_mock_user(), AsyncMock(), RunnerStats())

        assert tracked.await_args.kwargs["source"] == "proactive"

    @pytest.mark.asyncio
    async def test_the_run_id_is_minted_before_the_content_and_shared(self) -> None:
        """The collector is published around ``generate_content``, so the id
        must exist before it — a tracker that minted its own would file the
        consultations under a run the register never joins."""
        runner = self._successful_runner()

        with patch(
            "src.infrastructure.proactive.runner.track_proactive_tokens",
            new=AsyncMock(return_value="run-x"),
        ) as tracked:
            await runner._process_user(_make_mock_user(), AsyncMock(), RunnerStats())

        passed = tracked.await_args.kwargs["run_id"]
        assert passed, "no run id reached the tracker"
        assert isinstance(passed, str)

    @pytest.mark.asyncio
    async def test_the_sources_opened_during_the_sweep_are_collected(self) -> None:
        """The collector must be live while the task generates its content."""
        from src.domains.agents.effects.treatments import collected_treatments
        from src.domains.shared.consultation_surfaces import record_surface_consultations

        runner = self._successful_runner("heartbeat")
        seen: list[int] = []

        original = runner.task.generate_content

        async def _generate(*args: Any, **kwargs: Any) -> Any:
            record_surface_consultations(
                surface="heartbeat",
                user_id="11111111-1111-1111-1111-111111111111",
                opened=["emails"],
                duration_ms=5,
            )
            seen.append(len(collected_treatments()))
            return await original(*args, **kwargs)

        runner.task.generate_content = _generate

        with (
            patch(
                "src.infrastructure.proactive.runner.track_proactive_tokens",
                new=AsyncMock(return_value="run-x"),
            ),
            self._no_register(),
        ):
            await runner._process_user(_make_mock_user(), AsyncMock(), RunnerStats())

        assert seen == [1], "the runner published no collector around generate_content"

    @pytest.mark.asyncio
    async def test_a_delivered_notification_is_recorded_as_an_ACTION(self) -> None:
        """The gap reported from production, 2026-09-07.

        Sending a notification is an act LIA decided on alone, and it left no
        row in the action register at all — so « Actions menées d'elle-même »
        was empty by construction whatever LIA did. The helper is tested next
        door; this asserts the RUNNER reaches it, which is the half that was
        missing.
        """
        runner = self._successful_runner()
        claimed: list[dict] = []

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _spy(**kwargs):  # type: ignore[no-untyped-def]
            claimed.append(kwargs)
            from src.domains.agents.effects.out_of_turn_effects import ProactiveEffect

            effect = ProactiveEffect()
            yield effect
            claimed[-1]["delivered"] = effect.delivered

        with (
            patch(
                "src.infrastructure.proactive.runner.track_proactive_tokens",
                new=AsyncMock(return_value="run-x"),
            ),
            patch(
                "src.domains.agents.effects.out_of_turn_effects.proactive_notification_effect",
                _spy,
            ),
        ):
            user = _make_mock_user()
            await runner._process_user(user, AsyncMock(), RunnerStats())

        assert len(claimed) == 1, "the notification claimed no action row"
        assert claimed[0]["user_id"] == user.id
        assert claimed[0]["task_type"] == "interest"
        assert claimed[0]["delivered"] is True

    @pytest.mark.asyncio
    async def test_a_notification_nobody_received_is_not_recorded_as_done(self) -> None:
        """Settled from the dispatch's explicit result, never from silence."""
        from contextlib import asynccontextmanager

        from src.infrastructure.proactive.notification import NotificationResult

        runner = self._successful_runner()
        runner._dispatch_notification = AsyncMock(
            return_value=NotificationResult(success=False, error="FCM failed")
        )
        seen: list[bool] = []

        @asynccontextmanager
        async def _spy(**_kwargs):  # type: ignore[no-untyped-def]
            from src.domains.agents.effects.out_of_turn_effects import ProactiveEffect

            effect = ProactiveEffect()
            yield effect
            seen.append(effect.delivered)

        with (
            patch(
                "src.infrastructure.proactive.runner.track_proactive_tokens",
                new=AsyncMock(return_value="run-x"),
            ),
            patch(
                "src.domains.agents.effects.out_of_turn_effects.proactive_notification_effect",
                _spy,
            ),
        ):
            await runner._process_user(_make_mock_user(), AsyncMock(), RunnerStats())

        assert seen == [False]

    @pytest.mark.asyncio
    async def test_a_tracking_failure_never_loses_a_delivered_notification(self) -> None:
        """The notification is already sent; the accounting must not undo it.

        The protection lives INSIDE ``track_proactive_tokens`` rather than at
        this call site — one place, so every caller inherits it. Asserted on
        the real function, because a test that patched the seam would prove
        only that the patch was applied.
        """
        from src.infrastructure.proactive.tracking import track_proactive_tokens

        with patch(
            "src.domains.chat.service.TrackingContext",
            side_effect=RuntimeError("ledger down"),
        ):
            recorded = await track_proactive_tokens(
                user_id=uuid4(),
                task_type="interest",
                target_id="interest-1",
                conversation_id=None,
                tokens_in=10,
                tokens_out=2,
                model_name="gpt-test",
                source="proactive",
            )

        assert recorded is None, "a failed ledger must report nothing, never raise"

    @pytest.mark.asyncio
    async def test_a_model_that_cannot_be_priced_still_records_its_tokens(self) -> None:
        """An unpriced call is still a call; dropping it loses the tokens too."""
        from src.infrastructure.proactive.tracking import track_proactive_tokens

        with (
            patch(
                "src.infrastructure.cache.pricing_cache.get_cached_cost_usd_eur",
                side_effect=RuntimeError("no price for this model"),
            ),
            patch(
                "src.domains.chat.service.TrackingContext",
                side_effect=RuntimeError("stop before the write"),
            ),
        ):
            assert (
                await track_proactive_tokens(
                    user_id=uuid4(),
                    task_type="interest",
                    target_id="interest-1",
                    conversation_id=None,
                    tokens_in=10,
                    tokens_out=2,
                    model_name="a-model-nobody-prices",
                    source="proactive",
                )
                is None
            )
