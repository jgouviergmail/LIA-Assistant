"""
Distributed locking primitives for infrastructure operations.

This module provides Redis-based distributed locks for operations that require
coordination across multiple processes/instances:
- SchedulerLock: Prevents duplicate scheduled job execution with multiple workers
"""

from src.infrastructure.locks.scheduler_lock import SchedulerLock

__all__ = ["SchedulerLock"]
