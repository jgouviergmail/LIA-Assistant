"""The ⚙ execution trace survives a page reload — persisted with its message.

ADR-133 delivered the per-message execution trace as session-only state: the
frontend accumulates the ``execution_step`` chunks it renders live and attaches
them to the bubble at ``done`` — but a reload rebuilt history from
``message_metadata``, where no trace existed. This module closes that V2 gap by
capturing the SAME steps server-side, at the streaming chokepoint every emitted
chunk already flows through, and attaching them to the archived assistant row.

The capture rules deliberately mirror the frontend accumulator
(``sse-handlers/handlers.ts``) so the reloaded trace matches what the user saw:

- ``router_decision`` marks the turn start: reset, then seed the router step —
  a HITL resumption re-enters through a fresh ``router_decision`` and the
  persisted trace covers the answering invocation only.
- A step is kept only when it carries an ``i18n_key``: the persisted form is
  ``{emoji, i18n_key, category}`` and the label is re-resolved client-side at
  hydration. This is the PII guard as a structural property — free-text
  ``detail`` and ``reasoning`` deltas have no slot to land in.
- ``tool_error`` sub-events feed the connector notice banner, never the trace
  (same exclusion as the frontend interception).
- The cap keeps the TAIL — the most informative part of a long FOR_EACH run —
  and is settings-driven (``execution_trace_persist_max_steps``).
- What a tool step did is added up per label, as the live bubble does
  (2026-10-24): each call counted once by its ``step_key``, its latest
  outcome kept; a pipeline's per-tool total taken as it comes. Only
  INTEGERS reach storage, under ``outcome`` — calls when more than one,
  found, shown when fewer than found, failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.field_names import FIELD_EXECUTION_TRACE, FIELD_OUTCOME, FIELD_STEP_KEY
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: Categories the disclosure UI groups by; anything else degrades to "system"
#: (mirrors ``TRACE_CATEGORIES`` in ``sse-handlers/handlers.ts``).
_TRACE_CATEGORIES: frozenset[str] = frozenset({"system", "agent", "tool", "context"})

#: Sub-events that ride the ``execution_step`` channel but are not trace steps:
#: reasoning deltas (excluded by the PII guard) and connector-notice signals.
_EXCLUDED_STEP_TYPES: frozenset[str] = frozenset({"reasoning", "tool_error"})

#: Seed emitted on ``router_decision`` — the frontend seeds the same step with
#: the translated ``execution.steps.router_decision`` label (handlers.ts).
ROUTER_SEED_STEP: dict[str, str] = {
    "emoji": "🧭",
    "i18n_key": "router_decision",
    "category": "system",
}


_OUTCOME_KEYS: frozenset[str] = frozenset({"calls", "found", "shown", "failed"})


def _counts(raw: object) -> dict[str, int]:
    """The outcome's known counts, non-negative integers only — never anything else."""
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key, value in raw.items()
        if key in _OUTCOME_KEYS
        and isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    }


@dataclass
class _Tally:
    """What one label's steps did: each call's latest outcome, and a pipeline total."""

    calls: dict[str, dict[str, int]] = field(default_factory=dict)
    bulk: dict[str, int] = field(default_factory=dict)

    def add(self, metadata: dict[str, Any]) -> None:
        counts = _counts(metadata.get(FIELD_OUTCOME))
        step_key = metadata.get(FIELD_STEP_KEY)
        if step_key:
            self.calls[str(step_key)] = counts
        elif counts:
            self.bulk = counts

    def summary(self) -> dict[str, int]:
        """The counts worth showing; empty when a step only says it ran."""
        calls = len(self.calls) + self.bulk.get("calls", 0)
        found = sum(c.get("found", 0) for c in self.calls.values()) + self.bulk.get("found", 0)
        shown = sum(c.get("shown", c.get("found", 0)) for c in self.calls.values())
        shown += self.bulk.get("found", 0)
        failed = sum(c.get("failed", 0) for c in self.calls.values())
        failed += self.bulk.get("failed", 0)
        summary = {"calls": calls} if calls > 1 else {}
        if found:
            summary["found"] = found
            if shown < found:
                summary["shown"] = shown
        if failed:
            summary["failed"] = failed
        return summary


class TraceCapture:
    """Accumulate persistable trace steps across one streamed invocation.

    One instance lives on the ``StreamingService`` (one per run, like
    ``persistable_widgets``) and observes every emitted SSE chunk.
    """

    def __init__(self, max_steps: int) -> None:
        """Initialize an empty capture.

        Args:
            max_steps: Tail-keeping cap on retained steps
                (``settings.execution_trace_persist_max_steps``).
        """
        self._max_steps = max_steps
        self._steps: list[dict[str, str]] = []
        self._seen_keys: set[str] = set()
        self._tallies: dict[str, _Tally] = {}

    def observe(self, chunk_type: str, metadata: dict[str, Any] | None) -> None:
        """Feed one emitted SSE chunk into the capture.

        Args:
            chunk_type: ``ChatStreamChunk.type`` of the emitted chunk.
            metadata: The chunk's metadata dict, if any.
        """
        if chunk_type == "router_decision":
            # The router node ALSO emits an updates-mode execution_step with
            # i18n_key=router_decision — pre-marking the key mirrors the
            # frontend seed (handlers.ts) and keeps the seed unduplicated.
            self._steps = [dict(ROUTER_SEED_STEP)]
            self._seen_keys = {ROUTER_SEED_STEP["i18n_key"]}
            self._tallies = {}
            return
        if chunk_type != "execution_step" or not metadata:
            return
        if metadata.get("step_type") in _EXCLUDED_STEP_TYPES:
            return
        i18n_key = metadata.get("i18n_key")
        if not i18n_key:
            # Unpersistable without shipping free text (compaction events,
            # detail-only steps): the live bubble may show them, storage never.
            return
        key = str(i18n_key)
        self._tallies.setdefault(key, _Tally()).add(metadata)
        if key in self._seen_keys:
            # One occurrence per key per turn — the live bubble early-returns
            # on already-emitted keys (a FOR_EACH shows ONE tool step), so the
            # persisted trace must match what the user saw.
            return
        self._seen_keys.add(key)
        category = metadata.get("category")
        self._steps.append(
            {
                "emoji": metadata.get("emoji") or "⚙️",
                "i18n_key": key,
                "category": category if category in _TRACE_CATEGORIES else "system",
            }
        )
        if len(self._steps) > self._max_steps:
            self._steps = self._steps[-self._max_steps :]

    def snapshot(self) -> list[dict[str, Any]]:
        """Return the captured steps, each with what it did when there is something to say."""
        steps: list[dict[str, Any]] = []
        for step in self._steps:
            tally = self._tallies.get(step["i18n_key"])
            summary = tally.summary() if tally else {}
            steps.append({**step, FIELD_OUTCOME: summary} if summary else dict(step))
        return steps


def with_persisted_trace(
    message_metadata: dict[str, Any],
    steps: list[dict[str, Any]],
    *,
    duration_ms: int | None,
    run_id: str,
) -> dict[str, Any]:
    """Return ``message_metadata`` carrying the trace, as a NEW dict.

    Branch-free at the call site on purpose, like ``with_persisted_widgets``:
    the archive path lives inside an already very large streaming function.

    Args:
        message_metadata: Metadata being assembled for the assistant message.
        steps: Captured steps for this turn; empty is the pure-conversation
            common case (parity with the frontend: no disclosure, no storage).
        duration_ms: Wall-clock duration of the turn, when known.
        run_id: Correlates the emitted log with the rest of the turn.

    Returns:
        The input unchanged (same object) when there is nothing to attach,
        otherwise a new dict with the trace under ``FIELD_EXECUTION_TRACE``.
    """
    if not steps:
        return message_metadata
    logger.info(
        "message_execution_trace_persisted",
        run_id=run_id,
        step_count=len(steps),
        duration_ms=duration_ms,
    )
    return {
        **message_metadata,
        FIELD_EXECUTION_TRACE: {"steps": steps, "duration_ms": duration_ms},
    }
