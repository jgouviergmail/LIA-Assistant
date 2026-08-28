"""Self-diagnostics configuration (spec 2026-08-27, self-diagnostics programme).

Governs LIA's read access to its own telemetry (Prometheus, Loki, Alertmanager),
the deterministic self-check loop, the incident memory, the budgeted LLM
diagnosis, the request-path degradation advisor and the admin-only surfaces.

Doctrine reminders (enforced elsewhere, decided here):

- ``diagnostics_enabled`` defaults to **false**: with the flag off, no router,
  tool, scheduler job or webhook of this subsystem exists at runtime.
- An **empty source URL disables that source** — the clients report it as
  ``unavailable`` instead of failing, so an install without the observability
  stack behaves exactly as before this feature.
- Bounded Loki access: the *defaults* live here, but the **hard caps** live in
  ``src.core.constants`` (``DIAGNOSTICS_LOKI_MAX_*``) and the LogQL builder
  clamps to them regardless of configuration (Loki OOM history on the Pi).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    DIAGNOSTICS_ADVISOR_CACHE_TTL_SECONDS_DEFAULT,
    DIAGNOSTICS_ALERTMANAGER_URL_DEFAULT,
    DIAGNOSTICS_CHECK_API_ERROR_RATE_CRIT_DEFAULT,
    DIAGNOSTICS_CHECK_API_ERROR_RATE_WARN_DEFAULT,
    DIAGNOSTICS_CHECK_API_LATENCY_P95_CRIT_DEFAULT,
    DIAGNOSTICS_CHECK_API_LATENCY_P95_WARN_DEFAULT,
    DIAGNOSTICS_CHECK_DISK_USAGE_CRIT_DEFAULT,
    DIAGNOSTICS_CHECK_DISK_USAGE_WARN_DEFAULT,
    DIAGNOSTICS_CHECK_LLM_FAILURE_RATE_CRIT_DEFAULT,
    DIAGNOSTICS_CHECK_LLM_FAILURE_RATE_WARN_DEFAULT,
    DIAGNOSTICS_CHECK_MEMORY_USAGE_CRIT_DEFAULT,
    DIAGNOSTICS_CHECK_MEMORY_USAGE_WARN_DEFAULT,
    DIAGNOSTICS_CHECK_SCHEDULER_TICK_STALE_SECONDS_DEFAULT,
    DIAGNOSTICS_DIAGNOSIS_BATCH_SIZE_DEFAULT,
    DIAGNOSTICS_DIAGNOSIS_DAILY_COST_CAP_USD_DEFAULT,
    DIAGNOSTICS_DIAGNOSIS_MAX_ACTIONS_DEFAULT,
    DIAGNOSTICS_EGRESS_PROBE_TIMEOUT_SECONDS_DEFAULT,
    DIAGNOSTICS_FAILURE_CONTEXT_MAX_ENTRIES_DEFAULT,
    DIAGNOSTICS_HTTP_TIMEOUT_SECONDS_DEFAULT,
    DIAGNOSTICS_LOKI_DEFAULT_LINES_DEFAULT,
    DIAGNOSTICS_LOKI_MAX_LINES,
    DIAGNOSTICS_LOKI_URL_DEFAULT,
    DIAGNOSTICS_NOTIFICATION_COOLDOWN_SECONDS_DEFAULT,
    DIAGNOSTICS_PROMETHEUS_URL_DEFAULT,
    DIAGNOSTICS_RATE_LIMIT_CALLS_DEFAULT,
    DIAGNOSTICS_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    DIAGNOSTICS_RUNBOOK_MAX_CHARS_DEFAULT,
    DIAGNOSTICS_RUNBOOKS_DIR_DEFAULT,
    DIAGNOSTICS_SELF_CHECK_INTERVAL_SECONDS_DEFAULT,
    DIAGNOSTICS_SNAPSHOT_RETENTION_DAYS_DEFAULT,
)


class DiagnosticsSettings(BaseSettings):
    """Settings for the self-diagnostics subsystem (admin-only feature)."""

    diagnostics_enabled: bool = Field(
        default=False,
        description="Master switch for the self-diagnostics subsystem (opt-in).",
    )

    # ------------------------------------------------------------------
    # Telemetry sources (empty URL = source disabled)
    # ------------------------------------------------------------------
    diagnostics_prometheus_url: str = Field(
        default=DIAGNOSTICS_PROMETHEUS_URL_DEFAULT,
        description="Prometheus base URL on the compose network. Empty disables the source.",
    )
    diagnostics_loki_url: str = Field(
        default=DIAGNOSTICS_LOKI_URL_DEFAULT,
        description="Loki base URL on the compose network. Empty disables the source.",
    )
    diagnostics_alertmanager_url: str = Field(
        default=DIAGNOSTICS_ALERTMANAGER_URL_DEFAULT,
        description="Alertmanager base URL on the compose network. Empty disables the source.",
    )
    diagnostics_http_timeout_seconds: float = Field(
        default=DIAGNOSTICS_HTTP_TIMEOUT_SECONDS_DEFAULT,
        ge=0.5,
        le=30.0,
        description="Per-request timeout for telemetry HTTP calls.",
    )

    diagnostics_egress_probe_target: str = Field(
        default="",
        description=(
            "host:port the self-check opens a TCP connection to, to prove the "
            "platform can still reach the outside. Empty disables the check "
            "entirely — it is never reported as healthy on no measurement. Point "
            "it at a host this instance ALREADY talks to (its LLM provider, "
            "typically): probing anything else would disclose the instance's "
            "existence to a third party nobody chose."
        ),
    )
    diagnostics_egress_probe_timeout_seconds: float = Field(
        default=DIAGNOSTICS_EGRESS_PROBE_TIMEOUT_SECONDS_DEFAULT,
        ge=0.1,
        le=30.0,
        description="Per-attempt timeout of the egress probe.",
    )

    # ------------------------------------------------------------------
    # Self-check loop
    # ------------------------------------------------------------------
    diagnostics_self_check_interval_seconds: int = Field(
        default=DIAGNOSTICS_SELF_CHECK_INTERVAL_SECONDS_DEFAULT,
        ge=60,
        le=3600,
        description="Leader-only self-check cadence.",
    )
    diagnostics_snapshot_retention_days: int = Field(
        default=DIAGNOSTICS_SNAPSHOT_RETENTION_DAYS_DEFAULT,
        ge=1,
        le=365,
        description="Health snapshots older than this are pruned by the job.",
    )
    diagnostics_check_scheduler_tick_stale_seconds: int = Field(
        default=DIAGNOSTICS_CHECK_SCHEDULER_TICK_STALE_SECONDS_DEFAULT,
        ge=120,
        description="Scheduler-liveness check: last tick older than this is critical.",
    )

    # ------------------------------------------------------------------
    # Log access (defaults; hard caps are constants the builder clamps to)
    # ------------------------------------------------------------------
    diagnostics_loki_default_lines: int = Field(
        default=DIAGNOSTICS_LOKI_DEFAULT_LINES_DEFAULT,
        ge=1,
        le=DIAGNOSTICS_LOKI_MAX_LINES,
        description="Default line budget for log queries (tools and diagnosis evidence).",
    )

    # ------------------------------------------------------------------
    # Incidents & notifications
    # ------------------------------------------------------------------
    diagnostics_webhook_secret: str = Field(
        default="",
        description=(
            "Shared secret for the Alertmanager webhook. Empty keeps the endpoint "
            "absent (404), so the webhook cannot exist unauthenticated."
        ),
    )
    diagnostics_notification_cooldown_seconds: int = Field(
        default=DIAGNOSTICS_NOTIFICATION_COOLDOWN_SECONDS_DEFAULT,
        ge=60,
        description="Minimum delay between two admin notifications for one correlation key.",
    )

    # ------------------------------------------------------------------
    # LLM diagnosis budget
    # ------------------------------------------------------------------
    diagnostics_diagnosis_daily_cost_cap_usd: float = Field(
        default=DIAGNOSTICS_DIAGNOSIS_DAILY_COST_CAP_USD_DEFAULT,
        ge=0.0,
        description="Daily USD cap for diagnosis LLM calls; 0 disables the LLM step.",
    )
    diagnostics_diagnosis_batch_size: int = Field(
        default=DIAGNOSTICS_DIAGNOSIS_BATCH_SIZE_DEFAULT,
        ge=1,
        le=10,
        description="Max incidents diagnosed per self-check tick.",
    )
    diagnostics_diagnosis_max_actions: int = Field(
        default=DIAGNOSTICS_DIAGNOSIS_MAX_ACTIONS_DEFAULT,
        ge=1,
        le=10,
        description="Max recommended actions the diagnostician may produce (prompt placeholder).",
    )
    diagnostics_runbooks_dir: str = Field(
        default=DIAGNOSTICS_RUNBOOKS_DIR_DEFAULT,
        description="Directory holding per-alert runbooks (read-only mount in containers).",
    )
    diagnostics_runbook_max_chars: int = Field(
        default=DIAGNOSTICS_RUNBOOK_MAX_CHARS_DEFAULT,
        ge=500,
        le=20000,
        description="Runbook excerpt size cap fed to the diagnostician.",
    )

    # ------------------------------------------------------------------
    # Request-path resilience
    # ------------------------------------------------------------------
    diagnostics_failure_context_max_entries: int = Field(
        default=DIAGNOSTICS_FAILURE_CONTEXT_MAX_ENTRIES_DEFAULT,
        ge=1,
        le=50,
        description="Bound on the runtime_failures state key (checkpoint size guard).",
    )
    diagnostics_advisor_cache_ttl_seconds: int = Field(
        default=DIAGNOSTICS_ADVISOR_CACHE_TTL_SECONDS_DEFAULT,
        ge=5,
        le=600,
        description="TTL of the advisor's Redis-cached incident view.",
    )

    # ------------------------------------------------------------------
    # Chat tools rate limiting
    # ------------------------------------------------------------------
    diagnostics_rate_limit_calls: int = Field(
        default=DIAGNOSTICS_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=200,
        description="Max diagnostics tool calls per user per window (telemetry-load bound).",
    )
    diagnostics_rate_limit_window: int = Field(
        default=DIAGNOSTICS_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=3600,
        description="Rate-limit window (seconds) for diagnostics tools.",
    )

    # ------------------------------------------------------------------
    # Self-check thresholds (warn < crit enforced by the check registry test)
    # ------------------------------------------------------------------
    diagnostics_check_api_error_rate_warn: float = Field(
        default=DIAGNOSTICS_CHECK_API_ERROR_RATE_WARN_DEFAULT,
        ge=0.0,
        description="HTTP 5xx rate (%) above which the API check degrades.",
    )
    diagnostics_check_api_error_rate_crit: float = Field(
        default=DIAGNOSTICS_CHECK_API_ERROR_RATE_CRIT_DEFAULT,
        ge=0.0,
        description="HTTP 5xx rate (%) above which the API check is critical.",
    )
    diagnostics_check_api_latency_p95_warn: float = Field(
        default=DIAGNOSTICS_CHECK_API_LATENCY_P95_WARN_DEFAULT,
        ge=0.0,
        description="API p95 latency (seconds) above which the latency check degrades.",
    )
    diagnostics_check_api_latency_p95_crit: float = Field(
        default=DIAGNOSTICS_CHECK_API_LATENCY_P95_CRIT_DEFAULT,
        ge=0.0,
        description="API p95 latency (seconds) above which the latency check is critical.",
    )
    diagnostics_check_llm_failure_rate_warn: float = Field(
        default=DIAGNOSTICS_CHECK_LLM_FAILURE_RATE_WARN_DEFAULT,
        ge=0.0,
        description="LLM API failure rate (%) above which the LLM check degrades.",
    )
    diagnostics_check_llm_failure_rate_crit: float = Field(
        default=DIAGNOSTICS_CHECK_LLM_FAILURE_RATE_CRIT_DEFAULT,
        ge=0.0,
        description="LLM API failure rate (%) above which the LLM check is critical.",
    )
    diagnostics_check_disk_usage_warn: float = Field(
        default=DIAGNOSTICS_CHECK_DISK_USAGE_WARN_DEFAULT,
        ge=0.0,
        le=100.0,
        description="Disk usage (%) above which the storage check degrades.",
    )
    diagnostics_check_disk_usage_crit: float = Field(
        default=DIAGNOSTICS_CHECK_DISK_USAGE_CRIT_DEFAULT,
        ge=0.0,
        le=100.0,
        description="Disk usage (%) above which the storage check is critical.",
    )
    diagnostics_check_memory_usage_warn: float = Field(
        default=DIAGNOSTICS_CHECK_MEMORY_USAGE_WARN_DEFAULT,
        ge=0.0,
        le=100.0,
        description="Memory usage (%) above which the memory check degrades.",
    )
    diagnostics_check_memory_usage_crit: float = Field(
        default=DIAGNOSTICS_CHECK_MEMORY_USAGE_CRIT_DEFAULT,
        ge=0.0,
        le=100.0,
        description="Memory usage (%) above which the memory check is critical.",
    )
