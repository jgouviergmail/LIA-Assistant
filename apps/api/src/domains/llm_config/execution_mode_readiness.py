"""What « auto » does on this instance, for the screens that offer it (ADR-390).

The automatic execution mode decides turn by turn only when the instance runs the
ReAct loop AND its decision usage (``JevUsage.EXECUTION_MODE``) is on and
configured. Otherwise it does one thing every time, and the screen says which:
an automatic mode that silently always loops would be a placebo.

Lives with the decision usages it reads, beside no consumer, so the preference
route (auth) and the router (agents) both read it without importing each other.
"""

from __future__ import annotations

import structlog

from src.core.config import settings
from src.core.constants import AutoModeResolution
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import load_jev_snapshot

__all__ = ["auto_resolution"]

logger = structlog.get_logger(__name__)


async def auto_resolution() -> AutoModeResolution:
    """What « auto » does on this instance.

    Without the loop the router plans every turn in the pipeline; without a usable
    decision (the usage off, no provider, a configuration that cannot be read) every
    planned « auto » turn goes to the loop.

    Returns:
        ``decided``, ``always_react`` or ``always_pipeline``.
    """
    if not settings.react_agent_enabled:
        return "always_pipeline"
    try:
        snapshot = await load_jev_snapshot(JevUsage.EXECUTION_MODE)
    except Exception as exc:  # noqa: BLE001 - an unreadable configuration decides nothing
        logger.info("execution_mode_readiness_unread", error_type=type(exc).__name__)
        return "always_react"
    if snapshot.requested and snapshot.configuration is not None:
        return "decided"
    return "always_react"
