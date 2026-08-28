"""Unit tests for DiagnosticsSettings — self-diagnostics feature configuration.

The flag MUST default to false (the whole subsystem is opt-in), telemetry
sources MUST be individually disablable via an empty URL, and every bounded
field MUST reject out-of-range values at construction (never at use time).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config.diagnostics import DiagnosticsSettings
from src.core.constants import DIAGNOSTICS_LOKI_MAX_LINES

_ENV_VARS = (
    "DIAGNOSTICS_ENABLED",
    "DIAGNOSTICS_PROMETHEUS_URL",
    "DIAGNOSTICS_LOKI_URL",
    "DIAGNOSTICS_ALERTMANAGER_URL",
    "DIAGNOSTICS_HTTP_TIMEOUT_SECONDS",
    "DIAGNOSTICS_SELF_CHECK_INTERVAL_SECONDS",
    "DIAGNOSTICS_SNAPSHOT_RETENTION_DAYS",
    "DIAGNOSTICS_LOKI_DEFAULT_LINES",
    "DIAGNOSTICS_NOTIFICATION_COOLDOWN_SECONDS",
    "DIAGNOSTICS_DIAGNOSIS_DAILY_COST_CAP_USD",
    "DIAGNOSTICS_WEBHOOK_SECRET",
    "DIAGNOSTICS_FAILURE_CONTEXT_MAX_ENTRIES",
    "DIAGNOSTICS_ADVISOR_CACHE_TTL_SECONDS",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate from any ambient env so tests assert the code defaults."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.mark.unit
class TestDiagnosticsSettings:
    def test_flag_defaults_to_false(self, clean_env: None) -> None:
        assert DiagnosticsSettings().diagnostics_enabled is False

    def test_source_url_defaults_are_compose_service_names(self, clean_env: None) -> None:
        s = DiagnosticsSettings()
        assert s.diagnostics_prometheus_url == "http://prometheus:9090"
        assert s.diagnostics_loki_url == "http://loki:3100"
        assert s.diagnostics_alertmanager_url == "http://alertmanager:9093"

    def test_empty_url_is_accepted_as_disabled_source(self, clean_env: None) -> None:
        s = DiagnosticsSettings(diagnostics_prometheus_url="")
        assert s.diagnostics_prometheus_url == ""

    def test_operational_defaults(self, clean_env: None) -> None:
        s = DiagnosticsSettings()
        assert s.diagnostics_http_timeout_seconds == 5.0
        assert s.diagnostics_self_check_interval_seconds == 300
        assert s.diagnostics_snapshot_retention_days == 30
        assert s.diagnostics_loki_default_lines == 200
        assert s.diagnostics_notification_cooldown_seconds == 3600
        assert s.diagnostics_failure_context_max_entries == 10
        assert s.diagnostics_advisor_cache_ttl_seconds == 30
        assert s.diagnostics_webhook_secret == ""
        assert s.diagnostics_diagnosis_daily_cost_cap_usd == pytest.approx(1.0)

    def test_default_lines_stays_under_the_hard_cap(self, clean_env: None) -> None:
        s = DiagnosticsSettings()
        assert s.diagnostics_loki_default_lines <= DIAGNOSTICS_LOKI_MAX_LINES

    def test_env_override_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIAGNOSTICS_ENABLED", "true")
        monkeypatch.setenv("DIAGNOSTICS_SELF_CHECK_INTERVAL_SECONDS", "600")
        s = DiagnosticsSettings()
        assert s.diagnostics_enabled is True
        assert s.diagnostics_self_check_interval_seconds == 600

    def test_out_of_range_rejected(self, clean_env: None) -> None:
        with pytest.raises(ValidationError):
            DiagnosticsSettings(diagnostics_self_check_interval_seconds=10)  # ge=60
        with pytest.raises(ValidationError):
            DiagnosticsSettings(diagnostics_loki_default_lines=DIAGNOSTICS_LOKI_MAX_LINES + 1)
        with pytest.raises(ValidationError):
            DiagnosticsSettings(diagnostics_http_timeout_seconds=0.0)  # ge=0.5
        with pytest.raises(ValidationError):
            DiagnosticsSettings(diagnostics_diagnosis_daily_cost_cap_usd=-1.0)  # ge=0

    def test_check_thresholds_read_from_settings_and_ordered(self, clean_env: None) -> None:
        """warn < crit for every threshold pair — read dynamically, no literals."""
        s = DiagnosticsSettings()
        pairs = [
            (s.diagnostics_check_api_error_rate_warn, s.diagnostics_check_api_error_rate_crit),
            (s.diagnostics_check_api_latency_p95_warn, s.diagnostics_check_api_latency_p95_crit),
            (s.diagnostics_check_llm_failure_rate_warn, s.diagnostics_check_llm_failure_rate_crit),
            (s.diagnostics_check_disk_usage_warn, s.diagnostics_check_disk_usage_crit),
            (s.diagnostics_check_memory_usage_warn, s.diagnostics_check_memory_usage_crit),
        ]
        for warn, crit in pairs:
            assert warn < crit

    def test_composed_settings_expose_diagnostics_fields(self, clean_env: None) -> None:
        """DiagnosticsSettings must be in the Settings MRO (config composition rule)."""
        from src.core.config import Settings

        assert "diagnostics_enabled" in Settings.model_fields
