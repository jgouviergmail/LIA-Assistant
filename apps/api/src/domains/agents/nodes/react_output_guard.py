"""A model output cut at its budget is neither an answer nor a plan (ADR-275, amended).

``react_call_model_node`` writes each model reply to ``messages``: the thread,
checkpointed and replayed to every later call of the account's conversation. A
reply the provider stopped at its output budget has no place there. Its text
stops wherever the budget fell — measured on 2026-09-25, 71 822 characters and
no tool call; its tool calls may be the unfinished half of a plan. Kept, it was
copied verbatim by the model into later turns of the thread — seven routines out
of seven the next morning — while every register called those turns a success.

So the node hands its reply to :func:`model_call_update`. A complete reply is
written as before. A cut one is refused: counted, shown on the turn's panel,
logged by its facts, and only the flag that ends the loop is written —
``react_exit_reason`` reads it, one predicate for the router and the finalize
node (ADR-248 invariant 2). The call itself stays charged: it ran, and the
provider billed it.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import AIMessage

from src.core.turn_verdicts import note_verdict
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.llm.output_truncation import is_output_truncated
from src.infrastructure.llm.usage_metadata import reasoning_tokens_of, tokens_from_response
from src.infrastructure.observability.metrics_react import react_output_truncated_total

logger = structlog.get_logger(__name__)

__all__ = ["model_call_update"]


def model_call_update(
    response: AIMessage, *, iteration: int, elapsed_seconds: float
) -> dict[str, Any]:
    """The state update of one model call of the loop.

    Args:
        response: The model's reply, as the stream aggregated it.
        iteration: The loop's iteration counter BEFORE this call.
        elapsed_seconds: The turn's reasoning seconds, this call included
            (ADR-170: compute time, never the wall clock).

    Returns:
        The reply under ``messages`` when it is complete; the
        ``react_output_truncated`` flag instead when the provider cut it. Both
        advance the iteration and charge the seconds.
    """
    update: dict[str, Any] = {
        "react_iteration": iteration + 1,
        "react_elapsed_seconds": elapsed_seconds,
    }
    if not is_output_truncated(response):
        update["messages"] = [response]
        return update

    react_output_truncated_total.inc()
    note_verdict("output_truncated", "react_agent")
    # Facts only (ADR-317): the text is the model's, the calls' arguments the person's.
    logger.warning(
        "react_output_truncated",
        iteration=iteration + 1,
        output_tokens=tokens_from_response(response).completion,
        reasoning_tokens=reasoning_tokens_of(response),
        content_chars=len(coerce_content_to_text(response.content)),
        tool_calls=len(response.tool_calls),
        invalid_tool_calls=len(response.invalid_tool_calls),
    )
    update["react_output_truncated"] = True
    return update
