"""
Compaction node: Intelligent conversation history summarization.

Runs as the entry point of the LangGraph graph, before the router.
Checks if conversation history exceeds the dynamic token threshold,
and if safe, replaces old messages with a concise LLM-generated summary.

Also handles the /resume command to force compaction regardless of threshold.

Key design: The summary is injected as a SystemMessage (not HumanMessage)
so the router does not interpret it as a user action request. For /resume,
a short conversational HumanMessage asks the assistant to confirm compaction.

Phase: F4 — Intelligent Context Compaction
Created: 2026-03-16
"""

import time
from collections.abc import Callable
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.constants import (
    COMPACTION_SSE_STEP_TYPE,
    COMPACTION_SUMMARY_MARKER,
    COMPACTION_UI_ESTIMATE_CHARS_PER_TOKEN,
    COMPACTION_UI_ESTIMATE_MAX_SECONDS,
    COMPACTION_UI_ESTIMATE_SECONDS_PER_CHUNK,
    COMPACTION_UI_ESTIMATE_TOKENS_PER_CHUNK,
)
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.models import MessagesState
from src.domains.agents.services.compaction_service import CompactionService
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_compaction import (
    compaction_skipped_total,
    compaction_writer_unavailable_total,
)

# LangGraph 1.x publishes a per-node writer (`get_stream_writer`) that lets a
# node push payloads through the `"custom"` stream_mode. The import is wrapped
# defensively so the node still works in unit tests / older LangGraph versions
# where the symbol is unavailable.
try:
    from langgraph.config import get_stream_writer
except ImportError:  # pragma: no cover - defensive
    get_stream_writer = None

logger = get_logger(__name__)

# Command that triggers forced compaction
_RESUME_COMMAND = "/resume"


def _safe_writer() -> Callable[[dict[str, Any]], None]:
    """Return a writer callable, or a no-op when the stream writer is unavailable.

    `get_stream_writer()` raises `RuntimeError` outside a LangGraph run (eg in
    unit tests that call `compaction_node` directly). Falling back to a no-op
    keeps the node testable without injecting test-only branches into the
    production code. The fallback is logged at WARNING so a misconfiguration
    in production (eg. graph not running with `stream_mode=["custom"]`) does
    not silently swallow the start/done UI events.
    """
    if get_stream_writer is None:
        logger.warning(
            "compaction_writer_unavailable",
            reason="get_stream_writer_import_failed",
        )
        compaction_writer_unavailable_total.labels(reason="get_stream_writer_import_failed").inc()
        return lambda _chunk: None
    try:
        return get_stream_writer()
    except Exception as e:
        logger.warning(
            "compaction_writer_unavailable",
            reason="get_stream_writer_raised",
            error_type=type(e).__name__,
            error=str(e),
        )
        compaction_writer_unavailable_total.labels(reason="get_stream_writer_raised").inc()
        return lambda _chunk: None


def _estimate_compaction_seconds(messages: list[BaseMessage]) -> int:
    """Heuristic estimate of compaction duration for the UI progress hint.

    Approximates the number of LLM chunks needed and applies a p50 per-chunk
    wall-clock. Capped so the UI never displays an estimate larger than the
    global compaction budget minus the safety margin. All thresholds are
    centralised in `src/core/constants.py` so they stay aligned with the LLM
    chunk size and the global timeout.

    Args:
        messages: The conversation history about to be compacted.

    Returns:
        Estimated wall-clock duration in whole seconds, capped at
        `COMPACTION_UI_ESTIMATE_MAX_SECONDS`.
    """
    total_chars = sum(len(str(m.content)) for m in messages)
    approx_tokens = total_chars // COMPACTION_UI_ESTIMATE_CHARS_PER_TOKEN
    chunks = max(1, approx_tokens // COMPACTION_UI_ESTIMATE_TOKENS_PER_CHUNK)
    return min(
        COMPACTION_UI_ESTIMATE_MAX_SECONDS,
        chunks * COMPACTION_UI_ESTIMATE_SECONDS_PER_CHUNK,
    )


def _is_resume_command(messages: list[BaseMessage]) -> bool:
    """Check if the last user message is the /resume command."""
    if not messages:
        return False
    last_msg = messages[-1]
    if not isinstance(last_msg, HumanMessage):
        return False
    content = last_msg.text
    return content.strip().lower() == _RESUME_COMMAND


async def compaction_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """
    LangGraph node for context compaction.

    Logic:
    1. If disabled → pass-through (return empty dict)
    2. If /resume command → force compaction (skip threshold check)
    3. If should_compact() and is_safe_to_compact() → compact
    4. Otherwise → pass-through

    When compaction occurs:
    - Old messages are removed via RemoveMessage
    - Summary is injected as a SystemMessage (context, not routed)
    - For /resume: a conversational HumanMessage triggers confirmation response
    - For auto-trigger: the real user message is in preserved recent messages
    - The /resume message is consumed (not forwarded to router)

    Returns:
        Dict with updated state fields, or empty dict for pass-through.

    Raises:
        RuntimeError: When the run carries no typed runtime context. This node is
            the graph's entry point, so the check lands here rather than deep in a
            tool: with ``context_schema`` declared but no context supplied, a run —
            including a resume after a HITL interrupt — otherwise succeeds
            SILENTLY and every node reads ``None`` (measured; ADR-231, ADR-085).
    """
    runtime_context_if_running()

    if not settings.compaction_enabled:
        return {}

    messages: list[BaseMessage] = state.get("messages", [])
    if not messages:
        return {}

    service = CompactionService()
    is_resume = _is_resume_command(messages)

    # Determine if compaction is needed
    force_compact = is_resume
    should_compact = force_compact or service.should_compact(messages)

    if not should_compact:
        return {}

    # Safety check: don't compact if HITL state would be corrupted
    safety = service.is_safe_to_compact(state)
    if not safety.safe:
        logger.info(
            "compaction_skipped_unsafe",
            reason=safety.reason,
            is_resume=is_resume,
        )
        # If /resume was the command but we can't compact, still consume it
        if is_resume:
            return _consume_resume_command(messages, safety.reason)
        return {}

    # Perform compaction
    language = state.get("user_language", "en")
    preserve_n = settings.compaction_preserve_recent_messages

    # Emit `compaction_start` so the frontend can lock the chat input and show
    # a progress banner (Day 2 — Task 2.2). The chunk reaches the SSE stream
    # via the `"custom"` stream_mode handler added in Task 2.1.
    writer = _safe_writer()
    start_monotonic = time.monotonic()
    writer(
        {
            "type": "execution_step",
            "step_type": COMPACTION_SSE_STEP_TYPE,
            "step_label": "compaction_start",
            "metadata": {
                "phase": "start",
                "estimated_duration_seconds": _estimate_compaction_seconds(messages),
                "is_resume": is_resume,
            },
        }
    )

    result = await service.compact(
        messages=messages,
        preserve_recent_n=preserve_n,
        language=language,
        config=config,
    )

    if result.strategy == "noop" or not result.summary:
        # No work was done — still close the UI loop so the banner can clear.
        writer(
            {
                "type": "execution_step",
                "step_type": COMPACTION_SSE_STEP_TYPE,
                "step_label": "compaction_done",
                "metadata": {
                    "phase": "done",
                    "strategy": "noop",
                    "tokens_saved": 0,
                    "duration_ms": int((time.monotonic() - start_monotonic) * 1000),
                },
            }
        )
        if is_resume:
            return _consume_resume_command(messages, "nothing_to_compact")
        return {}

    # Emit `compaction_done` with the real outcome (strategy, tokens saved,
    # duration). Truncation fallback uses `strategy="truncation"` so the
    # frontend can display the explicit "older conversation truncated" banner.
    writer(
        {
            "type": "execution_step",
            "step_type": COMPACTION_SSE_STEP_TYPE,
            "step_label": "compaction_done",
            "metadata": {
                "phase": "done",
                "strategy": result.strategy,
                "tokens_saved": result.tokens_saved,
                "duration_ms": int((time.monotonic() - start_monotonic) * 1000),
            },
        }
    )

    # Build the new message list:
    # 1. RemoveMessage for each old message that was compacted
    # 2. SystemMessage with the summary (context only — NOT routed by router)
    # 3. For /resume: conversational HumanMessage to trigger confirmation
    compacted_count = state.get("compaction_count", 0) + 1

    # Identify messages to remove (all non-system, non-recent messages)
    non_system = [m for m in messages if not isinstance(m, SystemMessage)]
    preserve_n_effective = min(preserve_n, len(non_system))
    to_remove = non_system[:-preserve_n_effective] if preserve_n_effective > 0 else non_system

    new_messages: list[BaseMessage] = []

    # Remove old messages
    for msg in to_remove:
        if hasattr(msg, "id") and msg.id:
            new_messages.append(RemoveMessage(id=msg.id))

    # v2 (Task 1.5): also remove prior "compaction #N" SystemMessages IFF the
    # new summary actually consolidated them. On truncation fallback (or any
    # path where the service did not merge them in), we leave them in place
    # so the conversation does not lose information v1 had preserved.
    if settings.compaction_include_previous_summaries and getattr(
        result, "consolidated_previous_summaries", False
    ):
        for m in messages:
            content = m.content if isinstance(m, SystemMessage) else None
            if (
                isinstance(content, str)
                and content.startswith(COMPACTION_SUMMARY_MARKER)
                and getattr(m, "id", None)
            ):
                new_messages.append(RemoveMessage(id=m.id))

    # If /resume, also remove the /resume message itself
    if is_resume and messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "id") and last_msg.id:
            new_messages.append(RemoveMessage(id=last_msg.id))

    # Summary as SystemMessage — provides context without triggering router actions.
    # The router takes messages[-1] as the user query; a SystemMessage won't be picked up.
    summary_system = SystemMessage(
        content=(
            f"{COMPACTION_SUMMARY_MARKER} — compaction #{compacted_count}. "
            f"{result.tokens_saved} tokens saved. "
            f"Strategy: {result.strategy}.]\n\n{result.summary}"
        ),
    )
    new_messages.append(summary_system)

    # For /resume: add a conversational HumanMessage so the router routes to response_node
    # and the assistant confirms the compaction to the user.
    if is_resume:
        new_messages.append(
            HumanMessage(
                content=(
                    f"Conversation history has been compacted "
                    f"({result.tokens_saved} tokens saved). "
                    f"Please confirm this to me briefly."
                ),
            )
        )

    logger.info(
        "compaction_node_applied",
        messages_removed=len(to_remove),
        tokens_saved=result.tokens_saved,
        strategy=result.strategy,
        compaction_count=compacted_count,
        is_resume=is_resume,
    )

    return {
        "messages": new_messages,
        "compaction_summary": result.summary,
        "compaction_count": compacted_count,
        # Debug panel (`compaction` section): the strategy and savings only
        # existed in logs/SSE events — the panel needs them in state.
        "compaction_debug": {
            "strategy": result.strategy,
            "tokens_saved": result.tokens_saved,
            "messages_removed": len(to_remove),
        },
    }


def _consume_resume_command(messages: list[BaseMessage], reason: str) -> dict[str, Any]:
    """
    Consume the /resume command without compacting.

    Replaces /resume with a conversational message so the router
    routes to response_node for a confirmation instead of trying to act.
    """
    new_messages: list[BaseMessage] = []

    # Remove the /resume message
    last_msg = messages[-1]
    if hasattr(last_msg, "id") and last_msg.id:
        new_messages.append(RemoveMessage(id=last_msg.id))

    # Replace with conversational message — router will route to response_node
    new_messages.append(
        HumanMessage(content=f"Context compaction was skipped ({reason}). Please let me know.")
    )

    compaction_skipped_total.labels(reason=f"resume_{reason}").inc()

    return {"messages": new_messages}
