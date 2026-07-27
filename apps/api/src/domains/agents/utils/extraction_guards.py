"""Safety guards on the actions a background extraction proposes.

The background extractors (interests, long-term memory) let an LLM emit
``create`` / ``update`` / ``delete`` actions that are applied to user data
without review. ``create`` carries a confidence field and ``update`` rewrites a
single row, but ``delete`` is checked for nothing beyond UUID validity and
ownership — no confidence floor applies to it (that asymmetry is pinned by
``tests/unit/domains/interests/test_extraction_pure_helpers.py``).

Measured on 2026-07-27, replaying 45 real production conversation windows
through the shipped interest prompt: one ordinary window — a plain "where am I
on a map" request — made the model emit **19 delete actions**, the user's
entire active interest profile. Nothing in the pipeline stood between that
generation and the data.

A runaway generation is recognisable: a single conversation turn does not
justify wiping a profile. This module turns that observation into a hard cap,
counted so the event stops being invisible.

Scope: the cap drops the destructive actions of the batch and keeps the rest.
``create``/``update`` are recoverable and individually gated elsewhere; there
is no reason to lose a legitimate one because the same answer also contained
an implausible number of deletions.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Protocol, TypeVar

import structlog

from src.infrastructure.observability.metrics_extractions import (
    extraction_action_rejected_total,
)

logger = structlog.get_logger(__name__)

ACTION_DELETE = "delete"
REASON_DELETE_CAP = "delete_cap"


class _HasAction(Protocol):
    """Duck-typed extraction action.

    Read-only attribute via ``@property`` so the Protocol is satisfied by both
    Pydantic models (settable attributes — a strict superset) and test fakes.
    Same convention as ``domains/llm_config/reasoning_validation._CapsLike``.
    """

    @property
    def action(self) -> str: ...


ActionT = TypeVar("ActionT", bound=_HasAction)


def enforce_delete_cap(
    actions: list[ActionT],
    *,
    kind: str,
    cap: int,
) -> list[ActionT]:
    """Drop every ``delete`` when the batch proposes more than ``cap`` of them.

    Below or at the cap the batch is returned unchanged, so ordinary
    maintenance ("I'm not into that any more") keeps working. Above it, the
    deletions are treated as a generation failure rather than as user intent:
    they are dropped as a block, counted under ``delete_cap`` and logged at
    warning level with the offending count.

    Args:
        actions: Parsed actions, in the order the model emitted them.
        kind: Extraction subsystem for the metric label (``interests``,
            ``memory``) — same vocabulary as
            ``post_response_extraction_scheduled_total``.
        cap: Maximum number of deletions a single extraction may apply.
            ``0`` forbids deletion entirely.

    Returns:
        The actions to apply: unchanged, or the same list without any
        ``delete``.
    """
    delete_count = sum(1 for action in actions if action.action == ACTION_DELETE)
    if delete_count <= cap:
        return actions

    kept = [action for action in actions if action.action != ACTION_DELETE]
    logger.warning(
        "extraction_delete_cap_exceeded",
        kind=kind,
        delete_count=delete_count,
        cap=cap,
        kept_actions=len(kept),
        msg=(
            "A single extraction proposed more deletions than one conversation "
            "turn can justify — dropping all of them, keeping the rest."
        ),
    )
    # Metrics emission is best-effort: an observability failure must never turn
    # a protective guard into an exception on a fire-and-forget path.
    with suppress(Exception):
        extraction_action_rejected_total.labels(kind=kind, reason=REASON_DELETE_CAP).inc(
            delete_count
        )
    return kept
