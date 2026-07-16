"""
Observability configuration module.

Contains settings for:
- OpenTelemetry (OTEL)
- Prometheus
- Langfuse (LLM observability)

Phase: PHASE 2.1 - Config Split
Created: 2025-11-20
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    APP_VERSION_DEFAULT,
    BUILD_DATE_DEFAULT,
    EVALUATOR_HALLUCINATION_MAX_TOKENS_DEFAULT,
    EVALUATOR_LATENCY_ACCEPTABLE_THRESHOLD_MS_DEFAULT,
    EVALUATOR_LATENCY_EXCELLENT_THRESHOLD_MS_DEFAULT,
    EVALUATOR_LATENCY_GOOD_THRESHOLD_MS_DEFAULT,
    EVALUATOR_LATENCY_SLOW_THRESHOLD_MS_DEFAULT,
    EVALUATOR_RELEVANCE_MAX_TOKENS_DEFAULT,
    GEOIP_DB_PATH_DEFAULT,
    GIT_COMMIT_SHA_DEFAULT,
    LANGFUSE_FLUSH_INTERVAL_DEFAULT,
    LANGFUSE_SAMPLE_RATE_DEFAULT,
    LIFETIME_METRICS_UPDATE_INTERVAL_SECONDS_DEFAULT,
    OTEL_SERVICE_NAME_DEFAULT,
    PROMETHEUS_METRICS_PORT_DEFAULT,
)


class ObservabilitySettings(BaseSettings):
    """Observability and monitoring settings."""

    # OpenTelemetry
    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP exporter endpoint",
    )
    otel_service_name: str = Field(
        default=OTEL_SERVICE_NAME_DEFAULT,
        description="Service name for tracing",
    )

    # Build provenance (audit F030) — injected at build/deploy so a running
    # artifact is precisely identifiable across OTel, Langfuse, /health and logs.
    app_version: str = Field(
        default=APP_VERSION_DEFAULT,
        description="Release version of the running artifact (env APP_VERSION).",
    )
    git_commit_sha: str = Field(
        default=GIT_COMMIT_SHA_DEFAULT,
        validation_alias=AliasChoices("GIT_COMMIT_SHA", "GITHUB_SHA"),
        description="Git commit the artifact was built from (env GIT_COMMIT_SHA/GITHUB_SHA).",
    )
    build_date: str = Field(
        default=BUILD_DATE_DEFAULT,
        description="ISO-8601 UTC build timestamp (env BUILD_DATE).",
    )

    @property
    def build_release(self) -> str:
        """Human-readable ``version+shortsha`` release tag for tracing/Langfuse.

        Falls back to the bare version when the commit SHA was not injected.
        """
        sha = self.git_commit_sha
        if sha and sha != GIT_COMMIT_SHA_DEFAULT:
            return f"{self.app_version}+{sha[:12]}"
        return self.app_version

    # Prometheus
    prometheus_metrics_port: int = Field(
        default=PROMETHEUS_METRICS_PORT_DEFAULT,
        description="Dedicated HTTP-only port for Prometheus metrics scraping",
    )

    # Langfuse - LLM Observability (Phase 6)
    langfuse_enabled: bool = Field(
        default=False,
        description="Enable Langfuse tracing for LLM observability",
    )
    langfuse_host: str = Field(
        default="http://langfuse-web:3000",
        description="Langfuse server URL (self-hosted or cloud)",
    )
    langfuse_public_key: str = Field(
        default="",
        description="Langfuse public key (project identifier)",
    )
    langfuse_secret_key: str = Field(
        default="",
        description="Langfuse secret key (authentication)",
    )
    langfuse_release: str = Field(
        default="",
        description=(
            "Explicit Langfuse release tag. Leave empty to use the build "
            "provenance (build_release = app_version+commit) so deployments are "
            "identifiable instead of a fixed 'development' label (audit F030)."
        ),
    )
    langfuse_sample_rate: float = Field(
        default=LANGFUSE_SAMPLE_RATE_DEFAULT,
        ge=0.0,
        le=1.0,
        description="Sampling rate for traces (0.0-1.0, 1.0 = trace everything)",
    )
    langfuse_flush_interval: int = Field(
        default=LANGFUSE_FLUSH_INTERVAL_DEFAULT,
        ge=1,
        description="Flush interval in seconds (how often to send traces)",
    )
    langfuse_debug: bool = Field(
        default=False,
        description="Enable Langfuse debug mode (logs HTTP requests)",
    )

    # =========================================================================
    # LLM-as-Judge Evaluator Pipeline Settings (Phase 3.1.3)
    # =========================================================================
    # These settings control the evaluation pipeline that scores LLM outputs
    # for relevance, hallucination, and latency.

    evaluator_enabled: bool = Field(
        default=True,
        description="Enable LLM-as-judge evaluation pipeline",
    )
    # NOTE: evaluator LLM model/provider/temperature are configured via
    # LLM_DEFAULTS["evaluator"] in domains/llm_config/constants.py
    # and can be overridden via Admin UI (Settings > LLM Configuration)
    evaluator_relevance_max_tokens: int = Field(
        default=EVALUATOR_RELEVANCE_MAX_TOKENS_DEFAULT,
        description="Max tokens for relevance evaluator response",
    )
    evaluator_hallucination_max_tokens: int = Field(
        default=EVALUATOR_HALLUCINATION_MAX_TOKENS_DEFAULT,
        description="Max tokens for hallucination evaluator response",
    )
    evaluator_latency_excellent_threshold_ms: float = Field(
        default=EVALUATOR_LATENCY_EXCELLENT_THRESHOLD_MS_DEFAULT,
        description="Latency threshold for excellent score (1.0)",
    )
    evaluator_latency_good_threshold_ms: float = Field(
        default=EVALUATOR_LATENCY_GOOD_THRESHOLD_MS_DEFAULT,
        description="Latency threshold for good score (0.85)",
    )
    evaluator_latency_acceptable_threshold_ms: float = Field(
        default=EVALUATOR_LATENCY_ACCEPTABLE_THRESHOLD_MS_DEFAULT,
        description="Latency threshold for acceptable score (0.65)",
    )
    evaluator_latency_slow_threshold_ms: float = Field(
        default=EVALUATOR_LATENCY_SLOW_THRESHOLD_MS_DEFAULT,
        description="Latency threshold for slow score (0.45)",
    )
    evaluator_pipeline_send_to_langfuse: bool = Field(
        default=False,
        description="Send evaluation scores to Langfuse",
    )
    evaluator_hallucination_require_ground_truth: bool = Field(
        default=False,
        description="Require ground truth for hallucination detection",
    )

    # =========================================================================
    # Lifetime Metrics — DB-backed Prometheus gauges
    # =========================================================================
    lifetime_metrics_update_interval: int = Field(
        default=LIFETIME_METRICS_UPDATE_INTERVAL_SECONDS_DEFAULT,
        ge=5,
        description="Sync period in seconds for DB-backed lifetime gauges (tokens, cost)",
    )

    # =========================================================================
    # GeoIP — IP Geolocation (DB-IP Lite)
    # =========================================================================
    geoip_enabled: bool = Field(
        default=True,
        description="Enable IP geolocation enrichment in logs (requires MMDB file)",
    )
    geoip_db_path: str = Field(
        default=GEOIP_DB_PATH_DEFAULT,
        description="Path to GeoIP MMDB database file (DB-IP Lite City)",
    )
