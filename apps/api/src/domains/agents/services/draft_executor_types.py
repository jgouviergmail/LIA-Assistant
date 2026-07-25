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


def register_executor(draft_type: str, executor_fn: ExecutorFn) -> None:
    """Register an executor function for a draft type.

    Args:
        draft_type: Draft type string (email, event, contact, ...).
        executor_fn: Async function(draft_content, user_id, deps) -> result dict.
    """
    EXECUTOR_REGISTRY[draft_type] = executor_fn
    logger.debug(
        "draft_executor_registered",
        draft_type=draft_type,
        executor_fn=executor_fn.__name__,
    )
