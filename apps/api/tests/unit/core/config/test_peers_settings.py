"""Guard the PeersSettings composition into the Settings MRO (peers program, Lot 1)."""

import pytest

from src.core.config import settings


@pytest.mark.unit
class TestPeersSettings:
    """The peers config module is composed and carries sane defaults."""

    def test_flag_defaults_to_disabled(self):
        assert settings.peers_enabled is False

    def test_discovery_rate_limit_defaults(self):
        assert settings.peers_discovery_rate_limit_calls == 10
        assert settings.peers_discovery_rate_limit_window_seconds == 60

    def test_message_quota_defaults(self):
        assert settings.peers_message_max_per_day == 20
        assert settings.peers_message_max_per_day_per_pair == 10
        assert settings.peers_message_max_chars == 2000
        assert (
            settings.peers_message_max_per_day_per_pair <= settings.peers_message_max_per_day
        ), "per-pair quota must never exceed the global daily quota"

    def test_request_policy_defaults(self):
        assert settings.peers_request_cooldown_days == 7
        assert settings.peers_request_expiry_days == 30

    def test_delivery_and_retention_defaults(self):
        assert settings.peers_delivery_sweep_seconds == 60
        assert settings.peers_delivery_max_attempts == 5
        assert settings.peers_access_log_retention_days == 90
