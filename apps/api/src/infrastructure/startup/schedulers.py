"""Startup step: background job registration and scheduler leader election.

Registers every APScheduler job (feature-flag gated where applicable) and
starts the scheduler behind Redis leader election. ALL jobs must be
registered before ``leader_elector.start()`` — ``scheduler.start()`` happens
inside the elector, and the elected-jobs summary reads the job list. The
browser cleanup job is the one exception registered elsewhere (with the
browser agent, in ``startup.agents``) but still before this step runs.

Extracted verbatim from ``src.main.lifespan`` (ADR-123): same structlog
events (``scheduler_elected_jobs_summary`` included), same single try/except
around registration + start, same feature-flag guards, same SCHEDULER_JOB_*
constants.
"""

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.core.constants import (
    ACCOUNT_EXPORT_EXECUTOR_INTERVAL_SECONDS,
    CURRENCY_SYNC_HOUR,
    CURRENCY_SYNC_MINUTE,
    SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS,
    SCHEDULER_JOB_ACCOUNT_EXPORT,
    SCHEDULER_JOB_ATTACHMENT_CLEANUP,
    SCHEDULER_JOB_CURRENCY_SYNC,
    SCHEDULER_JOB_DEMO_ACCOUNT_PURGE,
    SCHEDULER_JOB_DEMO_DAILY_REPORT,
    SCHEDULER_JOB_HEARTBEAT_NOTIFICATION,
    SCHEDULER_JOB_INTEREST_CLEANUP,
    SCHEDULER_JOB_INTEREST_NOTIFICATION,
    SCHEDULER_JOB_INTEREST_SUBJECT_FULL,
    SCHEDULER_JOB_INTEREST_SUBJECT_STALE,
    SCHEDULER_JOB_JOURNAL_CONSOLIDATION,
    SCHEDULER_JOB_LEADER_LOCK_RENEWAL,
    SCHEDULER_JOB_MEMORY_CLEANUP,
    SCHEDULER_JOB_MEMORY_CONSOLIDATION,
    SCHEDULER_JOB_OAUTH_HEALTH,
    SCHEDULER_JOB_PRODUCT_ROLLUP,
    SCHEDULER_JOB_PSYCHE_DREAM_CYCLE,
    SCHEDULER_JOB_RAG_JOB_REAPER,
    SCHEDULER_JOB_REMINDER_NOTIFICATION,
    SCHEDULER_JOB_SCHEDULED_ACTION_EXECUTOR,
    SCHEDULER_JOB_TELEPHONY_NOTIFICATION_REAPER,
    SCHEDULER_JOB_TELEPHONY_RETENTION_REAPER,
    SCHEDULER_JOB_TELEPHONY_RETURN_REAPER,
    SCHEDULER_JOB_TELEPHONY_STALE_REAPER,
    SCHEDULER_JOB_TOKEN_REFRESH,
    SCHEDULER_JOB_UNVERIFIED_CLEANUP,
    SCHEDULER_JOB_USER_MCP_EVICTION,
    UNVERIFIED_ACCOUNT_CLEANUP_HOUR,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.scheduler.currency_sync import sync_currency_rates
from src.infrastructure.scheduler.interest_cleanup import cleanup_interests
from src.infrastructure.scheduler.interest_notification import process_interest_notifications
from src.infrastructure.scheduler.leader_elector import SchedulerLeaderElector
from src.infrastructure.scheduler.memory_cleanup import cleanup_memories
from src.infrastructure.scheduler.memory_consolidation import consolidate_memories
from src.infrastructure.scheduler.oauth_health import check_oauth_health_all_users
from src.infrastructure.scheduler.reminder_notification import process_pending_reminders
from src.infrastructure.scheduler.scheduled_action_executor import process_scheduled_actions
from src.infrastructure.scheduler.token_refresh import refresh_expiring_tokens
from src.infrastructure.scheduler.unverified_account_cleanup import cleanup_unverified_accounts

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = structlog.get_logger(__name__)


async def init_scheduler(scheduler: "AsyncIOScheduler") -> SchedulerLeaderElector:
    """Register all background jobs and start the scheduler behind leader election.

    Args:
        scheduler: The module-level APScheduler instance from ``src.main``
            (the browser cleanup job was already registered on it).

    Returns:
        The leader elector. Always constructed (even when registration or
        start failed — matching the historical lifespan behavior); its
        ``shutdown()`` must be awaited at application shutdown.
    """
    # ===================================================================
    # SCHEDULER LEADER ELECTION
    # ===================================================================
    redis_for_leader = None
    try:
        redis_for_leader = await get_redis_cache()
    except Exception as exc:
        logger.warning("scheduler_leader_redis_unavailable", error=str(exc))

    async def _on_scheduler_elected() -> None:
        """Log scheduled jobs when this worker becomes leader."""
        jobs = [j.id for j in scheduler.get_jobs() if j.id != SCHEDULER_JOB_LEADER_LOCK_RENEWAL]
        logger.info("scheduler_elected_jobs_summary", jobs=jobs, pid=os.getpid())

    leader_elector = SchedulerLeaderElector(
        redis_for_leader,
        scheduler,
        on_elected=_on_scheduler_elected,
    )

    # Start APScheduler for background tasks
    try:
        # Schedule daily currency sync at configured time (default: 3:00 AM UTC)
        scheduler.add_job(
            sync_currency_rates,
            trigger="cron",
            hour=CURRENCY_SYNC_HOUR,
            minute=CURRENCY_SYNC_MINUTE,
            id=SCHEDULER_JOB_CURRENCY_SYNC,
            name="Sync USD→EUR rates from API to DB",
            replace_existing=True,
        )

        # Schedule daily memory cleanup (Phase 6 - Long-Term Memory Purge)
        # Runs at configured hour (default: 4:00 AM UTC)
        # NOTE: Memory features are always enabled
        scheduler.add_job(
            cleanup_memories,
            trigger="cron",
            hour=settings.memory_cleanup_hour,
            minute=settings.memory_cleanup_minute,
            id=SCHEDULER_JOB_MEMORY_CLEANUP,
            name="Cleanup old unused memories (hybrid retention algorithm)",
            replace_existing=True,
        )
        logger.info(
            "memory_cleanup_job_scheduled",
            hour=settings.memory_cleanup_hour,
            minute=settings.memory_cleanup_minute,
        )

        # Schedule daily memory consolidation (merge near-duplicates)
        # Runs at configured hour (default: 5:00 AM UTC, right after cleanup)
        # so the table is pruned before consolidation. Gated by feature flag.
        if settings.memory_consolidation_enabled:
            scheduler.add_job(
                consolidate_memories,
                trigger="cron",
                hour=settings.memory_consolidation_hour,
                minute=0,
                id=SCHEDULER_JOB_MEMORY_CONSOLIDATION,
                name="Consolidate near-duplicate memories",
                replace_existing=True,
            )
            logger.info(
                "memory_consolidation_job_scheduled",
                hour=settings.memory_consolidation_hour,
                similarity_threshold=settings.memory_consolidation_similarity_threshold,
            )

        # Schedule daily interest cleanup (dormant marking + deletion)
        # Runs at 3:00 AM UTC (before memory cleanup at 4 AM)
        # NOTE: Interest features are always enabled
        scheduler.add_job(
            cleanup_interests,
            trigger="cron",
            hour=3,  # 3 AM UTC
            minute=0,
            id=SCHEDULER_JOB_INTEREST_CLEANUP,
            name="Cleanup dormant and old interests",
            replace_existing=True,
        )
        logger.info("interest_cleanup_job_scheduled", hour=3, minute=0)

        # Subject clustering (ADR-131): stale scan + nightly full re-cluster.
        # Subjects feed the subject-rarity notification selection, so both
        # jobs are gated by the notification scheduler flag.
        if settings.interest_notifications_enabled:
            from src.infrastructure.scheduler.interest_subject_clustering import (
                run_subject_clustering_full,
                run_subject_clustering_stale,
            )

            scheduler.add_job(
                run_subject_clustering_stale,
                trigger="interval",
                minutes=settings.interest_subject_recluster_interval_minutes,
                id=SCHEDULER_JOB_INTEREST_SUBJECT_STALE,
                name="Cluster interests with missing subject labels",
                replace_existing=True,
                max_instances=1,  # Prevent concurrent runs
                misfire_grace_time=60,
            )
            scheduler.add_job(
                run_subject_clustering_full,
                trigger="cron",
                hour=settings.interest_subject_recluster_full_hour,
                minute=15,  # After the 03:00 cleanup+merge pass
                id=SCHEDULER_JOB_INTEREST_SUBJECT_FULL,
                name="Nightly full interest subject re-clustering",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300,
            )
            logger.info(
                "interest_subject_clustering_jobs_scheduled",
                stale_interval_minutes=settings.interest_subject_recluster_interval_minutes,
                full_hour=settings.interest_subject_recluster_full_hour,
            )

        # Schedule reminder notification job (every minute)
        # Checks for pending reminders and sends notifications
        if settings.fcm_enabled:
            scheduler.add_job(
                process_pending_reminders,
                trigger="interval",
                minutes=1,
                id=SCHEDULER_JOB_REMINDER_NOTIFICATION,
                name="Process pending reminder notifications",
                replace_existing=True,
                max_instances=1,  # Prevent concurrent runs
                misfire_grace_time=30,  # Allow 30s delay before considering job missed
            )
            logger.info("reminder_notification_job_scheduled", interval_minutes=1)

        # Schedule scheduled action executor (every 60s)
        # Checks for due scheduled actions and executes them through the agent pipeline
        scheduler.add_job(
            process_scheduled_actions,
            trigger="interval",
            seconds=SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS,
            id=SCHEDULER_JOB_SCHEDULED_ACTION_EXECUTOR,
            name="Process scheduled actions",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=30,
        )

        # Account export executor (security program D3) — build + sweep tick.
        if getattr(settings, "account_export_enabled", False):
            from src.domains.account_export.executor import process_account_exports

            scheduler.add_job(
                process_account_exports,
                trigger="interval",
                seconds=ACCOUNT_EXPORT_EXECUTOR_INTERVAL_SECONDS,
                id=SCHEDULER_JOB_ACCOUNT_EXPORT,
                name="Build account export archives + retention sweep",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=30,
            )
            logger.info(
                "account_export_executor_job_scheduled",
                interval_seconds=ACCOUNT_EXPORT_EXECUTOR_INTERVAL_SECONDS,
            )

        # Product analytics rollup (ADR-178) — cost backfill, E2 upgrades,
        # retention purge, DB-backed gauge refresh. Leader-elected like every
        # job here; guarded by the product feature flag. next_run_time pins the
        # FIRST run shortly after boot: an interval-only job starves when the
        # API restarts more often than the interval (measured in prod — every
        # gauge stayed empty across 4 boots).
        if getattr(settings, "product_analytics_enabled", False):
            from src.core.constants import PRODUCT_ROLLUP_INITIAL_DELAY_MINUTES
            from src.infrastructure.scheduler.product_rollup import run_product_rollup

            scheduler.add_job(
                run_product_rollup,
                trigger="interval",
                minutes=settings.product_rollup_interval_minutes,
                next_run_time=datetime.now(UTC)
                + timedelta(minutes=PRODUCT_ROLLUP_INITIAL_DELAY_MINUTES),
                id=SCHEDULER_JOB_PRODUCT_ROLLUP,
                name="Product analytics rollup (ADR-178)",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300,
            )
            logger.info(
                "product_rollup_job_scheduled",
                interval_minutes=settings.product_rollup_interval_minutes,
            )

        # Peers relayed-message delivery sweep (peers program, Lot 4): the
        # durable delivery guarantee — the post-confirmation kick only
        # shortens the happy-path latency. Also recovers crash-stranded
        # claims and expires stale pending requests (one job owns every
        # peers time-based transition).
        if getattr(settings, "peers_enabled", False):
            from src.core.constants import SCHEDULER_JOB_PEERS_DELIVERY_SWEEP
            from src.infrastructure.scheduler.peer_message_delivery import (
                sweep_pending_deliveries,
            )

            scheduler.add_job(
                sweep_pending_deliveries,
                trigger="interval",
                seconds=settings.peers_delivery_sweep_seconds,
                id=SCHEDULER_JOB_PEERS_DELIVERY_SWEEP,
                name="Peers relayed-message delivery sweep",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60,
            )
            logger.info(
                "peers_delivery_sweep_job_scheduled",
                interval_seconds=settings.peers_delivery_sweep_seconds,
            )
        logger.info(
            "scheduled_action_executor_job_scheduled",
            interval_seconds=SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS,
        )

        # ADR-083 Phase 2 cleanup: SubAgentExecutor + its stale-recovery
        # scheduler job were removed. The ephemeral planner-delegation path
        # runs on ReactSubAgentRunner (no ORM records, no stale rows to
        # recover). The persistent /sub-agents REST API was deleted too.

        # Schedule proactive interest notifications (configurable interval, default 15 min)
        # Sends personalized content about user's interests (Wikipedia, Perplexity, LLM)
        # NOTE: Interest features are always enabled (no feature flag check)
        scheduler.add_job(
            process_interest_notifications,
            trigger="interval",
            minutes=settings.interest_notification_interval_minutes,
            id=SCHEDULER_JOB_INTEREST_NOTIFICATION,
            name="Proactive interest notifications",
            replace_existing=True,
            max_instances=1,  # Prevent concurrent runs
            misfire_grace_time=60,  # Allow 1 min delay before considering job missed
        )
        logger.info(
            "interest_notification_job_scheduled",
            interval_minutes=settings.interest_notification_interval_minutes,
        )

        # Schedule unverified account cleanup (daily at 5 AM UTC)
        # Deletes non-OAuth accounts that haven't verified email after 1 day
        scheduler.add_job(
            cleanup_unverified_accounts,
            trigger="cron",
            hour=UNVERIFIED_ACCOUNT_CLEANUP_HOUR,
            minute=0,
            id=SCHEDULER_JOB_UNVERIFIED_CLEANUP,
            name="Cleanup unverified accounts older than 1 day",
            replace_existing=True,
        )
        logger.info(
            "unverified_account_cleanup_job_scheduled",
            hour=UNVERIFIED_ACCOUNT_CLEANUP_HOUR,
        )

        # Schedule proactive OAuth token refresh (configurable interval)
        # Refreshes tokens expiring within configurable margin to prevent disconnections
        # NOTE: Proactive refresh is always enabled for production reliability
        scheduler.add_job(
            refresh_expiring_tokens,
            trigger="interval",
            minutes=settings.oauth_proactive_refresh_interval_minutes,
            id=SCHEDULER_JOB_TOKEN_REFRESH,
            name="Proactive OAuth token refresh",
            replace_existing=True,
            max_instances=1,  # Prevent concurrent runs
            misfire_grace_time=60,  # Allow 1 min delay before considering job missed
        )
        logger.info(
            "token_refresh_job_scheduled",
            interval_minutes=settings.oauth_proactive_refresh_interval_minutes,
            margin_seconds=settings.oauth_proactive_refresh_margin_seconds,
        )

        # Schedule OAuth health check (push notifications for broken connectors)
        # Only notifies on status=ERROR (refresh failed, needs manual re-auth)
        # NOTE: Only enabled if oauth_health_check_enabled is True
        if settings.oauth_health_check_enabled:
            scheduler.add_job(
                check_oauth_health_all_users,
                trigger="interval",
                minutes=settings.oauth_health_check_interval_minutes,
                id=SCHEDULER_JOB_OAUTH_HEALTH,
                name="OAuth health check notifications",
                replace_existing=True,
                max_instances=1,  # Prevent concurrent runs
                misfire_grace_time=60,  # Allow 1 min delay before considering job missed
            )
            logger.info(
                "oauth_health_check_job_scheduled",
                interval_minutes=settings.oauth_health_check_interval_minutes,
            )

        # Schedule user MCP pool eviction (evolution F2.1)
        if getattr(settings, "mcp_user_enabled", False):

            async def _evict_user_mcp_idle() -> None:
                from src.infrastructure.mcp.user_pool import get_user_mcp_pool

                pool = get_user_mcp_pool()
                if pool:
                    await pool.evict_idle()

            eviction_interval = getattr(settings, "mcp_user_pool_eviction_interval", 60)
            scheduler.add_job(
                _evict_user_mcp_idle,
                trigger="interval",
                seconds=eviction_interval,
                id=SCHEDULER_JOB_USER_MCP_EVICTION,
                name="User MCP pool idle eviction",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=30,
            )
            logger.info(
                "user_mcp_eviction_job_scheduled",
                interval_seconds=eviction_interval,
            )

        # Schedule proactive heartbeat notifications (evolution F5 — Heartbeat Autonome)
        # Only registered if feature flag enabled (pattern: channels_enabled)
        if getattr(settings, "heartbeat_enabled", False):
            from src.infrastructure.scheduler.heartbeat_notification import (
                process_heartbeat_notifications,
            )

            scheduler.add_job(
                process_heartbeat_notifications,
                trigger="interval",
                minutes=settings.heartbeat_notification_interval_minutes,
                id=SCHEDULER_JOB_HEARTBEAT_NOTIFICATION,
                name="Proactive heartbeat notifications",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60,
            )
            logger.info(
                "heartbeat_notification_job_scheduled",
                interval_minutes=settings.heartbeat_notification_interval_minutes,
            )

        # Schedule journal consolidation (Personal Journals — Carnets de Bord)
        # Runs every N hours (configurable) to review and maintain journal entries
        if getattr(settings, "journals_enabled", False):
            from src.infrastructure.scheduler.journal_consolidation import (
                process_journal_consolidation,
            )

            scheduler.add_job(
                process_journal_consolidation,
                trigger="interval",
                hours=settings.journal_consolidation_interval_hours,
                id=SCHEDULER_JOB_JOURNAL_CONSOLIDATION,
                name="Journal consolidation",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=300,
            )
            logger.info(
                "journal_consolidation_job_scheduled",
                interval_hours=settings.journal_consolidation_interval_hours,
            )

        # Schedule telephony reapers (agentic calls — spec P4.3)
        # - stale-call reaper (interval): frees phantom in-flight calls with no webhook.
        # - notification reaper (interval): re-dispatches return notifications a crash
        #   left PENDING (T1 durability).
        # - retention reaper (daily cron): clears summary/structured_data past TTL (D-8).
        if getattr(settings, "telephony_enabled", False):
            from src.domains.telephony.reapers import (
                telephony_notification_reaper,
                telephony_retention_reaper,
                telephony_return_reaper,
                telephony_stale_call_reaper,
            )

            scheduler.add_job(
                telephony_stale_call_reaper,
                trigger="interval",
                minutes=settings.telephony_stale_reaper_interval_minutes,
                id=SCHEDULER_JOB_TELEPHONY_STALE_REAPER,
                name="Telephony stale-call recovery",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60,
            )
            scheduler.add_job(
                telephony_notification_reaper,
                trigger="interval",
                minutes=settings.telephony_notification_reaper_interval_minutes,
                id=SCHEDULER_JOB_TELEPHONY_NOTIFICATION_REAPER,
                name="Telephony return-notification recovery",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60,
            )
            scheduler.add_job(
                telephony_return_reaper,
                trigger="interval",
                minutes=settings.telephony_return_reaper_interval_minutes,
                id=SCHEDULER_JOB_TELEPHONY_RETURN_REAPER,
                name="Telephony pre-synthesis return recovery",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60,
            )
            scheduler.add_job(
                telephony_retention_reaper,
                trigger="cron",
                hour=4,
                minute=30,
                id=SCHEDULER_JOB_TELEPHONY_RETENTION_REAPER,
                name="Telephony call retention purge",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=600,
            )
            logger.info(
                "telephony_reapers_scheduled",
                stale_interval_minutes=settings.telephony_stale_reaper_interval_minutes,
                notification_interval_minutes=settings.telephony_notification_reaper_interval_minutes,
            )

        # RAG durable-job recovery (audit F001): requeue upload/processing jobs a
        # crash stranded (stuck PROCESSING / orphaned PENDING). An immediate first
        # run at boot (on the elected leader) satisfies "recovery worker at
        # startup", then it runs periodically.
        if getattr(settings, "rag_spaces_enabled", False):
            from src.domains.rag_spaces.reapers import rag_job_reaper

            scheduler.add_job(
                rag_job_reaper,
                trigger="interval",
                seconds=settings.rag_job_reaper_interval_seconds,
                id=SCHEDULER_JOB_RAG_JOB_REAPER,
                name="RAG durable-job recovery",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60,
                next_run_time=datetime.now(UTC),
            )
            logger.info(
                "rag_job_reaper_scheduled",
                interval_seconds=settings.rag_job_reaper_interval_seconds,
            )

        # Schedule psyche weekly narrative (Psyche Engine — self-reflection)
        if getattr(settings, "psyche_enabled", False):
            from src.infrastructure.scheduler.psyche_snapshot import (
                process_psyche_weekly_narrative,
            )

            scheduler.add_job(
                process_psyche_weekly_narrative,
                trigger="cron",
                day_of_week="sun",
                hour=3,
                minute=0,
                id=SCHEDULER_JOB_PSYCHE_DREAM_CYCLE,
                name="Psyche weekly narrative",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=600,
            )
            logger.info("psyche_weekly_narrative_job_scheduled", cron="sun@03:00")

        # Schedule attachment cleanup (evolution F4 — File Attachments)
        # Runs every 6 hours as TTL safety net for orphan files
        if getattr(settings, "attachments_enabled", False):
            from src.infrastructure.scheduler.attachment_cleanup import (
                cleanup_expired_attachments,
            )

            scheduler.add_job(
                cleanup_expired_attachments,
                trigger="interval",
                hours=6,
                id=SCHEDULER_JOB_ATTACHMENT_CLEANUP,
                name="Cleanup expired attachments",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60,
            )
            logger.info("attachment_cleanup_job_scheduled", interval_hours=6)

        # Schedule nightly habit-profile recompute (ADR-214). One aggregate
        # query + one upsert per enabled user; per-user sessions and error
        # boundaries live inside the job.
        if getattr(settings, "habits_enabled", False):
            from src.core.constants import SCHEDULER_JOB_ID_HABIT_PROFILE
            from src.infrastructure.scheduler.habit_profile_job import (
                run_habit_profile_job,
            )

            scheduler.add_job(
                run_habit_profile_job,
                trigger="cron",
                hour=settings.habits_profile_job_hour_utc,
                minute=10,
                id=SCHEDULER_JOB_ID_HABIT_PROFILE,
                name="Recompute learned habit profiles",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
            logger.info(
                "habit_profile_job_scheduled",
                hour_utc=settings.habits_profile_job_hour_utc,
            )

        # Daily operator report — public demonstrator only, and registered
        # BEFORE the purge below because it must RUN before it: the database
        # lives in tmpfs and the purge drops what the report describes. The
        # ordering is enforced by the settings, not by this position; see
        # tests/unit/infrastructure/scheduler/test_demo_daily_report.py.
        if settings.demo_mode_enabled and settings.demo_daily_report_recipient:
            from src.infrastructure.scheduler.demo_daily_report import (
                run_demo_daily_report,
            )

            scheduler.add_job(
                run_demo_daily_report,
                trigger="cron",
                hour=settings.demo_daily_report_hour,
                minute=settings.demo_daily_report_minute,
                id=SCHEDULER_JOB_DEMO_DAILY_REPORT,
                name="Mail the demonstrator's daily report (before the purge)",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=600,
            )
            logger.info(
                "demo_daily_report_scheduled",
                hour=settings.demo_daily_report_hour,
                minute=settings.demo_daily_report_minute,
            )

        # Nightly visitor-account wipe — public demonstrator only. The job
        # itself re-checks the flag: a schedule left behind by a config change
        # must not be able to empty a private instance.
        if settings.demo_mode_enabled:
            from src.infrastructure.scheduler.demo_account_purge import (
                purge_demo_accounts,
            )

            scheduler.add_job(
                purge_demo_accounts,
                trigger="cron",
                hour=settings.demo_account_purge_hour,
                minute=settings.demo_account_purge_minute,
                id=SCHEDULER_JOB_DEMO_ACCOUNT_PURGE,
                name="Wipe demonstrator visitor accounts (nightly reset)",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
            logger.info(
                "demo_account_purge_scheduled",
                hour_utc=settings.demo_account_purge_hour,
                minute=settings.demo_account_purge_minute,
            )

        # Acquire leadership and start scheduler (or start background re-election).
        # All jobs are registered above — scheduler.start() is called inside the elector.
        await leader_elector.start()
    except (RuntimeError, ValueError) as exc:
        logger.error("scheduler_initialization_failed", error=str(exc), exc_info=True)

    return leader_elector
