"""Actionable connector error notices for the chat stream (Lot 3 P3, ADR-134).

When a tool fails because a connector's OAuth access is broken (revoked token,
401/403 from the provider) the failure used to surface only as a generic LLM
apology — the user had no way to know the fix is one click away. This module
classifies TYPED connector exceptions (never string matching, per the tool
error taxonomy rule) into actionable notices and emits them as custom
``execution_step`` events (``step_type="tool_error"``) on the LangGraph
stream, where the frontend renders a "Reconnect" banner linking to the
connectors settings.

Two real-world signals are covered (runtime-verified 2026-07-18 — the
``ToolErrorCode.UNAUTHORIZED`` route originally planned is produced by no
connector tool and would never fire):

- ``ConnectorTokenExpiredError``: OAuth refresh rejected (``invalid_grant``) —
  the dominant path when a user revokes access or the refresh token expires.
- ``ConnectorAPIError`` with upstream 401/403 (reconnect) or 429 (rate limit).

Emission is strictly best-effort: outside a LangGraph run (skills executor,
sub-agents, tests) the writer is unavailable and the notice is skipped.
Deduplication happens in the frontend reducer (keyed by connector + action),
so emitting once per failed step is acceptable and keeps this module
stateless.
"""

from dataclasses import dataclass
from typing import Any, Literal

import structlog

from src.core.exceptions import ConnectorAPIError, ConnectorTokenExpiredError
from src.infrastructure.observability.metrics import connector_error_notices_total

logger = structlog.get_logger(__name__)

# Upstream statuses that mean "the user must re-authorize" vs "back off".
_RECONNECT_STATUSES = frozenset({401, 403})
_RATE_LIMIT_STATUS = 429


@dataclass(frozen=True)
class ConnectorNotice:
    """A classified, actionable connector failure."""

    connector_type: str
    action: Literal["reconnect", "rate_limit"]


def _get_writer() -> Any | None:
    """Return the LangGraph custom stream writer, or None outside a run.

    Mirrors the defensive pattern of ``compaction_node``: ``get_stream_writer``
    raises ``RuntimeError`` outside a LangGraph invocation (unit tests, skills
    executor) and the import itself may fail on older LangGraph versions.
    """
    try:
        from langgraph.config import get_stream_writer
    except ImportError:  # pragma: no cover - environment-dependent
        return None
    try:
        return get_stream_writer()
    except RuntimeError:
        return None


def classify_connector_exception(exc: BaseException) -> ConnectorNotice | None:
    """Classify an exception into an actionable connector notice.

    Only TYPED connector exceptions classify; anything else (transient 5xx,
    generic errors, timeouts) returns None — a wrong "reconnect" banner on a
    transient failure is worse than no banner.

    Args:
        exc: The exception raised by a tool execution path.

    Returns:
        The notice to surface, or None when the failure is not actionable.
    """
    if isinstance(exc, ConnectorTokenExpiredError):
        return ConnectorNotice(connector_type=exc.connector_type, action="reconnect")
    if isinstance(exc, ConnectorAPIError):
        if exc.upstream_status_code in _RECONNECT_STATUSES:
            return ConnectorNotice(connector_type=exc.connector_type, action="reconnect")
        if exc.upstream_status_code == _RATE_LIMIT_STATUS:
            return ConnectorNotice(connector_type=exc.connector_type, action="rate_limit")
    return None


def emit_connector_notice_for_exception(exc: BaseException, tool_name: str) -> bool:
    """Classify and emit a connector notice on the custom stream (best-effort).

    Structured data only — the frontend resolves labels/messages client-side
    from ``connector_type`` and ``action`` (backend never bakes translated
    strings into stream payloads).

    Args:
        exc: The exception raised by the tool execution path.
        tool_name: The failing tool, for observability and display context.

    Returns:
        True when a notice was emitted, False otherwise (not actionable or
        writer unavailable).
    """
    notice = classify_connector_exception(exc)
    if notice is None:
        return False

    writer = _get_writer()
    if writer is None:
        logger.debug(
            "connector_notice_writer_unavailable",
            connector_type=notice.connector_type,
            action=notice.action,
            tool_name=tool_name,
        )
        return False

    writer(
        {
            "type": "execution_step",
            "step_type": "tool_error",
            "metadata": {
                "connector_type": notice.connector_type,
                "action": notice.action,
                "tool_name": tool_name,
            },
        }
    )
    connector_error_notices_total.labels(
        connector_type=notice.connector_type, action=notice.action
    ).inc()
    logger.info(
        "connector_error_notice_emitted",
        connector_type=notice.connector_type,
        action=notice.action,
        tool_name=tool_name,
    )
    return True
