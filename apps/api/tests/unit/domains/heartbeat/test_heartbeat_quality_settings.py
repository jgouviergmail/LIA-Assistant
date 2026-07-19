"""Tests for heartbeat interest-quality settings wiring (ADR-135)."""

import pytest

from src.core.config import settings


@pytest.mark.unit
class TestHeartbeatQualitySettings:
    def test_sample_and_window_settings(self) -> None:
        assert 1 <= settings.heartbeat_interest_sample_size <= 20
        assert 5 <= settings.heartbeat_recent_window_count <= 30
        assert 1 <= settings.heartbeat_recent_window_days <= 30
        assert isinstance(settings.heartbeat_interest_enrichment_enabled, bool)
        assert 5 <= settings.heartbeat_enrichment_timeout_seconds <= 180
