"""Typed failure extraction from what a run ALREADY carries.

No new state key on purpose (design note over spec §5.3): the pipeline's
``completed_steps`` and ReAct's ToolMessages already hold every failure of the
turn, and both survive checkpoints today. These pure readers turn them into
bounded, typed entries — error CODE and a truncated message head, never raw
payloads or log text — for the response node's honesty block. The user-facing
explanation derives from these typed classifications only (ADR-182/184).
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.messages import BaseMessage, ToolMessage

from src.domains.diagnostics.advisor import (
    format_degradations_block,
    get_active_degradations,
)

logger = structlog.get_logger(__name__)

#: Bound on extracted entries: enough to explain a turn, never a dump.
MAX_FAILURES = 10

#: Bound on the message head kept per failure.
_MESSAGE_HEAD_CHARS = 160


def _head(text: object) -> str:
    """First characters of a message-ish value (bounded, never None)."""
    return str(text or "")[:_MESSAGE_HEAD_CHARS]


def extract_failures_from_steps(
    completed_steps: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Typed failures from the pipeline's completed_steps.

    Args:
        completed_steps: The state's step results (may be None/malformed —
            this reader never raises).

    Returns:
        At most MAX_FAILURES entries: {source, agent, error_code, message}.
    """
    failures: list[dict[str, str]] = []
    for step_id, step in (completed_steps or {}).items():
        if len(failures) >= MAX_FAILURES:
            break
        if not isinstance(step, dict) or step.get("status") != "error":
            continue
        result = step.get("result")
        error_payload = result.get("error") if isinstance(result, dict) else None
        if isinstance(error_payload, dict):
            code = str(error_payload.get("code", "UNKNOWN"))
            message = _head(error_payload.get("message") or step.get("error"))
        else:
            code = "UNKNOWN"
            message = _head(step.get("error"))
        failures.append(
            {
                "source": str(step_id),
                "agent": str(step.get("agent", "")),
                "error_code": code,
                "message": message,
            }
        )
    return failures


def extract_failures_from_tool_messages(
    messages: list[BaseMessage],
) -> list[dict[str, str]]:
    """Typed failures from ReAct ToolMessages carrying a failed JSON payload.

    Args:
        messages: The conversation messages of the run.

    Returns:
        At most MAX_FAILURES entries: {source, tool, error_code, message}.
    """
    failures: list[dict[str, str]] = []
    for message in messages:
        if len(failures) >= MAX_FAILURES:
            break
        if not isinstance(message, ToolMessage):
            continue
        try:
            payload = json.loads(str(message.content))
        except json.JSONDecodeError, TypeError, ValueError:
            continue
        if not isinstance(payload, dict) or payload.get("success") is not False:
            continue
        failures.append(
            {
                "source": "react_tool",
                "tool": str(getattr(message, "name", "") or ""),
                "error_code": str(payload.get("error_code") or payload.get("error", "UNKNOWN"))[
                    :64
                ],
                "message": _head(payload.get("message") or payload.get("error")),
            }
        )
    return failures


async def build_runtime_failures_directive(
    *,
    completed_steps: dict[str, Any] | None,
    messages: list[BaseMessage],
    template: str,
) -> str:
    """The response-synthesis honesty block, or "" when the turn was clean.

    Merges the typed failures of both execution modes with the advisor's
    degradations, wrapped in the versioned directive prompt. The advisor is
    best-effort (its own contract is fail-open); the typed failures render
    with or without it.

    Args:
        completed_steps: Pipeline step results from the state (may be None).
        messages: The run's messages (ReAct ToolMessages are read).
        template: The versioned directive template, loaded by the CALLER —
            injected so this domain never imports the agents prompt loader
            (F009: no diagnostics→agents runtime edge).

    Returns:
        The formatted directive, or an EMPTY STRING when there is nothing to
        say (zero tokens on a clean turn — spec commitment).
    """
    failures = extract_failures_from_steps(completed_steps)
    failures += extract_failures_from_tool_messages(messages)[: MAX_FAILURES - len(failures)]
    try:
        degradations_block = format_degradations_block(await get_active_degradations())
    except Exception as exc:
        logger.debug("runtime_failures_advisor_unavailable", error=str(exc))
        degradations_block = ""
    if not failures and not degradations_block:
        return ""
    return template.format(
        failures_json=json.dumps(failures, ensure_ascii=False),
        degradations_block=degradations_block,
    )
