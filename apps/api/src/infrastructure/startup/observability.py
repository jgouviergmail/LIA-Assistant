"""Startup steps: observability subsystems.

Prometheus metrics HTTP server, Langfuse callback factory and the DB-backed
lifetime metrics updater task. Extracted verbatim from ``src.main.lifespan``
(ADR-123): same structlog events, same exception handling.
"""

import asyncio
import os

import structlog

from src.core.config import settings

logger = structlog.get_logger(__name__)


def start_metrics_server() -> None:
    """Start the dedicated HTTP-only Prometheus metrics server.

    Separate from the main HTTPS uvicorn server so Prometheus can scrape
    without TLS handshake issues between Docker containers.
    """
    metrics_port = settings.prometheus_metrics_port
    prometheus_multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    try:
        from prometheus_client import CollectorRegistry, start_http_server

        if prometheus_multiproc_dir:
            # Multi-worker (prod): expose the AGGREGATE of every worker's metrics.
            # All workers write to PROMETHEUS_MULTIPROC_DIR; the first worker to bind
            # the port serves a MultiProcessCollector registry that reads them all.
            from prometheus_client import multiprocess

            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            start_http_server(metrics_port, registry=registry)
        else:
            start_http_server(metrics_port)  # Daemon thread, auto-stops on process exit
        logger.info(
            "prometheus_metrics_server_started",
            port=metrics_port,
            multiprocess=bool(prometheus_multiproc_dir),
        )
    except OSError as exc:
        # In multiprocess mode only one worker binds the port; the others legitimately
        # fail (they still export metrics via the shared dir), so it is expected and
        # logged at debug instead of warning to avoid noise on every redeploy.
        if prometheus_multiproc_dir:
            logger.debug(
                "prometheus_metrics_server_not_bound_multiproc",
                port=metrics_port,
                error=str(exc),
            )
        else:
            logger.warning("prometheus_metrics_server_failed", port=metrics_port, error=str(exc))


def init_langfuse() -> None:
    """Initialize the Langfuse callback factory for LLM observability."""
    try:
        from src.infrastructure.llm.callback_factory import init_callback_factory

        callback_factory = init_callback_factory(settings)
        if callback_factory.is_enabled():
            logger.info(
                "langfuse_callback_factory_initialized",
                host=settings.langfuse_host,
                release=settings.langfuse_release,
            )
        else:
            logger.info("langfuse_tracing_disabled")
    except (RuntimeError, ImportError, ValueError, ConnectionError) as exc:
        logger.error("langfuse_initialization_failed", error=str(exc), exc_info=True)


def start_lifetime_metrics() -> asyncio.Task[None] | None:
    """Start the lifetime metrics updater task (Phase 1.2 - DB-Backed Gauges).

    Solves RC1: Prometheus counter resets on restart.

    Returns:
        The running updater task (to cancel at shutdown), or None on failure.
    """
    lifetime_metrics_task: asyncio.Task[None] | None = None
    try:
        from src.infrastructure.observability.lifetime_metrics import update_lifetime_metrics

        lifetime_metrics_task = asyncio.create_task(update_lifetime_metrics())
        logger.info(
            "lifetime_metrics_updater_started",
            message="DB-backed Prometheus gauges will sync every 30s (restart-safe)",
        )
    except (RuntimeError, ImportError) as exc:
        logger.error("lifetime_metrics_updater_failed", error=str(exc), exc_info=True)
    return lifetime_metrics_task
