"""Draft-executor registry primitives (leaf module).

Holds the executor registry and its ``register_executor`` accessor, and
nothing else. It exists to break the cycle between the execution engine
(``draft_executor``) and the module that populates the registry by importing
the whole tool surface (``draft_executor_registry``): both depend on this leaf,
neither depends on the other at import time.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

# Executor signature: (draft_content, user_id, deps) -> result dict
ExecutorFn = Callable[[dict[str, Any], UUID, Any], Coroutine[Any, Any, dict[str, Any]]]

# Registry of executor functions per draft type, populated lazily on first use.
EXECUTOR_REGISTRY: dict[str, ExecutorFn] = {}

#: Executors whose effect is recorded by the TOOL they replay, not by
#: themselves (ADR-263). Gating them too would claim a second row for one
#: effect — and both claims would share the scope key, so the inner call would
#: be mistaken for a replay and never run. A closed list, asserted by a test:
#: an exemption is declared, never inherited from a flag someone passed.
EXECUTORS_GATED_BY_THEIR_TOOL: frozenset[str] = frozenset({"tool_call"})


def register_executor(draft_type: str, executor_fn: ExecutorFn) -> None:
    """Register an executor function for a draft type.

    Args:
        draft_type: Draft type string (email, event, contact, ...).
        executor_fn: Async function(draft_content, user_id, deps) -> result dict.
    """
    # ADR-263: a confirmed draft is where the effect actually happens, so the
    # gate is installed here for the same reason it is installed on a tool at
    # registration — one door, not a call every caller must remember.
    from src.domains.agents.effects.runtime import gated_executor

    if draft_type in EXECUTORS_GATED_BY_THEIR_TOOL:
        EXECUTOR_REGISTRY[draft_type] = executor_fn
    else:
        EXECUTOR_REGISTRY[draft_type] = gated_executor(draft_type, executor_fn)
    logger.debug(
        "draft_executor_registered",
        draft_type=draft_type,
        executor_fn=executor_fn.__name__,
    )
