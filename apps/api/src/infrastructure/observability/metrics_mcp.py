"""Prometheus metrics for the MCP subsystem (evolution F2, ADR-062, ADR-224).

MCP tools are discovered at runtime from third-party servers, so nothing about
them is visible in the code: which tools exist, whether they answer, and whether
they were registered at all are runtime facts. That is why the registration
failure counter lives here rather than staying a log line — a capability that
disappears silently is one nobody reports.

Extracted from ``metrics_agents`` so the MCP metrics live where the rest of the
per-domain metric modules do, and so neither file has to grow past its cap.

Instrumented in: ``infrastructure/mcp/`` (tool_adapter, user_tool_adapter,
registration, client_manager) and ``domains/agents/tools/mcp_react_tools.py``.
Reference: docs/technical/MCP_INTEGRATION.md
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

mcp_tool_invocations_total = Counter(
    "mcp_tool_invocations_total",
    "Total MCP tool invocations",
    ["server_name", "tool_name", "status"],  # status: success/error
)

mcp_tool_duration_seconds = Histogram(
    "mcp_tool_duration_seconds",
    "MCP tool execution duration",
    ["server_name", "tool_name"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

mcp_server_health = Gauge(
    "mcp_server_health",
    "MCP server connection status (1=healthy, 0=down)",
    ["server_name"],
    # livemin: across workers, a server is "healthy" only if EVERY live worker can
    # reach it — any worker that fails drives it to 0, surfacing partial outages.
    multiprocess_mode="livemin",
)

mcp_connection_errors_total = Counter(
    "mcp_connection_errors_total",
    "MCP server connection errors",
    ["server_name", "error_type"],
)

# A tool that fails to build is dropped from the registry: the assistant simply
# answers that it cannot do the thing, with nothing user-visible to say why.
# Production spent 72 h dropping 30 of one server's 40 tools on every turn
# behind a warning nobody queries (2026-09-01). Labels stay deliberately
# BOUNDED — scope is a three-value vocabulary, error_type an exception class —
# because a per-server label would add one series per user per server; the
# server and tool names travel in the log, which has no cardinality budget.
mcp_tool_registration_failures_total = Counter(
    "mcp_tool_registration_failures_total",
    "MCP tools dropped while building their adapter (a capability silently lost)",
    ["scope", "error_type"],  # scope: admin/user_standard/user_iterative
)

# ADR-062: MCP ReAct Sub-Agent metrics
mcp_react_invocations_total = Counter(
    "mcp_react_invocations_total",
    "MCP ReAct sub-agent invocations",
    ["server_name", "status"],  # status: success/error
)

mcp_react_iterations_histogram = Histogram(
    "mcp_react_iterations_histogram",
    "Number of ReAct iterations per MCP task",
    ["server_name"],
    buckets=[1, 2, 3, 5, 8, 10, 15],
)
