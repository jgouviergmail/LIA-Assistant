"""A payload that declares a failure never leaves a connector tool as a success (ADR-347).

Every connector tool runs through ``ConnectorTool.execute`` or
``APIKeyConnectorTool.execute``: ``execute_api_call`` returns a PAYLOAD and the
tool's own ``format_registry_response`` turns it into the ``UnifiedToolOutput``
whose ``success`` flag every reader of the verdict reads
(``core.tool_outcome.explicit_success``: the effect register, the tool metrics,
the ReAct loop, the pipeline executor).

A formatter can contradict its payload. The three Hue commands answered a
refused command with a success saying it failed, so the register settled the
act SUCCEEDED and the ReAct directive told the response model it had switched
the light. A behavioural probe (2026-10-14, re-run 2026-10-15) handed
``{"success": False}`` to the 71 registry-mode connector formatters: 27 answered
with a success — the three Hue commands, and 24 whose ``execute_api_call``
today returns no failure they misread (it raises instead, or returns a refusal
its formatter recognises by another key). Latent, not absent.

The two chokepoints therefore hand each pair to :func:`keep_declared_failure`:
when the payload declared a failure and the output claims success, the
payload's verdict wins, in the payload's own words — a formatter that never
read the verdict wrote its words for data the failure does not carry. Every
correction is a formatter defect: it is logged at ERROR, counted
(``tool_failure_verdict_corrected_total``) and fails any unit test that
triggers it (autouse fixture in ``tests/unit/conftest.py``).

A payload declares a failure in one of the two shapes connector tools use:
``success`` false, or — with no ``success`` key at all — a non-empty
``error_code`` (the refusals of ``mailbox_draft_base.refusal`` and the mail
attachment tool, which carry ``error_code`` and ``message``).
"""

from __future__ import annotations

from typing import Final, TypeGuard

import structlog

from src.core.field_names import FIELD_ERROR, FIELD_ERROR_CODE, FIELD_MESSAGE, FIELD_SUCCESS
from src.domains.agents.tools.common import ToolErrorCode, coerce_tool_error_code
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.observability.metrics_agents import (
    tool_failure_verdict_corrected_total,
)

logger = structlog.get_logger(__name__)

#: What the corrected failure says when neither the formatter nor the payload
#: left a word — technical English, the model reads it (ADR-256).
NO_WORDS_MESSAGE: Final = "The tool reported a failure without describing it."


def declares_failure(payload: object) -> TypeGuard[dict[str, object]]:
    """Whether a connector payload declared a failure.

    Args:
        payload: What ``execute_api_call`` returned.

    Returns:
        True for ``success`` false, or for a non-empty ``error_code`` when the
        payload carries no ``success`` key at all. An explicit ``success`` true
        always wins, and anything that is not a dict declares nothing.
    """
    if not isinstance(payload, dict):
        return False
    if FIELD_SUCCESS in payload:
        return payload[FIELD_SUCCESS] is False
    return bool(payload.get(FIELD_ERROR_CODE))


def keep_declared_failure(
    payload: object,
    output: UnifiedToolOutput,
    *,
    tool_name: str,
) -> UnifiedToolOutput:
    """Return ``output``, unless it claims a success its payload refused.

    Args:
        payload: What ``execute_api_call`` returned.
        output: What the tool's ``format_registry_response`` made of it.
        tool_name: The tool, for the log line and the metric label.

    Returns:
        ``output`` itself in every coherent case; otherwise a failure carrying
        the payload's typed code (``INTERNAL_ERROR`` when it names none the
        taxonomy knows) and the payload's words, else the formatter's.
    """
    # Only an EXPLICIT success is corrected, read without assuming the attribute:
    # a net that raised here would reach the tool's ``handle_error`` and turn its
    # own answer into an error — the one outcome a net must never cause.
    if getattr(output, "success", None) is not True or not declares_failure(payload):
        return output
    code = coerce_tool_error_code(payload.get(FIELD_ERROR_CODE)) or ToolErrorCode.INTERNAL_ERROR
    _report_correction(tool_name, code.value)
    return UnifiedToolOutput.failure(message=_words(payload, output), error_code=code.value)


def _words(payload: dict[str, object], output: UnifiedToolOutput) -> str:
    """The failure's own words: the payload's, else the formatter's, else a fixed line."""
    for words in (payload.get(FIELD_ERROR), payload.get(FIELD_MESSAGE), output.message):
        if isinstance(words, str) and words.strip():
            return words
    return NO_WORDS_MESSAGE


def _report_correction(tool_name: str, error_code: str) -> None:
    """Log and count one corrected verdict — facts only, never the words (ADR-317)."""
    logger.error(
        "tool_failure_verdict_corrected",
        tool_name=tool_name,
        error_code=error_code,
    )
    tool_failure_verdict_corrected_total.labels(tool_name=tool_name).inc()
