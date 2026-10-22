"""Register the independent discussion producer on the elected native scheduler."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_PROACTIVE_DISCUSSIONS
from src.infrastructure.scheduler.proactive_discussions import process_proactive_discussions
from src.infrastructure.startup.scheduler_jitter import jitter_seconds_for


def register_discussion_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register the producer tick on the elected scheduler, jittered, one instance.

    Args:
        scheduler: The application's scheduler.
    """
    scheduler.add_job(
        process_proactive_discussions,
        trigger="interval",
        minutes=settings.discussion_interval_minutes,
        jitter=jitter_seconds_for(minutes=settings.discussion_interval_minutes),
        id=SCHEDULER_JOB_PROACTIVE_DISCUSSIONS,
        name="Initiate personal discussions",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )
