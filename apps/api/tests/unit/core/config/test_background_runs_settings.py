"""Unit tests for BackgroundRunsSettings — detached chat runs (ADR-117)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.config.background_runs import BackgroundRunsSettings
from src.core.constants import REDIS_KEY_RUN_STREAM_PREFIX

# Every env var read by BackgroundRunsSettings — test_defaults asserts the
# CODE defaults, so all of them must be scrubbed (a var asserted but not
# isolated makes the test dependent on same-worker predecessors under xdist).
_ENV_VARS = (
    "BACKGROUND_RUNS_ENABLED",
    "BACKGROUND_RUNS_STREAM_MAXLEN",
    "BACKGROUND_RUNS_STREAM_TTL_SECONDS",
    "BACKGROUND_RUNS_STREAM_SAFETY_TTL_SECONDS",
    "BACKGROUND_RUNS_XREAD_BLOCK_MS",
    "BACKGROUND_RUNS_DRAIN_TIMEOUT_SECONDS",
    "BACKGROUND_RUNS_ACTIVE_TTL_SECONDS",
    "BACKGROUND_RUNS_HEARTBEAT_SECONDS",
    "BACKGROUND_RUNS_LISTENER_TTL_SECONDS",
    "BACKGROUND_RUNS_CANCEL_POLL_SECONDS",
    "BACKGROUND_RUNS_CANCEL_TTL_SECONDS",
    "BACKGROUND_RUNS_ORPHAN_GRACE_SECONDS",
    "SHUTDOWN_BACKGROUND_TASKS_TIMEOUT_SECONDS",
)


@pytest.mark.unit
class TestBackgroundRunsSettings:
    def test_defaults(self, monkeypatch):
        # Isolate from any ambient env so we assert the code defaults.
        for var in _ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        s = BackgroundRunsSettings()
        # Aligned on production (2026-08-06): background runs have been on.
        assert s.background_runs_enabled is True
        assert s.background_runs_stream_maxlen == 10000
        assert s.background_runs_stream_ttl_seconds == 1800
        assert s.background_runs_xread_block_ms == 2000
        assert s.background_runs_drain_timeout_seconds == 60
        assert s.shutdown_background_tasks_timeout_seconds == 15
        # Lot 2 — active-run lock + subscriber presence
        assert s.background_runs_active_ttl_seconds == 30
        assert s.background_runs_heartbeat_seconds == 10
        assert s.background_runs_listener_ttl_seconds == 30
        # Lot 3 — cancellation signal
        assert s.background_runs_cancel_poll_seconds == 1
        assert s.background_runs_cancel_ttl_seconds == 600
        # Hard-kill hardening (2026-07 audit)
        assert s.background_runs_stream_safety_ttl_seconds == 7200
        assert s.background_runs_orphan_grace_seconds == 20

    def test_heartbeat_stays_under_half_the_lock_ttl(self, monkeypatch):
        # A single missed beat must never expire a healthy run's lock.
        for var in _ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv("BACKGROUND_RUNS_ACTIVE_TTL_SECONDS", raising=False)
        monkeypatch.delenv("BACKGROUND_RUNS_HEARTBEAT_SECONDS", raising=False)
        s = BackgroundRunsSettings()
        assert s.background_runs_heartbeat_seconds <= s.background_runs_active_ttl_seconds / 2

    def test_env_override_propagates(self, monkeypatch):
        monkeypatch.setenv("BACKGROUND_RUNS_ENABLED", "true")
        monkeypatch.setenv("BACKGROUND_RUNS_XREAD_BLOCK_MS", "5000")
        s = BackgroundRunsSettings()
        assert s.background_runs_enabled is True
        assert s.background_runs_xread_block_ms == 5000

    def test_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            BackgroundRunsSettings(background_runs_xread_block_ms=20_000)  # le=15000
        with pytest.raises(ValidationError):
            BackgroundRunsSettings(background_runs_stream_maxlen=10)  # ge=100
        with pytest.raises(ValidationError):
            BackgroundRunsSettings(background_runs_drain_timeout_seconds=0)  # ge=5

    def test_xread_block_far_below_socket_timeout(self):
        # POC-2 (2026-07) proved a blocking XREAD whose window reaches the
        # client socket_timeout raises TimeoutError on redis-py 8. Keep a
        # 2x safety margin against the composed runtime settings.
        assert settings.background_runs_xread_block_ms / 1000 <= settings.redis_socket_timeout / 2

    def test_stream_key_prefix(self):
        assert REDIS_KEY_RUN_STREAM_PREFIX == "chat:run:"

    def test_flapping_heartbeat_config_rejected(self):
        # Boot-time guard: heartbeat > ttl/2 would let a single missed beat
        # expire a HEALTHY run's lock (concurrent-run thread race).
        with pytest.raises(ValidationError):
            BackgroundRunsSettings(
                background_runs_active_ttl_seconds=10,
                background_runs_heartbeat_seconds=8,
            )

    def test_safety_ttl_below_post_terminal_ttl_rejected(self):
        # Boot-time guard: a crashed run's stream must never vanish faster
        # than a completed one (swapped-values symptom).
        with pytest.raises(ValidationError):
            BackgroundRunsSettings(
                background_runs_stream_ttl_seconds=7200,
                background_runs_stream_safety_ttl_seconds=3600,
            )
        # Equality is the accepted floor.
        s = BackgroundRunsSettings(
            background_runs_stream_ttl_seconds=3600,
            background_runs_stream_safety_ttl_seconds=3600,
        )
        assert s.background_runs_stream_safety_ttl_seconds == 3600

    def test_orphan_grace_below_two_heartbeats_rejected(self):
        # Boot-time guard: the orphan exit is a last-resort escape hatch —
        # below 2x the heartbeat, one late beat could surface a false error
        # on a healthy silent run.
        with pytest.raises(ValidationError):
            BackgroundRunsSettings(
                background_runs_heartbeat_seconds=6,
                background_runs_orphan_grace_seconds=11,
            )
        s = BackgroundRunsSettings(
            background_runs_heartbeat_seconds=6,
            background_runs_orphan_grace_seconds=12,
        )
        assert s.background_runs_orphan_grace_seconds == 12
