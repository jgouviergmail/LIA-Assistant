"""The wake sweep serves queued wakes under the FULL eligibility (ADR-261).

Every wake ends in exactly one bounded outcome; the sweep never bypasses a
gate: stale payloads are dropped, the per-user wake cooldown is checked
first, a refused source never wakes, no signal never wakes, and a Drive wake
is a reindex, not a decision.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
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
        "push_wake_sweep_interval_seconds": 120,
        "push_wake_serve_timeout_seconds": 180,
        "push_wake_calendar_lookahead_hours": 24,
        "push_wake_calendar_recent_update_minutes": 10,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _acquired_lock() -> MagicMock:
    lock = MagicMock()
    lock.acquired = True
    lock_cm = MagicMock()
    lock_cm.__aenter__ = AsyncMock(return_value=lock)
    lock_cm.__aexit__ = AsyncMock(return_value=False)
    return lock_cm


@pytest.fixture(autouse=True)
def _settings_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sweep, "settings", _settings())


@pytest.fixture(autouse=True)
def _no_mail_watch_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hermetic: a Gmail wake's watch lookup used to reach a REAL database from these
    unit tests (2 s each, and a schema error in the log). The watches have their own
    module (test_wake_mail_watches.py)."""
    monkeypatch.setattr(
        "src.domains.scheduled_actions.mail_watches.has_mail_watches",
        AsyncMock(return_value=False),
    )
    # Same leak through the capability switch, read from the database per sweep.
    monkeypatch.setattr(sweep, "is_capability_enabled", AsyncMock(return_value=True))


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
            patch.object(sweep, "pop_next_wake", AsyncMock(side_effect=[payloads, None])),
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

    async def test_a_wake_that_stops_moving_is_cut_and_the_next_account_is_served(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Production, 2026-09-22: one Drive drain held the sweep 22 minutes (ADR-304)."""
        monkeypatch.setattr(sweep, "settings", _settings(push_wake_serve_timeout_seconds=0.05))
        stuck, next_one = _payload("google_drive"), _payload("google_gmail")

        async def _serve(_redis: object, payload: WakePayload) -> str:
            if payload is stuck:
                await asyncio.sleep(10)
            return "notified"

        before = sweep.push_wakes_total.labels(
            provider="google_drive", outcome="timeout"
        )._value.get()
        with (
            patch.object(sweep, "get_redis_cache", AsyncMock(return_value=MagicMock())),
            patch.object(sweep, "SchedulerLock", MagicMock(return_value=_acquired_lock())),
            patch.object(
                sweep, "pop_next_wake", AsyncMock(side_effect=[[stuck], [next_one], None])
            ),
            patch.object(sweep, "_serve_one", _serve),
        ):
            result = await sweep.run_heartbeat_wake_sweep()
        assert result == {"served": 1, "skipped": 1}
        assert (
            sweep.push_wakes_total.labels(provider="google_drive", outcome="timeout")._value.get()
            == before + 1
        )

    async def test_accounts_are_popped_one_at_a_time(self) -> None:
        """While one account is served, the others are still queued — nobody waits behind it."""
        queue = [[_payload("google_gmail")], [_payload("google_calendar")]]
        queued_during_first_serve: list[int] = []

        async def _pop(_redis: object, _providers: object) -> list[WakePayload] | None:
            return queue.pop(0) if queue else None

        async def _serve(_redis: object, _payload: WakePayload) -> str:
            queued_during_first_serve.append(len(queue))
            return "no_signal"

        with (
            patch.object(sweep, "get_redis_cache", AsyncMock(return_value=MagicMock())),
            patch.object(sweep, "SchedulerLock", MagicMock(return_value=_acquired_lock())),
            patch.object(sweep, "pop_next_wake", _pop),
            patch.object(sweep, "_serve_one", _serve),
        ):
            await sweep.run_heartbeat_wake_sweep()
        assert queued_during_first_serve == [1, 0]

    async def test_the_sweep_stops_at_its_per_sweep_bound(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sweep, "settings", _settings(push_wake_max_users_per_sweep=2))
        pop = AsyncMock(side_effect=lambda *_: [_payload()])
        with (
            patch.object(sweep, "get_redis_cache", AsyncMock(return_value=MagicMock())),
            patch.object(sweep, "SchedulerLock", MagicMock(return_value=_acquired_lock())),
            patch.object(sweep, "pop_next_wake", pop),
            patch.object(sweep, "_serve_one", AsyncMock(return_value="no_signal")),
        ):
            await sweep.run_heartbeat_wake_sweep()
        assert pop.await_count == 2

    async def test_the_lock_is_sized_on_the_sweeps_own_period(self) -> None:
        """A 120 s sweep under the default 300 s TTL found its previous lock
        still held on every other tick (2026-09-11): the TTL follows the period."""
        lock = MagicMock()
        lock.acquired = False
        lock_cm = MagicMock()
        lock_cm.__aenter__ = AsyncMock(return_value=lock)
        lock_cm.__aexit__ = AsyncMock(return_value=False)
        with (
            patch.object(sweep, "get_redis_cache", AsyncMock(return_value=MagicMock())),
            patch.object(sweep, "SchedulerLock", MagicMock(return_value=lock_cm)) as lock_cls,
            patch.object(sweep, "pop_next_wake", AsyncMock(return_value=None)),
        ):
            await sweep.run_heartbeat_wake_sweep()
        assert lock_cls.call_args.kwargs["ttl_seconds"] == sweep.ttl_for_interval(120)
        assert lock_cls.call_args.kwargs["ttl_seconds"] < 120

    async def test_lock_busy_serves_nothing(self) -> None:
        lock = MagicMock()
        lock.acquired = False
        lock_cm = MagicMock()
        lock_cm.__aenter__ = AsyncMock(return_value=lock)
        lock_cm.__aexit__ = AsyncMock(return_value=False)
        with (
            patch.object(sweep, "get_redis_cache", AsyncMock(return_value=MagicMock())),
            patch.object(sweep, "SchedulerLock", MagicMock(return_value=lock_cm)),
            patch.object(sweep, "pop_next_wake", AsyncMock()) as pop,
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


class _OpenSessions:
    """A detached connector service whose unit of work counts open sessions."""

    open = 0

    def __init__(self, credentials: object) -> None:
        self.service = MagicMock()
        self.service.get_connector_credentials = AsyncMock(return_value=credentials)
        self.service.db = MagicMock()

    @contextlib.asynccontextmanager
    async def unit_of_work(self) -> AsyncIterator[MagicMock]:
        _OpenSessions.open += 1
        try:
            yield self.service
        finally:
            _OpenSessions.open -= 1


class TestProbesHoldNoSession:
    """The Gmail and calendar probes read credentials, close, THEN call Google (ADR-304)."""

    async def test_the_gmail_delta_is_read_with_no_session_open(self) -> None:
        seen: list[int] = []

        async def _preview(_client: object, _anchor: str) -> tuple[list[str], str]:
            seen.append(_OpenSessions.open)
            return ["m1"], "h2"

        async def _metadata(_client: object, _ids: list[str]) -> list[dict]:
            seen.append(_OpenSessions.open)
            return [{"id": "m1"}]

        redis = MagicMock()
        redis.get = AsyncMock(return_value=b"h1")
        client = MagicMock()
        client.close = AsyncMock()
        detached = _OpenSessions({"token": "x"})
        with (
            patch.object(sweep, "get_redis_cache", AsyncMock(return_value=redis)),
            patch(
                "src.domains.connectors.session_scope.DetachedConnectorService",
                return_value=detached,
            ),
            patch(
                "src.domains.connectors.clients.google_gmail_client.GoogleGmailClient",
                return_value=client,
            ) as client_cls,
            patch("src.domains.heartbeat.wake_context.gmail_delta_preview", _preview),
            patch("src.domains.heartbeat.wake_context.fetch_mail_metadata", _metadata),
            patch.object(sweep, "record_surface_consultations"),
        ):
            delta = await sweep._gmail_delta(_payload("google_gmail"))
        assert delta == ([{"id": "m1"}], "h2")
        assert seen == [0, 0]
        # The client writes through the detached service, never a caller session.
        assert client_cls.call_args.args[2] is detached
        client.close.assert_awaited_once()

    async def test_the_calendar_probe_reads_its_preference_in_the_same_short_session(
        self,
    ) -> None:
        seen: list[int] = []

        async def _resolve(
            *, client: object, name: str | None, owner_id: object, container: object
        ) -> str:
            seen.append(_OpenSessions.open)
            return f"id-of-{name}"

        async def _changes(_client: object, **kwargs: object) -> list[dict]:
            seen.append(_OpenSessions.open)
            assert kwargs["calendar_id"] == "id-of-Work"
            return []

        client = MagicMock()
        client.close = AsyncMock()
        with (
            patch(
                "src.domains.connectors.session_scope.DetachedConnectorService",
                return_value=_OpenSessions({"token": "x"}),
            ),
            patch(
                "src.domains.connectors.clients.google_calendar_client.GoogleCalendarClient",
                return_value=client,
            ),
            patch(
                "src.domains.connectors.preferences.owner_defaults.read_owner_container_name",
                AsyncMock(return_value="Work"),
            ),
            patch(
                "src.domains.connectors.preferences.owner_defaults.resolve_owner_container_id",
                _resolve,
            ),
            patch("src.domains.heartbeat.wake_context.fetch_calendar_changes", _changes),
            patch.object(sweep, "record_surface_consultations"),
        ):
            outcome, _enriched = await sweep._calendar_signal(
                _payload("google_calendar"), SimpleNamespace(email="me@example.test")
            )
        assert outcome == "no_signal"
        assert seen == [0, 0]
        client.close.assert_awaited_once()

    async def test_no_calendar_credentials_is_a_disabled_source_and_calls_nothing(self) -> None:
        with (
            patch(
                "src.domains.connectors.session_scope.DetachedConnectorService",
                return_value=_OpenSessions(None),
            ),
            patch(
                "src.domains.connectors.clients.google_calendar_client.GoogleCalendarClient"
            ) as client_cls,
        ):
            outcome, _ = await sweep._calendar_signal(
                _payload("google_calendar"), SimpleNamespace(email="me@example.test")
            )
        assert outcome == "source_disabled"
        client_cls.assert_not_called()
