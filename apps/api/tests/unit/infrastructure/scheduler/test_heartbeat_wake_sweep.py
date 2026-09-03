"""The wake sweep serves queued wakes under the FULL eligibility (ADR-261).

Every wake ends in exactly one bounded outcome; the sweep never bypasses a
gate: stale payloads are dropped, the per-user wake cooldown is checked
first, a refused source never wakes, no signal never wakes, and a Drive wake
is a reindex, not a decision.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.push_channels.wake import WakePayload
from src.infrastructure.scheduler import heartbeat_wake_sweep as sweep

pytestmark = pytest.mark.unit


def _payload(provider: str = "google_gmail", age_seconds: int = 30) -> WakePayload:
    return WakePayload(
        user_id=uuid.uuid4(),
        provider=provider,
        enqueued_at=datetime.now(UTC) - timedelta(seconds=age_seconds),
    )


def _settings(**overrides: object) -> SimpleNamespace:
    base = {
        "push_channels_enabled": True,
        "push_wake_enabled": True,
        "heartbeat_enabled": True,
        "push_wake_payload_ttl_seconds": 3600,
        "push_wake_cooldown_minutes": 20,
        "push_wake_max_users_per_sweep": 10,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _settings_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sweep, "settings", _settings())


class TestServeOne:
    async def test_stale_payload_is_dropped_before_anything(self) -> None:
        with patch.object(sweep, "try_acquire_wake_cooldown", AsyncMock()) as cooldown:
            assert await sweep._serve_one(MagicMock(), _payload(age_seconds=7200)) == "stale"
        cooldown.assert_not_awaited()

    async def test_drive_wake_is_a_reindex_not_a_decision(self) -> None:
        with (
            patch.object(sweep, "_serve_drive", AsyncMock(return_value="reindexed")) as drive,
            patch.object(sweep, "try_acquire_wake_cooldown", AsyncMock()) as cooldown,
        ):
            assert await sweep._serve_one(MagicMock(), _payload("google_drive")) == "reindexed"
        drive.assert_awaited_once()
        cooldown.assert_not_awaited()

    async def test_cooldown_refuses_a_second_wake(self) -> None:
        with patch.object(sweep, "try_acquire_wake_cooldown", AsyncMock(return_value=False)):
            assert await sweep._serve_one(MagicMock(), _payload()) == "cooldown"

    async def test_unknown_or_heartbeat_disabled_user_is_ineligible(self) -> None:
        with (
            patch.object(sweep, "try_acquire_wake_cooldown", AsyncMock(return_value=True)),
            patch.object(sweep, "_load_user", AsyncMock(return_value=None)),
        ):
            assert await sweep._serve_one(MagicMock(), _payload()) == "ineligible"
        with (
            patch.object(sweep, "try_acquire_wake_cooldown", AsyncMock(return_value=True)),
            patch.object(
                sweep,
                "_load_user",
                AsyncMock(return_value=SimpleNamespace(heartbeat_enabled=False)),
            ),
        ):
            assert await sweep._serve_one(MagicMock(), _payload()) == "ineligible"

    async def test_a_refused_source_never_wakes(self) -> None:
        user = SimpleNamespace(heartbeat_enabled=True, heartbeat_disabled_sources=["emails"])
        with (
            patch.object(sweep, "try_acquire_wake_cooldown", AsyncMock(return_value=True)),
            patch.object(sweep, "_load_user", AsyncMock(return_value=user)),
            patch.object(sweep, "_gmail_signal", AsyncMock()) as signal,
        ):
            assert (
                await sweep._serve_one(MagicMock(), _payload("google_gmail")) == "source_disabled"
            )
        signal.assert_not_awaited()

    async def test_no_signal_stops_before_the_heartbeat(self) -> None:
        user = SimpleNamespace(heartbeat_enabled=True, heartbeat_disabled_sources=[])
        payload = _payload("google_gmail")
        with (
            patch.object(sweep, "try_acquire_wake_cooldown", AsyncMock(return_value=True)),
            patch.object(sweep, "_load_user", AsyncMock(return_value=user)),
            patch.object(sweep, "_gmail_signal", AsyncMock(return_value=("no_signal", payload))),
            patch.object(sweep, "_serve_heartbeat", AsyncMock()) as serve,
        ):
            assert await sweep._serve_one(MagicMock(), payload) == "no_signal"
        serve.assert_not_awaited()

    async def test_a_signal_runs_the_heartbeat_for_that_user_only(self) -> None:
        user = SimpleNamespace(heartbeat_enabled=True, heartbeat_disabled_sources=[])
        payload = _payload("google_calendar")
        enriched = WakePayload(
            payload.user_id, "google_calendar", payload.enqueued_at, events=({"id": "e"},)
        )
        with (
            patch.object(sweep, "try_acquire_wake_cooldown", AsyncMock(return_value=True)),
            patch.object(sweep, "_load_user", AsyncMock(return_value=user)),
            patch.object(sweep, "_calendar_signal", AsyncMock(return_value=("signal", enriched))),
            patch.object(sweep, "_serve_heartbeat", AsyncMock(return_value="notified")) as serve,
        ):
            assert await sweep._serve_one(MagicMock(), payload) == "notified"
        assert serve.await_args.args[0] is enriched


class TestServeHeartbeat:
    async def test_the_runner_targets_the_user_and_skips_only_the_probabilistic_gate(
        self,
    ) -> None:
        payload = _payload("google_gmail")
        stats = SimpleNamespace(success=1, skip_reasons={})
        with (
            patch(
                "src.infrastructure.proactive.runner.execute_proactive_task",
                AsyncMock(return_value=stats),
            ) as run,
            patch(
                "src.infrastructure.scheduler.heartbeat_notification._create_heartbeat_eligibility_checker",
                MagicMock(return_value="checker"),
            ),
        ):
            assert await sweep._serve_heartbeat(payload) == "notified"
        kwargs = run.await_args.kwargs
        assert kwargs["user_ids"] == [payload.user_id]
        assert kwargs["skip_probabilistic_gate"] is True
        assert kwargs["eligibility_checker"] == "checker"
        assert kwargs["task"].wake is payload

    async def test_outcomes_follow_the_runner_stats(self) -> None:
        payload = _payload()
        for stats, expected in (
            (SimpleNamespace(success=0, skip_reasons={"no_target": 1}), "no_target"),
            (SimpleNamespace(success=0, skip_reasons={"outside_time_window": 1}), "ineligible"),
        ):
            with (
                patch(
                    "src.infrastructure.proactive.runner.execute_proactive_task",
                    AsyncMock(return_value=stats),
                ),
                patch(
                    "src.infrastructure.scheduler.heartbeat_notification._create_heartbeat_eligibility_checker",
                    MagicMock(),
                ),
            ):
                assert await sweep._serve_heartbeat(payload) == expected


class TestSweep:
    async def test_flag_off_does_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sweep, "settings", _settings(push_wake_enabled=False))
        with patch.object(sweep, "get_redis_cache", AsyncMock()) as redis:
            assert await sweep.run_heartbeat_wake_sweep() == {"served": 0, "skipped": 0}
        redis.assert_not_awaited()

    async def test_every_wake_is_counted_and_an_error_never_kills_the_sweep(self) -> None:
        payloads = [_payload("google_gmail"), _payload("google_calendar"), _payload("google_drive")]
        outcomes = iter(["notified", RuntimeError("boom"), "reindexed"])

        async def _serve(_redis: object, _payload: WakePayload) -> str:
            value = next(outcomes)
            if isinstance(value, Exception):
                raise value
            return value

        lock = MagicMock()
        lock.acquired = True
        lock_cm = MagicMock()
        lock_cm.__aenter__ = AsyncMock(return_value=lock)
        lock_cm.__aexit__ = AsyncMock(return_value=False)
        before = {
            o: sweep.push_wakes_total.labels(provider=p, outcome=o)._value.get()
            for p, o in (
                ("google_gmail", "notified"),
                ("google_calendar", "error"),
                ("google_drive", "reindexed"),
            )
        }
        with (
            patch.object(sweep, "get_redis_cache", AsyncMock(return_value=MagicMock())),
            patch.object(sweep, "SchedulerLock", MagicMock(return_value=lock_cm)),
            patch.object(sweep, "pop_wakes", AsyncMock(return_value=payloads)),
            patch.object(sweep, "_serve_one", _serve),
        ):
            result = await sweep.run_heartbeat_wake_sweep()
        assert result == {"served": 2, "skipped": 1}
        assert (
            sweep.push_wakes_total.labels(provider="google_gmail", outcome="notified")._value.get()
            == before["notified"] + 1
        )
        assert (
            sweep.push_wakes_total.labels(provider="google_calendar", outcome="error")._value.get()
            == before["error"] + 1
        )
        assert (
            sweep.push_wakes_total.labels(provider="google_drive", outcome="reindexed")._value.get()
            == before["reindexed"] + 1
        )

    async def test_lock_busy_serves_nothing(self) -> None:
        lock = MagicMock()
        lock.acquired = False
        lock_cm = MagicMock()
        lock_cm.__aenter__ = AsyncMock(return_value=lock)
        lock_cm.__aexit__ = AsyncMock(return_value=False)
        with (
            patch.object(sweep, "get_redis_cache", AsyncMock(return_value=MagicMock())),
            patch.object(sweep, "SchedulerLock", MagicMock(return_value=lock_cm)),
            patch.object(sweep, "pop_wakes", AsyncMock()) as pop,
        ):
            result = await sweep.run_heartbeat_wake_sweep()
        assert result["lock_busy"] == 1
        pop.assert_not_awaited()


class TestMailSources:
    """A Gmail wake feeds the label sources (ADR-262) before any heartbeat gate."""

    async def test_label_sources_are_indexed_before_the_cooldown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sweep, "settings", _settings(rag_spaces_mail_sync_enabled=True))
        payload = _payload("google_gmail")
        with (
            patch(
                "src.domains.rag_spaces.mail_sync.index_mail_sources_from_push",
                AsyncMock(return_value="indexed"),
            ) as index,
            patch.object(sweep, "try_acquire_wake_cooldown", AsyncMock(return_value=False)),
        ):
            assert await sweep._serve_one(MagicMock(), payload) == "cooldown"
        index.assert_awaited_once_with(payload.user_id)

    async def test_flag_off_never_touches_the_sources(self) -> None:
        with (
            patch(
                "src.domains.rag_spaces.mail_sync.index_mail_sources_from_push", AsyncMock()
            ) as index,
            patch.object(sweep, "try_acquire_wake_cooldown", AsyncMock(return_value=False)),
        ):
            await sweep._serve_one(MagicMock(), _payload("google_gmail"))
        index.assert_not_awaited()

    async def test_an_indexing_failure_never_costs_the_wake(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sweep, "settings", _settings(rag_spaces_mail_sync_enabled=True))
        with (
            patch(
                "src.domains.rag_spaces.mail_sync.index_mail_sources_from_push",
                AsyncMock(side_effect=RuntimeError("boom")),
            ),
            patch.object(sweep, "try_acquire_wake_cooldown", AsyncMock(return_value=False)),
        ):
            assert await sweep._serve_one(MagicMock(), _payload("google_gmail")) == "cooldown"
