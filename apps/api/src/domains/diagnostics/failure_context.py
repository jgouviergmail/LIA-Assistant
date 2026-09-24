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
from collections.abc import Mapping
from typing import Any

import structlog
from langchain_core.messages import BaseMessage, ToolMessage

from src.core.field_names import (
    FIELD_ERROR,
    FIELD_ERROR_CODE,
    FIELD_FOR_EACH_AGGREGATE,
    FIELD_SUCCESS,
)
from src.core.tool_outcome import TOOL_ERROR_CODE_MAX_CHARS, TOOL_ERROR_HEAD_CHARS
from src.domains.diagnostics.advisor import (
    format_degradations_block,
    get_active_degradations,
)

logger = structlog.get_logger(__name__)

#: Bound on extracted entries: enough to explain a turn, never a dump.
MAX_FAILURES = 10


def _message_text(content: object) -> str:
    """The words of a tool message body, whichever shape LangChain gave it.

    A body is usually a string, but ``content`` also accepts a LIST whose
    blocks are plain strings OR typed dicts — the shape ``function_call`` takes
    under ``responses/v1`` and ``tool_use`` on Anthropic. Read with ``str()``
    that list reached the model as the repr of a Python structure: tokens spent
    on noise, and filtering it down to dicts alone dropped the string blocks
    entirely (ADR-303 cold review, both measured). A block carrying no readable
    text says nothing rather than its repr.

    Args:
        content: ``ToolMessage.content``.

    Returns:
        The readable text, possibly empty.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(part for part in map(_block_text, content) if part)
    return str(content or "")


def _block_text(block: object) -> str:
    """The readable words of one content block, or "" when it carries none."""
    if isinstance(block, str):
        return block
    if isinstance(block, dict) and isinstance(block.get("text"), str):
        return str(block["text"])
    return ""


def _entry(tool: str, code: str, message: object) -> dict[str, str]:
    """One typed failure, carrying only what the directive NAMES.

    The capability is omitted rather than published empty: the prompt asks the
    model to name it, and a model asked to name what it was not given invents
    one (ADR-184 applied to this block). Nothing else travels — a key the
    prompt never mentions is tokens billed on every failed turn for noise.

    Args:
        tool: The capability's name, empty when the turn cannot resolve one.
        code: The error code, already bounded.
        message: The message whose head is kept.

    Returns:
        The entry as the model receives it.
    """
    entry = {"error_code": code, "message": _head(message)}
    if tool:
        entry["tool"] = tool
    return entry


def _head(text: object) -> str:
    """First characters of a message-ish value (bounded, never None)."""
    return str(text or "")[:TOOL_ERROR_HEAD_CHARS]


def extract_failures_from_steps(
    completed_steps: dict[str, Any] | None,
    tool_names_by_step: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """Typed failures from the pipeline's completed_steps.

    Reads the shape the executor WRITES —
    ``{FIELD_SUCCESS: False, FIELD_ERROR: str, FIELD_ERROR_CODE: str | None}``
    (``parallel_executor._merge_single_step_result``). It used to require
    ``step["status"] == "error"``, a key no writer in the repository ever
    produced, so this reader returned an empty list for the whole life of
    the pipeline while its own test froze the fictional shape (ADR-303).

    Args:
        completed_steps: The state's step results (may be None/malformed —
            this reader never raises).
        tool_names_by_step: ``step_id → tool_name`` from the execution plan,
            so a failure NAMES the capability; a FOR_EACH item
            ``step_2_item_0`` resolves through ``step_2``.

    Returns:
        At most MAX_FAILURES entries: {source, tool, error_code, message}.
    """
    failures: list[dict[str, str]] = []
    names = tool_names_by_step or {}
    for step_id, step in (completed_steps or {}).items():
        if len(failures) >= MAX_FAILURES:
            break
        if not _is_failed_step(step):
            continue
        key = str(step_id)
        failures.append(
            _entry(
                tool=str(names.get(key) or names.get(key.rsplit("_item_", 1)[0], "")),
                code=str(step.get(FIELD_ERROR_CODE) or "UNKNOWN")[:TOOL_ERROR_CODE_MAX_CHARS],
                message=step.get(FIELD_ERROR),
            )
        )
    return failures


def _is_failed_step(step: object) -> bool:
    """A failed step entry, FOR_EACH aggregates excluded.

    An aggregate carries the loop's verdict; its items carry the failures, and
    listing both would count one failure twice.
    """
    return (
        isinstance(step, dict)
        and step.get(FIELD_SUCCESS) is False
        and not step.get(FIELD_FOR_EACH_AGGREGATE)
    )


def count_failed_steps(completed_steps: dict[str, Any] | None) -> int:
    """The EXACT number of failed steps — the list is bounded, the count is not.

    A directive that shows ten of fourteen failures and says nothing of the
    four is a capped read presented as a complete one (ADR-185).

    Args:
        completed_steps: The state's step results (may be None/malformed).

    Returns:
        How many steps failed, aggregates excluded.
    """
    return sum(1 for step in (completed_steps or {}).values() if _is_failed_step(step))


def extract_failures_from_tool_messages(
    messages: list[BaseMessage],
    limit: int | None = MAX_FAILURES,
) -> list[dict[str, str]]:
    """Typed failures from the ReAct loop's ToolMessages.

    Args:
        messages: The conversation messages of the run.

    Returns:
        At most MAX_FAILURES entries: {source, tool, error_code, message}.
    """
    failures: list[dict[str, str]] = []
    for message in messages:
        if limit is not None and len(failures) >= limit:
            break
        if not isinstance(message, ToolMessage):
            continue
        verdict = _tool_message_failure(message)
        if verdict is None:
            continue
        code, text = verdict
        failures.append(
            _entry(
                tool=str(getattr(message, "name", "") or ""),
                code=code[:TOOL_ERROR_CODE_MAX_CHARS],
                message=text,
            )
        )
    return failures


def _tool_message_failure(message: ToolMessage) -> tuple[str, str] | None:
    """``(error_code, text)`` when this ToolMessage reports a failure, else None.

    The verdict is STRUCTURAL: ``ToolMessage.status == "error"``, set by the
    ReAct executor on every declared failure and by the finalize node on every
    abandoned call (ADR-248). It used to be read by parsing the body as JSON —
    a shape ``compose_tool_message`` never emits, since it writes the tool's
    PROSE — so no ReAct failure was ever extracted and the honesty directive
    stayed empty on every ReAct turn (measured in production: a scheduled
    briefing announced that three ACTIVE connectors were not configured).

    A JSON body is still read when present, for the codes it carries.

    Args:
        message: One ToolMessage of the run.

    Returns:
        The code and the text to quote, or None when the call succeeded.
    """
    text = _message_text(message.content)
    payload: dict[str, Any] | None = None
    try:
        parsed = json.loads(text)
        payload = parsed if isinstance(parsed, dict) else None
    except TypeError, ValueError:  # JSONDecodeError is a ValueError
        payload = None

    declared_failure = payload is not None and payload.get(FIELD_SUCCESS) is False
    if getattr(message, "status", None) != "error" and not declared_failure:
        return None

    if payload is not None:
        code = str(payload.get(FIELD_ERROR_CODE) or payload.get(FIELD_ERROR) or "UNKNOWN")
        return code, str(payload.get("message") or payload.get(FIELD_ERROR) or text)
    # No code to read: the ReAct body carries the tool's prose, and the
    # directive's UNKNOWN branch tells the model to quote the message as-is.
    return "UNKNOWN", text


async def build_runtime_failures_directive(
    *,
    completed_steps: dict[str, Any] | None,
    messages: list[BaseMessage],
    template: str,
    tool_names_by_step: Mapping[str, str] | None = None,
    include_degradations: bool = True,
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
        tool_names_by_step: ``step_id → tool_name``, so a failure NAMES the
            capability the person asked for.
        include_degradations: Consult the advisor. The typed failures render
            with or without it — the caller puts the diagnostics flag HERE,
            never around the whole block: telling someone what just failed
            is not a diagnostics feature (ADR-248 doctrine, ADR-303).

    Returns:
        The formatted directive, or an EMPTY STRING when there is nothing to
        say (zero tokens on a clean turn — spec commitment).
    """
    failures = extract_failures_from_steps(completed_steps, tool_names_by_step)
    react_failures = extract_failures_from_tool_messages(messages, limit=None)
    total = count_failed_steps(completed_steps) + len(react_failures)
    failures += react_failures[: max(0, MAX_FAILURES - len(failures))]
    degradations_block = ""
    if include_degradations:
        try:
            degradations_block = format_degradations_block(await get_active_degradations())
        except Exception as exc:
            logger.debug("runtime_failures_advisor_unavailable", error=str(exc))
    if not failures and not degradations_block:
        return ""
    return template.format(
        failures_json=json.dumps(
            {"total": total, "shown": len(failures), "failures": failures},
            ensure_ascii=False,
        ),
        degradations_block=degradations_block,
    )
