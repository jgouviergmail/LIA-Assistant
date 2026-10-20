"""Peer retention registrar extracted without changing its delivery gates."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_PEERS_DELIVERY_SWEEP
from src.infrastructure.scheduler.peer_message_delivery import sweep_pending_deliveries
from src.infrastructure.startup.scheduler_jitter import jitter_seconds_for


def register_peer_maintenance(scheduler: AsyncIOScheduler) -> None:
    """Retention runs while peers is off; the sweep gates all delivery itself."""
    scheduler.add_job(
        sweep_pending_deliveries,
        trigger="interval",
        seconds=settings.peers_delivery_sweep_seconds,
        jitter=jitter_seconds_for(seconds=settings.peers_delivery_sweep_seconds),
        id=SCHEDULER_JOB_PEERS_DELIVERY_SWEEP,
        name="Peers retention and enabled-message delivery sweep",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )
