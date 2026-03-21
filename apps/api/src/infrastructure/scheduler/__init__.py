"""
Scheduled tasks (cron jobs) using APScheduler.

This package contains background tasks that run on schedules
(e.g., daily currency rate sync, cleanup jobs) and the leader
election mechanism for multi-worker environments.
"""

from src.infrastructure.scheduler.leader_elector import SchedulerLeaderElector

__all__ = ["SchedulerLeaderElector"]
