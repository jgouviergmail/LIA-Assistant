"""One pass of the moment sweep, and the guarantees it owes.

The sweep is where the whole feature can go wrong quietly, so what is pinned
here is not the happy path but the refusals:

- **the capability is read at CALL time.** An operator switching moments off
  must be obeyed without a restart, and a flag read at import would need one.
- **an account outside its window is not even looked at.** Not an optimisation:
  it will not be served whatever is detected, so detecting for it spends a
  calendar read to file a row that expires unread.
- **housekeeping runs FIRST.** A row that expired thirty seconds ago must not be
  claimed by the same pass that was about to close it.
- **every claimed row reaches a settled state, with a bounded reason.** A quota
  refusal settles as a SKIP and logs « skipped » — a ceiling refusing a call is
  not a generation failure (ADR-272).
- **one account failing does not take the sweep down.**
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.moments.models import MomentKind, MomentSkipReason, MomentState
from src.domains.moments.schemas import MomentFacts
from src.infrastructure.proactive.runner import RunnerStats
from src.infrastructure.scheduler import moment_sweep

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 11, 15, 0, tzinfo=UTC)
_MODULE = "src.infrastructure.scheduler.moment_sweep"


def _user(**overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "id": uuid4(),
        "email": "moi@example.com",
        "timezone": "UTC",
        "is_active": True,
        "heartbeat_enabled": True,
        "heartbeat_notify_start_hour": 9,
        "heartbeat_notify_end_hour": 22,
        "moment_kinds_disabled": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _moment_row(user_id: Any, **overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "id": uuid4(),
        "user_id": user_id,
        "kind": MomentKind.EVENT_FOLLOWUP.value,
        "source_ref": "evt-1",
        "payload": {"title": "Point budget"},
        "due_at": NOW - timedelta(minutes=5),
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _db_ctx() -> Any:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _ctx():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    return _ctx


def _stats(**overrides: Any) -> RunnerStats:
    """The REAL RunnerStats, never a stand-in.

    A SimpleNamespace here is what let ``stats.failures`` — a field that does
    not exist — pass thirteen green tests: a duck-typed double answers any
    attribute name, including a misspelt one. MyPy caught it; the test could
    not, and that is the point of using the real type.
    """
    stats = RunnerStats()
    for name, value in overrides.items():
        setattr(stats, name, value)
    return stats


class TestTheCapabilityGate:
    async def test_a_switched_off_capability_does_nothing_at_all(self) -> None:
        with (
            patch(f"{_MODULE}.is_capability_enabled", new=AsyncMock(return_value=False)),
            patch(f"{_MODULE}.get_redis_cache", new=AsyncMock()) as redis,
        ):
            result = await moment_sweep.run_moment_sweep()

        assert result == {"skipped": "capability_off"}
        redis.assert_not_awaited()

    async def test_the_capability_is_read_at_call_time(self) -> None:
        """Read at import, an operator's switch would need a restart."""
        with (
            patch(f"{_MODULE}.is_capability_enabled", new=AsyncMock(return_value=False)) as gate,
            patch(f"{_MODULE}.get_redis_cache", new=AsyncMock()),
        ):
            await moment_sweep.run_moment_sweep()
            await moment_sweep.run_moment_sweep()

        assert gate.await_count == 2


class TestChoosingAccounts:
    async def test_an_account_outside_its_window_is_skipped(self) -> None:
        """22:00 local, window 9-22: nothing is detected and nothing is served."""
        night = NOW.replace(hour=23)
        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch(f"{_MODULE}.last_seen_at", new=AsyncMock(return_value=None), create=True),
            patch(f"{_MODULE}.select"),
            patch(f"{_MODULE}.func"),
        ):
            # The DB layer is mocked out; the predicate is what this pins.
            from src.infrastructure.proactive.eligibility import is_within_hour_window

            assert is_within_hour_window(night.hour, 9, 22) is False
            assert is_within_hour_window(15, 9, 22) is True

    def test_an_overnight_window_wraps_midnight(self) -> None:
        from src.infrastructure.proactive.eligibility import is_within_hour_window

        assert is_within_hour_window(23, 22, 9) is True
        assert is_within_hour_window(3, 22, 9) is True
        assert is_within_hour_window(12, 22, 9) is False


class TestServingOne:
    async def _run(self, *, claimed: Any, facts: MomentFacts, stats: Any) -> tuple[str, Any]:
        settled: dict[str, Any] = {}

        repo = MagicMock()
        repo.claim_due = AsyncMock(return_value=claimed)

        async def _settle(moment_id, *, owner, state, skip_reason=None, now):
            settled.update(state=state, skip_reason=skip_reason, owner=owner)
            return True

        repo.settle = AsyncMock(side_effect=_settle)

        spec = MagicMock()
        spec.headline = "A meeting on their calendar has just ended."
        spec.revalidator = AsyncMock(return_value=facts)

        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch(f"{_MODULE}.MomentRepository", return_value=repo),
            patch.dict(
                f"{_MODULE}.MOMENT_KIND_SPECS",
                {MomentKind.EVENT_FOLLOWUP: spec},
                clear=True,
            ),
            # Patched at its SOURCE: ``_serve`` imports it inside the function,
            # so the name never exists on this module.
            patch(
                "src.infrastructure.proactive.runner.execute_proactive_task",
                new=AsyncMock(return_value=stats),
            ),
        ):
            outcome = await moment_sweep._serve_one(_user(), NOW)
        return outcome, settled

    async def test_nothing_due_settles_nothing(self) -> None:
        outcome, settled = await self._run(
            claimed=None, facts=MomentFacts(still_valid=True), stats=_stats()
        )

        assert outcome == "none"
        assert settled == {}

    async def test_a_served_moment_is_settled_as_served(self) -> None:
        user_id = uuid4()
        outcome, settled = await self._run(
            claimed=_moment_row(user_id),
            facts=MomentFacts(still_valid=True, lines=("Meeting: x",)),
            stats=_stats(success=1),
        )

        assert outcome == MomentState.SERVED.value
        assert settled["state"] is MomentState.SERVED

    async def test_a_cancelled_fact_is_never_said(self) -> None:
        """The event was cancelled or moved while the moment waited."""
        outcome, settled = await self._run(
            claimed=_moment_row(uuid4()),
            facts=MomentFacts(still_valid=False),
            stats=_stats(success=1),
        )

        assert outcome == MomentState.CANCELLED.value
        assert settled["state"] is MomentState.CANCELLED

    async def test_a_quota_refusal_is_a_skip_never_a_failure(self) -> None:
        """A ceiling refusing a call is not a generation failure (ADR-272)."""
        outcome, settled = await self._run(
            claimed=_moment_row(uuid4()),
            facts=MomentFacts(still_valid=True),
            stats=_stats(skip_reasons={"usage_limit_exceeded": 1}),
        )

        assert settled["state"] is MomentState.SKIPPED
        assert settled["skip_reason"] is MomentSkipReason.QUOTA
        assert outcome == "skipped_quota"

    async def test_the_model_choosing_silence_is_recorded_as_such(self) -> None:
        """A moment is an occasion to speak, never an obligation."""
        _, settled = await self._run(
            claimed=_moment_row(uuid4()),
            facts=MomentFacts(still_valid=True),
            stats=_stats(skip_reasons={"no_target": 1}),
        )

        assert settled["skip_reason"] is MomentSkipReason.LLM_SKIP

    async def test_an_ineligible_account_is_recorded_as_such(self) -> None:
        _, settled = await self._run(
            claimed=_moment_row(uuid4()),
            facts=MomentFacts(still_valid=True),
            stats=_stats(skip_reasons={"quota_exceeded": 1}),
        )

        assert settled["skip_reason"] is MomentSkipReason.NOT_ELIGIBLE

    async def test_a_failed_revalidation_settles_rather_than_hanging(self) -> None:
        """A row left claimed forever is a row nothing will ever close."""
        settled: dict[str, Any] = {}
        repo = MagicMock()
        repo.claim_due = AsyncMock(return_value=_moment_row(uuid4()))

        async def _settle(moment_id, *, owner, state, skip_reason=None, now):
            settled.update(state=state, skip_reason=skip_reason)
            return True

        repo.settle = AsyncMock(side_effect=_settle)

        spec = MagicMock()
        spec.headline = "x"
        spec.revalidator = AsyncMock(side_effect=RuntimeError("provider down"))

        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch(f"{_MODULE}.MomentRepository", return_value=repo),
            patch.dict(
                f"{_MODULE}.MOMENT_KIND_SPECS",
                {MomentKind.EVENT_FOLLOWUP: spec},
                clear=True,
            ),
        ):
            outcome = await moment_sweep._serve_one(_user(), NOW)

        assert settled["skip_reason"] is MomentSkipReason.REVALIDATION_FAILED
        assert outcome == "skipped_revalidation_failed"


class TestDetecting:
    async def test_a_detector_that_blows_up_does_not_stop_the_others(self) -> None:
        good = MagicMock()
        good.detector = AsyncMock(return_value=[])
        bad = MagicMock()
        bad.detector = AsyncMock(side_effect=RuntimeError("calendar down"))

        recorded: dict[str, Any] = {}

        def _record(**kwargs: Any) -> None:
            recorded.update(kwargs)

        # Keys are enum members by contract (the registry's completeness assert
        # refuses anything else), so the stand-in for a second kind is a real
        # enum member — hashable, and carrying a ``.value`` like the code reads.
        second_kind = Enum("SecondKind", {"OTHER": "second"}).OTHER

        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch.dict(
                f"{_MODULE}.MOMENT_KIND_SPECS",
                {MomentKind.EVENT_FOLLOWUP: bad, second_kind: good},
                clear=True,
            ),
            patch(f"{_MODULE}.record_surface_consultations", side_effect=_record),
        ):
            filed = await moment_sweep._detect_for(_user(), NOW)

        assert filed == 0
        good.detector.assert_awaited_once()
        assert recorded["failed"] == [MomentKind.EVENT_FOLLOWUP.value]

    async def test_what_was_read_is_recorded_as_a_consultation(self) -> None:
        """Nobody asked, and nobody was watching: the register is the trace."""
        spec = MagicMock()
        spec.detector = AsyncMock(return_value=[])
        recorded: dict[str, Any] = {}

        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch.dict(
                f"{_MODULE}.MOMENT_KIND_SPECS",
                {MomentKind.EVENT_FOLLOWUP: spec},
                clear=True,
            ),
            patch(
                f"{_MODULE}.record_surface_consultations",
                side_effect=lambda **kw: recorded.update(kw),
            ),
        ):
            await moment_sweep._detect_for(_user(), NOW)

        assert recorded["surface"] == moment_sweep.CONSULTATION_SURFACE
        assert recorded["opened"] == [MomentKind.EVENT_FOLLOWUP.value]
        assert recorded["failed"] == []


class TestTheRefusalIsObeyed:
    """A switch that changes nothing is a lie an operator and a person act on.

    Refusing a kind stops BOTH halves: the detector is not even called (running
    it would spend a calendar read to file a row nothing will serve), and a row
    filed before the refusal is closed rather than served — the person changed
    their mind, which is not a failure.
    """

    async def test_a_refused_kind_is_never_detected(self) -> None:
        spec = MagicMock()
        spec.detector = AsyncMock(return_value=[])

        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch.dict(
                f"{_MODULE}.MOMENT_KIND_SPECS",
                {MomentKind.EVENT_FOLLOWUP: spec},
                clear=True,
            ),
            patch(f"{_MODULE}.record_surface_consultations"),
        ):
            filed = await moment_sweep._detect_for(
                _user(moment_kinds_disabled=[MomentKind.EVENT_FOLLOWUP.value]), NOW
            )

        assert filed == 0
        spec.detector.assert_not_awaited()

    async def test_a_refused_kind_records_no_consultation(self) -> None:
        """Nothing was opened, so the register must claim nothing."""
        spec = MagicMock()
        spec.detector = AsyncMock(return_value=[])
        recorded: dict[str, Any] = {}

        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch.dict(
                f"{_MODULE}.MOMENT_KIND_SPECS",
                {MomentKind.EVENT_FOLLOWUP: spec},
                clear=True,
            ),
            patch(
                f"{_MODULE}.record_surface_consultations",
                side_effect=lambda **kw: recorded.update(kw),
            ),
        ):
            await moment_sweep._detect_for(
                _user(moment_kinds_disabled=[MomentKind.EVENT_FOLLOWUP.value]), NOW
            )

        assert recorded["opened"] == []
        assert recorded["failed"] == []

    async def test_a_moment_filed_before_the_refusal_is_closed_not_served(self) -> None:
        settled: dict[str, Any] = {}
        repo = MagicMock()
        repo.claim_due = AsyncMock(return_value=_moment_row(uuid4()))

        async def _settle(moment_id, *, owner, state, skip_reason=None, now):
            settled.update(state=state, skip_reason=skip_reason)
            return True

        repo.settle = AsyncMock(side_effect=_settle)
        spec = MagicMock()
        spec.headline = "x"
        spec.revalidator = AsyncMock()

        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch(f"{_MODULE}.MomentRepository", return_value=repo),
            patch.dict(
                f"{_MODULE}.MOMENT_KIND_SPECS",
                {MomentKind.EVENT_FOLLOWUP: spec},
                clear=True,
            ),
        ):
            outcome = await moment_sweep._serve_one(
                _user(moment_kinds_disabled=[MomentKind.EVENT_FOLLOWUP.value]), NOW
            )

        assert outcome == MomentState.CANCELLED.value
        assert settled["state"] is MomentState.CANCELLED
        spec.revalidator.assert_not_awaited()


class TestHousekeepingGivesBackWhatItCanReach:
    """Three statements, and their ORDER is the whole point.

    A claim whose holder stopped answering is reachable by nothing else in the
    repository — expiry reads pending rows, the purge reads settled ones, a new
    claim reads pending. Measured on a real server: such a row was still there
    at +365 days. So it is handed back FIRST, and a row whose window has also
    closed is expired by the very next statement, in this same pass.
    """

    @staticmethod
    def _repo(reclaimed: int = 0, expired: list[str] | None = None, purged: int = 0) -> Any:
        repo = MagicMock()
        repo.reclaim_stale = AsyncMock(return_value=reclaimed)
        repo.expire_stale = AsyncMock(return_value=expired or [])
        repo.purge_settled = AsyncMock(return_value=purged)
        return repo

    async def test_it_reclaims_before_it_expires(self) -> None:
        calls: list[str] = []
        repo = self._repo()
        repo.reclaim_stale = AsyncMock(side_effect=lambda **_: calls.append("reclaim") or 0)
        repo.expire_stale = AsyncMock(side_effect=lambda **_: calls.append("expire") or [])
        repo.purge_settled = AsyncMock(side_effect=lambda **_: calls.append("purge") or 0)

        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch(f"{_MODULE}.MomentRepository", MagicMock(return_value=repo)),
        ):
            await moment_sweep._housekeeping(NOW)

        assert calls == ["reclaim", "expire", "purge"]

    async def test_the_lease_comes_from_the_setting_that_owns_it(self) -> None:
        repo = self._repo()
        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch(f"{_MODULE}.MomentRepository", MagicMock(return_value=repo)),
        ):
            await moment_sweep._housekeeping(NOW)

        lease = repo.reclaim_stale.await_args.kwargs["older_than"]
        assert lease == timedelta(minutes=settings.moments_claim_lease_minutes)
        # Generous on purpose: a lease shorter than a real serve would hand the
        # same moment to a second worker mid-sentence.
        assert lease >= timedelta(minutes=2)

    async def test_it_reports_all_three_counts(self) -> None:
        repo = self._repo(reclaimed=2, expired=[MomentKind.EVENT_FOLLOWUP.value], purged=7)
        with (
            patch(f"{_MODULE}.get_db_context", new=_db_ctx()),
            patch(f"{_MODULE}.MomentRepository", MagicMock(return_value=repo)),
        ):
            assert await moment_sweep._housekeeping(NOW) == (2, 1, 7)

    async def test_the_sweep_publishes_them_without_collision(self) -> None:
        """The per-account outcomes are nested: a settled state named like a
        housekeeping counter would otherwise overwrite it in the log."""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _granted(*_args: Any, **_kwargs: Any):
            yield SimpleNamespace(acquired=True)

        with (
            patch.object(moment_sweep, "_housekeeping", AsyncMock(return_value=(3, 1, 9))),
            patch.object(moment_sweep, "_eligible_accounts", AsyncMock(return_value=[])),
            patch(f"{_MODULE}.is_capability_enabled", AsyncMock(return_value=True)),
            patch(f"{_MODULE}.get_redis_cache", AsyncMock(return_value=MagicMock())),
            patch(f"{_MODULE}.SchedulerLock", _granted),
        ):
            result = await moment_sweep.run_moment_sweep()

        assert result["reclaimed"] == 3
        assert result["expired"] == 1
        assert result["purged"] == 9
        assert result["outcomes"] == {}
