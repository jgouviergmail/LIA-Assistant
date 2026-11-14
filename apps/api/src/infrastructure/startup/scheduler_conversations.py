"""Retired runtimes remain cleanup work while discussion creation is disabled."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_CONVERSATION_CLEANUP
from src.infrastructure.scheduler.conversation_cleanup import cleanup_conversations
from src.infrastructure.startup.scheduler_jitter import jitter_seconds_for


def register_conversation_cleanup(scheduler: AsyncIOScheduler) -> None:
    """Register bounded leader work before the election starts the scheduler."""
    scheduler.add_job(
        cleanup_conversations,
        trigger="interval",
        seconds=settings.conversation_cleanup_interval_seconds,
        jitter=jitter_seconds_for(seconds=settings.conversation_cleanup_interval_seconds),
        id=SCHEDULER_JOB_CONVERSATION_CLEANUP,
        name="Cleanup retired conversation runtimes",
        replace_existing=True,
        max_instances=1,
    )
