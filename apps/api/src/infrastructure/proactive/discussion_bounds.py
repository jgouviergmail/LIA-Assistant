"""How long a discussion run holds an account: the slots' time, never less (ADR-221).

The environment's deadlines and lease stand until a slot needs longer: a run never
ends, and its claim never lapses, before a call of ``admin-llm-config`` may.
"""

from __future__ import annotations

import math

from src.core.config import settings
from src.core.llm_config_helper import run_bound_seconds

_CONTEXT_SLOT = "discussion_context"
_SLOTS: tuple[str, ...] = (_CONTEXT_SLOT, "discussion_decision", "discussion_message")


def discussion_deadline_seconds(context_only: bool) -> float:
    """How long a run may last.

    Args:
        context_only: The run is a requested rebuild, which writes no message.

    Returns:
        The deadline, in seconds.
    """
    if context_only:
        return run_bound_seconds(settings.discussion_rebuild_deadline_seconds, _CONTEXT_SLOT)
    return run_bound_seconds(settings.discussion_run_deadline_seconds, *_SLOTS)


def discussion_lease_seconds() -> int:
    """How long a claim holds between two renewals: past the longest call it covers.

    Every read and every model call renews the claim, none during its own wait.

    Returns:
        The lease, in whole seconds.
    """
    return math.ceil(
        max(run_bound_seconds(settings.discussion_run_lease_seconds, slot) for slot in _SLOTS)
    )
