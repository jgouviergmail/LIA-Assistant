"""A turn the model's window refused is compacted and replayed, once (lot 15).

A provider refuses a request larger than the model's window before generating
anything (``ContextOverflowError``): the outcome is KNOWN, nothing was produced.
Retrying the same turn as it was fails the same way, and the compaction that
would make it fit is triggered by a share of the RESPONSE slot's window: a slot
on a smaller window overflows before it ever runs, turn after turn.

So the turn is replayed with its compaction forced, under four rules:

- it forks from the checkpoint the turn was restored from: the refused
  attempt's writes stay on a branch nobody reads, and the replay is the turn
  exactly as the person sent it;
- the compaction is forced through the run's context, never through the state:
  the instruction cannot outlive the replay (``LiaRuntimeContext``);
- it runs only where a compaction can help: compaction on, a checkpoint to fork
  from, messages before the kept tail (``compactable_messages``, the rule the
  compaction applies), no question waiting for the person;
- it never runs when the register holds an act of the run, because a replay
  would perform it twice, and doubt counts as an act (``run_may_have_acted``).

Once: a replay the window refuses again is the turn's failure, said as such.
A resumed question is never replayed: its value is the person's answer, which
a fork would re-ask.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from dataclasses import replace
from typing import Any, Final

import structlog
from langchain_core.exceptions import ContextOverflowError
from langchain_core.runnables import RunnableConfig
from langgraph._internal._constants import CONFIG_KEY_CHECKPOINT_ID

from src.core.config import settings
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.effects.replay_guard import run_may_have_acted
from src.domains.agents.services.compaction_service import (
    CompactionService,
    compactable_messages,
)
from src.domains.agents.services.orchestration.turn_input import fresh_run_config
from src.infrastructure.observability.metrics_compaction import (
    compaction_overflow_replays_total,
)

__all__ = ["GRAPH_STREAM_MODES", "replay_refusal", "stream_fresh_turn"]

logger = structlog.get_logger(__name__)

#: What the chat stream reads from a run. ``custom`` carries the nodes' own
#: events (the compaction's start and done, among others).
GRAPH_STREAM_MODES: Final[list[str]] = ["values", "messages", "updates", "custom"]


async def replay_refusal(
    state: Mapping[str, Any], *, run_id: str, restored_checkpoint_id: str | None
) -> str | None:
    """Why the refused turn cannot be replayed, or None when it may be.

    The facts the turn already holds are asked first; the register, a database
    read, only when they all allow a replay.

    Args:
        state: The state the turn started from, its request last.
        run_id: The run, whose acts the register holds.
        restored_checkpoint_id: The checkpoint the turn was restored from.

    Returns:
        The refusal reason, or None.
    """
    if not settings.compaction_enabled:
        return "compaction_disabled"
    if restored_checkpoint_id is None:
        return "no_checkpoint"
    messages = list(state.get("messages") or [])
    if not compactable_messages(messages, settings.compaction_preserve_recent_messages):
        return "nothing_to_compact"
    if CompactionService.pending_question(state) is not None:
        return "hitl_pending"
    if await run_may_have_acted(run_id):
        return "acted"
    return None


def _replay_config(config: RunnableConfig, checkpoint_id: str) -> RunnableConfig:
    """A fresh run forking from the checkpoint the turn was restored from."""
    fresh = fresh_run_config(config)
    configurable = {**(fresh.get("configurable") or {}), CONFIG_KEY_CHECKPOINT_ID: checkpoint_id}
    return {**fresh, "configurable": configurable}


async def stream_fresh_turn(
    graph: Any,
    graph_input: Mapping[str, Any],
    config: RunnableConfig,
    context: LiaRuntimeContext,
    *,
    state: Mapping[str, Any],
    run_id: str,
    restored_checkpoint_id: str | None,
) -> AsyncGenerator[tuple[str, Any]]:
    """Stream a new turn; replay it once, compacted, if the model's window refuses it.

    Args:
        graph: The compiled graph.
        graph_input: What the turn hands the graph (``turn_input``).
        config: The run's config.
        context: The run's typed context.
        state: The state the turn started from, its request last.
        run_id: The run.
        restored_checkpoint_id: The checkpoint the turn was restored from.

    Yields:
        The graph's ``(mode, chunk)`` items, the replay's after the refused
        attempt's.

    Raises:
        ContextOverflowError: The turn could not be replayed, or the replay was
            refused too.
    """
    try:
        async for item in graph.astream(
            graph_input,
            fresh_run_config(config),
            stream_mode=GRAPH_STREAM_MODES,
            context=context,
            durability="async",
        ):
            yield item
        return
    except ContextOverflowError:
        refusal = await replay_refusal(
            state, run_id=run_id, restored_checkpoint_id=restored_checkpoint_id
        )
        if refusal is not None:
            compaction_overflow_replays_total.labels(outcome=f"refused_{refusal}").inc()
            logger.warning("context_overflow_replay_refused", run_id=run_id, reason=refusal)
            raise
    assert restored_checkpoint_id is not None  # replay_refusal answered no_checkpoint otherwise
    compaction_overflow_replays_total.labels(outcome="replayed").inc()
    logger.warning("context_overflow_replaying", run_id=run_id)
    try:
        async for item in graph.astream(
            graph_input,
            _replay_config(config, restored_checkpoint_id),
            stream_mode=GRAPH_STREAM_MODES,
            context=replace(context, compaction_forced=True),
            durability="async",
        ):
            yield item
    except ContextOverflowError:
        compaction_overflow_replays_total.labels(outcome="replay_overflowed").inc()
        raise
