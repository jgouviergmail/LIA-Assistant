"""Bounded World metrics: rule family, finite outcome and record area only, never accounts or rounds."""

from prometheus_client import Counter, Histogram

from src.core.constants import WORLD_ARCADE_BOT_MAX_NODES

world_game_commands_total = Counter(
    "world_game_commands_total",
    "Authoritative game command outcomes, including explicit refusals",
    ["game", "outcome"],
)
world_game_compute_seconds = Histogram(
    "world_game_compute_seconds",
    "Bounded computer preparation latency outside authority and SQL locks",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 3),
)
world_game_compute_fallback_total = Counter(
    "world_game_compute_fallback_total", "Legal low-cost computer fallback", ["reason"]
)
world_game_compute_nodes = Histogram(
    "world_game_compute_nodes",
    "Charged computer search children per prepared action",
    buckets=(0, 10, 50, 100, 500, 1000, 3000, WORLD_ARCADE_BOT_MAX_NODES),
)
# A server defect, expected 0: a transition produced a record the strict reader
# refuses. The area is a top-level authority field (bounded by the model), never
# a value; the refused rule's code is in the error log line.
world_authority_integrity_failures_total = Counter(
    "world_authority_integrity_failures_total",
    "Post-transition World authority records refused before publication",
    ["area"],
)
