"""Prometheus metrics for the wait a person has before a chat turn reaches its graph.

``sse_time_to_first_token_seconds`` starts when the graph starts, so everything
a turn does BEFORE it — opening the conversation, restoring the state,
archiving the request, preparing the person's MCP servers, filtering the turn's
catalogue — was invisible to every latency signal. The MCP preparation alone
reached p95 19 s in production (spec 2026-10-21 §0ter): a person waited, and
no histogram said why.

Read only through the door in ``domains/agents/services/streaming/latency_sli``,
which observes a turn only when a person waits for it. Kept out of
``metrics_agents`` so that frozen module does not grow past its cap.
"""

from __future__ import annotations

from prometheus_client import Histogram

# From an instant reply to the slowest answer a person still waits for.
_JOURNEY_BUCKETS = [
    0.25,
    0.5,
    1.0,
    2.0,
    3.0,
    5.0,
    7.5,
    10.0,
    15.0,
    20.0,
    30.0,
    45.0,
    60.0,
    90.0,
    120.0,
    180.0,
    300.0,
]

chat_journey_first_token_seconds = Histogram(
    "chat_journey_first_token_seconds",
    "From the chat request to its first answer token, pre-graph preparation included",
    buckets=_JOURNEY_BUCKETS,
)

# Bounded label: cancelled | error | interrupted (a turn that asked instead of answering).
chat_journey_unanswered_seconds = Histogram(
    "chat_journey_unanswered_seconds",
    "How long a person waited on a chat turn that ended without an answer token",
    ["outcome"],
    buckets=_JOURNEY_BUCKETS,
)

# Bounded label: the five phases are a closed vocabulary owned by the door.
chat_pre_graph_phase_seconds = Histogram(
    "chat_pre_graph_phase_seconds",
    "Duration of each pre-graph phase of a chat turn a person waits for",
    ["phase"],
    # From a cached read (ms) to an MCP preparation bounded by its ceiling (20 s).
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0],
)
