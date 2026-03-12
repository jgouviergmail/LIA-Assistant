"""
Observability configuration module.

Contains settings for:
- OpenTelemetry (OTEL)
- Prometheus
- Langfuse (LLM observability)

Phase: PHASE 2.1 - Config Split
Created: 2025-11-20
"""

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import GEOIP_DB_PATH_DEFAULT, OTEL_SERVICE_NAME_DEFAULT


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

    # Prometheus
    prometheus_metrics_port: int = Field(
        default=9091,
        description="Dedicated HTTP-only port for Prometheus metrics scraping",
    )

    # Langfuse - LLM Observability (Phase 6)
    langfuse_enabled: bool = Field(
        default=True,
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
        default="development",
        description="Release version for tracking deployments",
    )
    langfuse_sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Sampling rate for traces (0.0-1.0, 1.0 = trace everything)",
    )
    langfuse_flush_interval: int = Field(
        default=5,
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
        default=500,
        description="Max tokens for relevance evaluator response",
    )
    evaluator_hallucination_max_tokens: int = Field(
        default=1000,
        description="Max tokens for hallucination evaluator response",
    )
    evaluator_latency_excellent_threshold_ms: float = Field(
        default=500.0,
        description="Latency threshold for excellent score (1.0)",
    )
    evaluator_latency_good_threshold_ms: float = Field(
        default=1000.0,
        description="Latency threshold for good score (0.85)",
    )
    evaluator_latency_acceptable_threshold_ms: float = Field(
        default=2000.0,
        description="Latency threshold for acceptable score (0.65)",
    )
    evaluator_latency_slow_threshold_ms: float = Field(
        default=5000.0,
        description="Latency threshold for slow score (0.45)",
    )
    evaluator_pipeline_send_to_langfuse: bool = Field(
        default=True,
        description="Send evaluation scores to Langfuse",
    )
    evaluator_hallucination_require_ground_truth: bool = Field(
        default=False,
        description="Require ground truth for hallucination detection",
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
