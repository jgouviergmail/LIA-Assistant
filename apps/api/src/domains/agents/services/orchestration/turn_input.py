"""What a turn hands the graph: the keys it changed, never the whole restored state.

The loader restores the checkpoint's values and shapes them for the turn — the new
message, the refreshed preferences, the turn counter, the result of a schema
migration. Passed whole as the graph input, every key was written AGAIN: the input
landed as a ``__start__`` blob of about 1 MB, and every channel took a new version
on every turn whatever it held, ``agent_results`` (600 KB) and ``registry`` (350 KB)
included (measured 2026-10-12 on production: ~40 checkpoint saves of 1 MB and more
per ReAct turn, p50 51 ms, p90 187 ms, p99 459 ms; 1.9 GB of blobs). The graph keeps
what it holds: only what changed since the restore needs to travel, and the diff is
DERIVED from a deep snapshot of the restored values, never from a list of keys a
later writer would have to remember (``plan_approved`` is set by the chat service
after the loader returns, the proactive messages are injected into the list).

What the model reads is untouched: every node assembles its context from the graph's
state, which stays complete — this changes what is written to the database between
two nodes, nothing else.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog
from langchain_core.messages import BaseMessage

__all__ = [
    "LOADED_SNAPSHOT_KEY",
    "appended_messages",
    "prepare_graph_input",
    "snapshot_loaded_state",
    "snapshot_restored_state",
    "turn_input",
]

logger = structlog.get_logger(__name__)

#: Temporary key the loader leaves on the state it returns, popped by the stream
#: before the graph runs — never a channel, like ``_interrupt_resume_data``.
LOADED_SNAPSHOT_KEY = "_loaded_snapshot"


def snapshot_loaded_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """A deep copy of the restored values, taken before the turn shapes them.

    Deep, because the turn mutates nested values in place (the turn's
    attachments are popped from ``metadata``, the messages are appended) and a
    shallow copy would read those mutations as « unchanged ». The snapshot key
    itself is never copied.

    Args:
        state: The values the checkpoint restored.

    Returns:
        An independent copy.
    """
    return copy.deepcopy({key: value for key, value in state.items() if key != LOADED_SNAPSHOT_KEY})


def snapshot_restored_state(state: MutableMapping[str, Any], run_id: str) -> None:
    """Keep the restored values on the state itself, before the turn shapes them.

    The loader calls it the moment the checkpoint's values are in hand; the
    schema migration and every later writer mutate the state in place, so the
    copy rides along under its temporary key until the stream pops it. A deep
    copy on the event loop: its cost is logged, never assumed, and a value the
    copy cannot take leaves no snapshot (the whole state travels, as before).

    Args:
        state: The restored state, mutated in place.
        run_id: The run, for the log.
    """
    started = time.perf_counter()
    try:
        snapshot = snapshot_loaded_state(state)
    except Exception as exc:  # noqa: BLE001 — an optimisation never breaks the turn
        # A value the copy cannot take: no snapshot, the turn travels whole as
        # it always did, and the fact is logged with the type, never the value.
        logger.warning("state_snapshot_failed", run_id=run_id, error=type(exc).__name__)
        return
    state[LOADED_SNAPSHOT_KEY] = snapshot
    logger.debug(
        "state_snapshot_taken",
        run_id=run_id,
        key_count=len(snapshot),
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )


def appended_messages(
    base: list[BaseMessage], current: list[BaseMessage]
) -> list[BaseMessage] | None:
    """The messages appended to ``base``, or None when its prefix changed.

    Args:
        base: The restored list.
        current: The list the turn hands over.

    Returns:
        The appended tail (possibly empty), or None when ``current`` does not
        start with ``base`` — the whole list must then travel.
    """
    if len(current) < len(base) or current[: len(base)] != base:
        return None
    return list(current[len(base) :])


def turn_input(state: Mapping[str, Any], snapshot: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """The graph input of a turn.

    Without a snapshot (a new conversation, a checkpoint that could not be read)
    the whole state travels, as before. With one, every key whose value changed
    since the restore travels, the messages reduced to those appended — the
    ``messages`` channel appends what it is handed, so the restored prefix must
    never be sent again. The snapshot key itself never travels.

    Args:
        state: The state the loader returned, shaped for the turn.
        snapshot: The restored values as ``snapshot_loaded_state`` copied them.

    Returns:
        The state itself without a snapshot; otherwise a new mapping of the
        changed keys.
    """
    if snapshot is None:
        return state
    changed: dict[str, Any] = {}
    for key, value in state.items():
        if key == LOADED_SNAPSHOT_KEY:
            continue
        if key == "messages":
            tail = appended_messages(list(snapshot.get("messages") or []), list(value or []))
            if tail is None:
                changed["messages"] = list(value)
            elif tail:
                changed["messages"] = tail
            continue
        if key not in snapshot or snapshot[key] != value:
            changed[key] = value
    return changed


def prepare_graph_input(
    state: MutableMapping[str, Any], run_id: str, resuming: bool
) -> Mapping[str, Any]:
    """Pop the snapshot the loader left and hand the graph the turn's changes.

    A resumption travels as a ``Command`` and never reads the state: the
    snapshot is dropped and the state handed back untouched, nothing logged.

    Args:
        state: The state the loader returned, as the stream holds it.
        run_id: The run, for the log.
        resuming: Whether the turn resumes an interrupt.

    Returns:
        What ``graph.astream`` receives on a normal turn.
    """
    snapshot = state.pop(LOADED_SNAPSHOT_KEY, None)
    if resuming:
        return state
    graph_input = turn_input(state, snapshot)
    logger.info(
        "graph_input_prepared",
        run_id=run_id,
        mode="delta" if snapshot is not None else "full",
        key_count=len(graph_input),
        message_count=len(graph_input.get("messages") or []),
    )
    return graph_input
