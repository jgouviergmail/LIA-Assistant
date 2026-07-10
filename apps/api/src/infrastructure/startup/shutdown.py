"""Shutdown sequence for the application lifespan (ADR-123).

Extracted verbatim from ``src.main.lifespan``: same structlog events, same
exception handling, same ordering. Order matters:

1. Drain in-flight chat producers FIRST (ADR-117) — they need the
   checkpointer, DB pool and Redis that are torn down below.
2. Generic fire-and-forget background tasks, for the same reason.
3. Flush/stop emitters (Prometheus multiproc, lifetime metrics, Langfuse)
   before their transports disappear.
4. Stop the scheduler (leader lock release) before its dependencies close.
5. Close pools and clients; the DB closes near the end and Redis closes
   LAST (the drain and the invalidation subscriber both depend on it).
"""

import asyncio
import os
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.infrastructure.cache.redis import close_redis
from src.infrastructure.database.session import close_db

if TYPE_CHECKING:
    from telegram import Bot

    from src.infrastructure.mcp.client_manager import MCPClientManager
    from src.infrastructure.scheduler.leader_elector import SchedulerLeaderElector

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class StartupHandles:
    """Cross-``yield`` state produced at startup and consumed at shutdown.

    Attributes:
        leader_elector: Always constructed at startup; its ``shutdown()`` is
            awaited unconditionally (stops the scheduler, releases the lock).
        mcp_manager: Truthy gate for MCP cleanup. May be a PARTIALLY
            initialized manager (startup failed mid-way) — cleanup still runs.
        telegram_bot: Truthy gate for the Telegram bot shutdown.
        lifetime_metrics_task: Lifetime metrics updater task to cancel (None
            if it never started).
        cache_invalidation_task: Cache invalidation subscriber task to cancel
            (None if it never started).
    """

    leader_elector: "SchedulerLeaderElector"
    mcp_manager: "MCPClientManager | None"
    telegram_bot: "Bot | None"
    lifetime_metrics_task: "asyncio.Task[None] | None"
    cache_invalidation_task: "asyncio.Task[None] | None"


async def shutdown_application(handles: StartupHandles) -> None:
    """Run the full shutdown sequence in the exact historical order.

    Args:
        handles: The cross-``yield`` state accumulated by the lifespan startup.
    """
    # === Drain in-flight background work FIRST (ADR-117) ===
    # Order matters: chat producers need the checkpointer, DB pool and Redis
    # that are torn down below. Without this drain, uvicorn worker recycling
    # (--limit-max-requests) and docker stop kill in-flight runs (proven by
    # the 2026-07 de-risking POC: 1/30 chunks survived without drain, 30/30
    # with it). Keep drain + generic-task timeouts below stop_grace_period.
    try:
        from src.domains.agents.api.background_runner import drain_chat_producers

        drained_done, drained_pending = await drain_chat_producers(
            timeout=settings.background_runs_drain_timeout_seconds
        )
        if drained_pending:
            logger.warning(
                "chat_producers_drain_incomplete",
                done=drained_done,
                pending=drained_pending,
            )
    except Exception as exc:
        logger.error("chat_producers_drain_failed", error=str(exc))

    # Generic fire-and-forget tasks (memory/interest extraction, warmups).
    # wait_all_background_tasks existed but was never wired — latent bug fixed
    # here (Systemic Rules: dead code is wired or removed).
    try:
        from src.infrastructure.async_utils import wait_all_background_tasks

        await wait_all_background_tasks(timeout=settings.shutdown_background_tasks_timeout_seconds)
    except Exception as exc:
        logger.error("background_tasks_drain_failed", error=str(exc))

    # Prometheus multiprocess: drop this worker's per-process metric files so its
    # contribution leaves the 'live*' gauges on exit. Counters/histograms persist
    # (correct — totals must survive a worker restart). No-op outside multiprocess.
    prometheus_multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if prometheus_multiproc_dir:
        try:
            from prometheus_client import multiprocess

            multiprocess.mark_process_dead(os.getpid())
            logger.info("prometheus_multiproc_marked_dead", pid=os.getpid())
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            logger.warning("prometheus_multiproc_cleanup_failed", error=str(exc))

    # Stop lifetime metrics updater
    if handles.lifetime_metrics_task:
        try:
            handles.lifetime_metrics_task.cancel()
            with suppress(asyncio.CancelledError):
                await handles.lifetime_metrics_task
            logger.info("lifetime_metrics_updater_stopped")
        except RuntimeError as exc:
            logger.error("lifetime_metrics_updater_shutdown_failed", error=str(exc))

    # Flush and shutdown Langfuse (Phase 6 - LLM Observability)
    try:
        from src.infrastructure.llm.callback_factory import (
            flush_callbacks,
            shutdown_callback_factory,
        )

        flush_callbacks()
        shutdown_callback_factory()
        logger.info("langfuse_shutdown_complete")
    except (RuntimeError, ImportError) as exc:
        logger.error("langfuse_shutdown_failed", error=str(exc))

    # Stop scheduler and release leader lock
    await handles.leader_elector.shutdown()

    # Reset v3.1 Semantic Services (clear cached embeddings)
    # Note: SemanticIntentDetector and SemanticDomainSelector removed in v3.1
    try:
        from src.domains.agents.services.tool_selector import reset_tool_selector

        reset_tool_selector()
        logger.info("v3_semantic_services_reset", services=["SemanticToolSelector"])
    except (RuntimeError, ImportError) as exc:
        logger.error("v3_semantic_services_reset_failed", error=str(exc))

    # Clear agent registry cache
    try:
        from src.domains.agents.registry import reset_global_registry

        reset_global_registry()
        logger.info("agent_registry_cleared")
    except (RuntimeError, ImportError) as exc:
        logger.error("agent_registry_cleanup_failed", error=str(exc))

    # Close MCP connections (evolution F2)
    if handles.mcp_manager:
        try:
            from src.infrastructure.mcp.client_manager import cleanup_mcp_client_manager

            await cleanup_mcp_client_manager()
            logger.info("mcp_connections_closed")
        except (RuntimeError, ImportError) as exc:
            logger.error("mcp_shutdown_failed", error=str(exc))

    # Close user MCP pool connections (evolution F2.1)
    if getattr(settings, "mcp_user_enabled", False):
        try:
            from src.infrastructure.mcp.user_pool import cleanup_user_mcp_pool

            await cleanup_user_mcp_pool()
            logger.info("user_mcp_pool_closed")
        except (RuntimeError, ImportError) as exc:
            logger.error("user_mcp_pool_shutdown_failed", error=str(exc))

    # Close browser pool (evolution F7)
    # Browser not installed — nothing to close
    with suppress(RuntimeError, ImportError):
        from src.infrastructure.browser.pool import close_browser_pool

        await close_browser_pool()
        logger.info("browser_pool_closed")

    # Shutdown Telegram Bot (evolution F3)
    if handles.telegram_bot:
        try:
            from src.infrastructure.channels.telegram.bot import shutdown_telegram_bot

            await shutdown_telegram_bot()
            logger.info("telegram_bot_shutdown")
        except (RuntimeError, ImportError) as exc:
            logger.error("telegram_bot_shutdown_failed", error=str(exc))

    # Close checkpointer connection
    try:
        from src.domains.conversations.checkpointer import cleanup_checkpointer

        await cleanup_checkpointer()
        logger.info("checkpointer_closed")
    except (RuntimeError, ImportError, ConnectionError) as exc:
        logger.error("checkpointer_shutdown_failed", error=str(exc))

    # Close tool context store connection
    try:
        from src.domains.agents.context import cleanup_tool_context_store

        await cleanup_tool_context_store()
        logger.info("tool_context_store_closed")
    except (RuntimeError, ImportError, ConnectionError) as exc:
        logger.error("tool_context_store_shutdown_failed", error=str(exc))

    # Close geocoding HTTP client (connection pooling cleanup)
    try:
        from src.domains.connectors.clients.google_geocoding_helpers import (
            close_geocoding_client,
        )

        await close_geocoding_client()
        logger.info("geocoding_client_closed")
    except (RuntimeError, ImportError) as exc:
        logger.error("geocoding_client_shutdown_failed", error=str(exc))

    # Close GeoIP reader
    try:
        from src.infrastructure.observability.geoip import geoip_resolver

        geoip_resolver.close()
        logger.info("geoip_reader_closed")
    except Exception as exc:
        logger.error("geoip_reader_close_failed", error=str(exc))

    # Close database connections
    await close_db()
    logger.info("database_closed")

    # Stop cross-worker cache invalidation subscriber (ADR-063)
    if handles.cache_invalidation_task:
        try:
            handles.cache_invalidation_task.cancel()
            # Expected: task was just cancelled above
            with suppress(asyncio.CancelledError):
                await handles.cache_invalidation_task
            logger.info("cache_invalidation_subscriber_stopped")
        except RuntimeError as exc:
            logger.error("cache_invalidation_subscriber_shutdown_failed", error=str(exc))

    # Close Redis connections
    await close_redis()
    logger.info("redis_closed")
