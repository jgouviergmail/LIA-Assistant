"""The single calls of a turn send their static part as the system message (ADR-309).

Each module below renders a versioned prompt holding ``DYNAMIC_CONTEXT_MARKER``
and sends it in ONE call. Sent whole as one user message, its static part was
never marked by the payload shapers (they mark instruction roles only): measured
2026-09-23 on gpt-6-luna, every extraction read 0 % of its prompt from the cache
and wrote all of it at 1.25x. The guard reads the CALL — the ``messages``
argument of the LLM door must be a call to ``single_call_messages`` — never a
name found somewhere in the file.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[3] / "src"

#: Every single call of a turn that renders a marker-bearing prompt as ONE string.
#: (The HITL classifier is not one: it already sends its whole prompt as a system
#: message, where the shapers find the marker.)
SINGLE_CALL_SITES: tuple[str, ...] = (
    "domains/agents/nodes/initiative_node.py",
    "domains/agents/services/memory_extractor.py",
    "domains/agents/services/query_analyzer_service.py",
    "domains/interests/services/extraction_service.py",
    "domains/journals/extraction_service.py",
)

_DOORS = frozenset({"get_structured_output", "invoke_with_instrumentation"})


def _door_calls(tree: ast.AST) -> list[ast.Call]:
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name in _DOORS:
                calls.append(node)
    return calls


def _messages_argument(call: ast.Call) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == "messages":
            return keyword.value
    return call.args[1] if len(call.args) > 1 else None


def _is_single_call_messages(node: ast.expr | None) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "single_call_messages"
    )


@pytest.mark.parametrize("relative", SINGLE_CALL_SITES)
def test_the_call_sends_the_static_part_as_the_system_message(relative: str) -> None:
    tree = ast.parse((_SRC / relative).read_text(encoding="utf-8"))
    calls = _door_calls(tree)

    assert calls, f"{relative}: no LLM door call found"
    for call in calls:
        assert _is_single_call_messages(
            _messages_argument(call)
        ), f"{relative}:{call.lineno}: messages must be single_call_messages(prompt)"
