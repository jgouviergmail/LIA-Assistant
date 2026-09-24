"""A graph config's run id has ONE reader: ``src.core.run_config.run_id_of``.

ADR-231 moved the run id to ``config["metadata"]``; ``configurable`` carries
LangGraph plumbing only. Eleven readers kept looking in ``configurable`` and read
a key no writer writes. For most it was a log line saying ``unknown`` and every
plan named ``smart_unknown``; for the effect register it filed every direct
action under the THREAD id, so a pipeline step key collided with the previous
turns' identical step ids and the second action was SERVED the first one's
recorded result instead of running — measured in production on 2026-09-22, a
reminder never created while the tool answered as if it had been.

This guard refuses both shapes that let a second reader drift: a run id read
from ``configurable``, and an ad-hoc read of ``config.metadata`` outside the one
reader.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_SRC = Path(__file__).resolve().parents[2] / "src"
_THE_READER = _SRC / "core" / "run_config.py"
_RUN_ID_KEYS = frozenset({"run_id", "FIELD_RUN_ID"})
_CONFIGURABLE_KEYS = frozenset({"configurable", "FIELD_CONFIGURABLE"})
_METADATA_KEYS = frozenset({"metadata", "FIELD_METADATA"})


def _key(node: ast.expr | None) -> str | None:
    """The key a ``get``/subscript names, as a literal or a constant's name."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    return None


def _get_of(node: ast.expr) -> str | None:
    """The key of ``<x>.get(<key>, …)``, or None when ``node`` is not such a call."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
    ):
        return _key(node.args[0])
    return None


def _config_plane(receiver: ast.expr) -> str | None:
    """Which config plane ``receiver`` reads: ``configurable``, ``metadata`` or None."""
    if isinstance(receiver, ast.BoolOp):  # (config.get("metadata") or {})
        receiver = receiver.values[0]
    if isinstance(receiver, ast.Name) and receiver.id == "configurable":
        return "configurable"
    key = _get_of(receiver)
    if key is None and isinstance(receiver, ast.Subscript):
        key = _key(receiver.slice)
    if key in _CONFIGURABLE_KEYS:
        return "configurable"
    if key in _METADATA_KEYS:
        return "metadata"
    return None


def offending_reads(source: str) -> list[str]:
    """Every run-id read of a config plane in ``source``, as source text.

    Args:
        source: A Python module.

    Returns:
        The offending expressions.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _get_of(node) in _RUN_ID_KEYS:
            assert isinstance(node.func, ast.Attribute)
            if _config_plane(node.func.value) is not None:
                found.append(ast.unparse(node))
        elif isinstance(node, ast.Subscript) and _key(node.slice) in _RUN_ID_KEYS:
            if _config_plane(node.value) is not None:
                found.append(ast.unparse(node))
    return found


class TestTheGuardSeesTheShapes:
    """A guard that matches nothing guards nothing."""

    @pytest.mark.parametrize(
        "snippet",
        [
            'configurable.get("run_id")',
            "configurable.get(FIELD_RUN_ID, 'unknown')",
            'config.get("configurable", {}).get("run_id")',
            'config["configurable"]["run_id"]',
            "config.get(FIELD_METADATA, {}).get(FIELD_RUN_ID)",
            '(config.get("metadata") or {}).get("run_id")',
        ],
    )
    def test_each_forbidden_shape_is_seen(self, snippet: str) -> None:
        assert len(offending_reads(snippet)) == 1

    @pytest.mark.parametrize(
        "snippet",
        [
            # Other dicts that legitimately carry a run id.
            "pending_hitl.get(FIELD_RUN_ID)",
            'message.metadata.get("run_id")',
            'record.get("run_id")',
            # The thread id is plumbing: reading it from configurable is right.
            'config.get("configurable", {}).get("thread_id")',
        ],
    )
    def test_other_reads_are_not_flagged(self, snippet: str) -> None:
        assert offending_reads(snippet) == []


def test_no_module_reads_the_run_id_but_the_reader() -> None:
    modules = [path for path in _SRC.rglob("*.py") if path != _THE_READER]
    assert len(modules) > 1000, "the guard lost its subject"
    offenders = {
        str(path.relative_to(_SRC)): reads
        for path in modules
        if (reads := offending_reads(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}, (
        "Read a graph config's run id through src.core.run_config.run_id_of: "
        "configurable carries no run id since ADR-231, and a second reader of "
        f"metadata is how the first one drifted. Offenders: {offenders}"
    )
