"""
Proactive Task Infrastructure.

Generic, reusable infrastructure for all proactive tasks:
- Interest notifications
- Birthday reminders
- Weekly summaries
- Event reminders
- etc.

Architecture:
    ProactiveTask (Protocol)
        ↓
    ProactiveTaskRunner (Orchestrator)
        ├── EligibilityChecker (timezone, quota, cooldown, activity)
        ├── NotificationDispatcher (FCM + SSE + archive)
        └── track_proactive_tokens() (TrackingContext wrapper)

Usage:
    1. Implement ProactiveTask protocol for your specific task
    2. Register scheduler job with ProactiveTaskRunner
    3. Runner handles all common logic (eligibility, dispatch, tokens)

Example:
    >>> from src.infrastructure.proactive import ProactiveTaskRunner, ProactiveTask
    >>>
    >>> class MyProactiveTask:
    ...     task_type = "my_task"
    ...     async def check_eligibility(self, user_id, settings, now): ...
    ...     async def select_target(self, user_id): ...
    ...     async def generate_content(self, user_id, target, language): ...
    ...     async def on_feedback(self, user_id, target, feedback): ...
    >>>
    >>> runner = ProactiveTaskRunner(task=MyProactiveTask())
    >>> stats = await runner.execute()

"""

from src.infrastructure.proactive.base import (
    ContentSource,
    ProactiveTask,
    ProactiveTaskResult,
)
from src.infrastructure.proactive.eligibility import (
    EligibilityChecker,
    EligibilityReason,
    EligibilityResult,
)
from src.infrastructure.proactive.notification import (
    NotificationDispatcher,
    NotificationResult,
)
from src.infrastructure.proactive.runner import (
    ProactiveTaskRunner,
    RunnerStats,
    execute_proactive_task,
)
from src.infrastructure.proactive.tracking import (
    TokenAccumulator,
    track_proactive_tokens,
    track_proactive_tokens_from_result,
)

__all__ = [
    # Base types
    "ProactiveTask",
    "ProactiveTaskResult",
    "ContentSource",
    # Runner
    "ProactiveTaskRunner",
    "RunnerStats",
    "execute_proactive_task",
    # Eligibility
    "EligibilityChecker",
    "EligibilityResult",
    "EligibilityReason",
    # Notification
    "NotificationDispatcher",
    "NotificationResult",
    # Tracking
    "track_proactive_tokens",
    "track_proactive_tokens_from_result",
    "TokenAccumulator",
]
