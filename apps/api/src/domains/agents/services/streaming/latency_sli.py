"""The chat's latency SLIs measure a PERSON's wait — and nothing else.

``sse_time_to_first_token_seconds`` and ``sse_streaming_duration_seconds`` say
how long someone waits for an answer to start and to finish; the core alert
``SSELatencyP95High`` reads the first. Every out-of-turn run — a routine, a
ticket, the relay of a finished call — streams through the same code and used
to feed them too, although nobody is waiting for its first token. Measured on
production 2026-10-18: three morning routines fed one to two observations per
ten minutes, every one above 90 s, and the alert fired every morning from
2026-09-19 on (29 incidents) — a p95 computed over a single sample, of a wait
nobody had.

The out-of-turn funnel (``infrastructure/scheduler/out_of_turn_run``) declares,
for the whole run, whether a person waits (only a live phone delegation does:
the person is on the line); the stream observes the two histograms only when
one does. An ordinary chat turn needs no declaration: the default is a person.

The same door feeds the JOURNEY histograms (spec 2026-10-21, O1 and C1): they
start with the request rather than the graph, so the wait before the graph —
its phases, the first answer token after them, and the turns that ended
without one — is a person's wait too, and a routine never feeds it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

from src.infrastructure.observability.metrics_agents import (
    sse_streaming_duration_seconds,
    sse_time_to_first_token_seconds,
)
from src.infrastructure.observability.metrics_chat_journey import (
    chat_journey_first_token_seconds,
    chat_journey_unanswered_seconds,
    chat_pre_graph_phase_seconds,
)

PreGraphPhase = Literal["conversation", "state", "archive", "mcp", "catalogue"]
UnansweredOutcome = Literal["cancelled", "error", "interrupted"]

_person_waiting_ctx: ContextVar[bool] = ContextVar("stream_person_waiting", default=True)


@contextmanager
def awaited_by_a_person(waiting: bool) -> Iterator[None]:
    """Declare, for every turn run inside, whether a person waits for it.

    Args:
        waiting: True when someone waits for the answer (a chat turn, a live
            phone delegation); False for a run the server consumes alone.

    Yields:
        Nothing; the declaration is undone on exit, so it never leaks into
        the next turn the task runs.
    """
    token = _person_waiting_ctx.set(waiting)
    try:
        yield
    finally:
        _person_waiting_ctx.reset(token)


def a_person_is_waiting() -> bool:
    """Whether a person waits for the turn being streamed.

    Returns:
        False only inside a run that declared nobody waits.
    """
    return _person_waiting_ctx.get()


def observe_first_token(intention: str, seconds: float) -> None:
    """Record the time to the first token, when someone waited for it.

    Args:
        intention: The router's intention label.
        seconds: From the start of the stream to its first answer token.
    """
    if a_person_is_waiting():
        sse_time_to_first_token_seconds.labels(intention=intention).observe(seconds)


def observe_stream_duration(intention: str, seconds: float) -> None:
    """Record the whole stream's duration, when someone waited for it.

    Args:
        intention: The router's intention label.
        seconds: From the start of the stream to its end.
    """
    if a_person_is_waiting():
        sse_streaming_duration_seconds.labels(intention=intention).observe(seconds)


def observe_pre_graph_phase(phase: PreGraphPhase, seconds: float) -> None:
    """Record one phase of the wait before the graph starts, when someone waited for it.

    Args:
        phase: Which pre-graph step: the conversation setup, the state load
            with its attachments, the archived request, the MCP preparation or
            the turn's catalogue.
        seconds: How long the phase took.
    """
    if a_person_is_waiting():
        chat_pre_graph_phase_seconds.labels(phase=phase).observe(seconds)


def observe_journey_first_token(seconds: float) -> None:
    """Record the wait from the request to its first answer token, when someone waited.

    Args:
        seconds: From the start of the request — before the conversation
            setup and the MCP preparation — to the first answer token.
    """
    if a_person_is_waiting():
        chat_journey_first_token_seconds.observe(seconds)


def observe_journey_unanswered(outcome: UnansweredOutcome, seconds: float) -> None:
    """Record a turn that ended without an answer token, when someone waited.

    Args:
        outcome: Why it ended: the person left, the turn failed, or it asked
            a question instead of answering.
        seconds: How long the person had waited when it ended.
    """
    if a_person_is_waiting():
        chat_journey_unanswered_seconds.labels(outcome=outcome).observe(seconds)
