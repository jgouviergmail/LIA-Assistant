"""The one reading of « did this tool call succeed? » (ADR-303).

Shared by the consultation register (``domains/agents/effects/outcome.py``),
the tool metrics decorator (``infrastructure/observability/decorators.py``) and
the ReAct loop (``domains/agents/nodes/react_nodes.py``) — three readers that
used to disagree on the same payload: the register read it and said ``failed``,
the decorator never looked and said ``success="true"``, the loop read ``success``
on a dict only so a Pydantic failure counted as productive. Measured in
production on 2026-09-09: four HTTP 403s, four ``failed`` rows in the register,
and a Prometheus counter that saw four successes.

Lives in ``core`` because ``infrastructure`` must import it without taking a
dependency on a domain, and a domain must import it without reaching sideways.
"""

from __future__ import annotations

from typing import Any

from src.core.field_names import FIELD_ERROR_CODE, FIELD_SUCCESS

#: Bound on an error CODE wherever it travels: a Prometheus label, a log line,
#: a typed failure entry. A code is an identifier; a payload that puts a
#: document there must not put a document on a metric label.
TOOL_ERROR_CODE_MAX_CHARS = 64

#: Bound on the HEAD of an error message kept for a reader — the directive's
#: entries and the typed failed steps carried in the graph state. One notion,
#: so the state and the prompt cannot bound the same text differently.
TOOL_ERROR_HEAD_CHARS = 160


def _attribute(result: Any, name: str) -> Any:
    """``getattr`` that cannot raise — a property may blow up on access.

    Reading a result must never change the result: this predicate runs inside
    the metrics decorator's ``try``, so anything it raises would be caught by
    the tool's own error path and report a SUCCESSFUL call as failed
    (ADR-303 cold review).

    Args:
        result: Whatever the tool returned.
        name: The attribute to read.

    Returns:
        The value, or None when it cannot be read.
    """
    try:
        return getattr(result, name, None)
    except Exception:  # noqa: BLE001 - an observer never breaks the observed
        return None


def explicit_success(result: Any) -> bool:
    """False ONLY when the tool explicitly said so.

    Reads a ``UnifiedToolOutput``-like object (``.success``) or a
    ``ToolResponse``-like dict (``["success"]``). Anything else — a bare
    string, a list, ``None``, a payload that cannot be read at all — is not a
    refusal and counts as success, which is exactly how the consultation
    register has always read it.

    Args:
        result: Whatever the tool returned.

    Returns:
        ``False`` iff the payload carries ``success`` equal to ``False``.
    """
    if isinstance(result, dict):
        return result.get(FIELD_SUCCESS) is not False
    return _attribute(result, FIELD_SUCCESS) is not False


def error_code_of(result: Any) -> str | None:
    """The error code a failed result carries — for labels and logs.

    Never the message: a code is bounded and safe to put on a metric label or
    in a log line, where a message carries a URL, a name or a mailbox.

    Args:
        result: Whatever the tool returned.

    Returns:
        The code as a bounded string, or None when the payload names none.
    """
    value = (
        result.get(FIELD_ERROR_CODE)
        if isinstance(result, dict)
        else _attribute(result, FIELD_ERROR_CODE)
    )
    return str(value)[:TOOL_ERROR_CODE_MAX_CHARS] if value else None
