"""Guard: health values are aggregated through ONE door (ADR-148 amendment 2026-11-14).

Overlapping samples from two devices are counted once by
``fusion.counted_samples``; a reader summing ``HealthSample.value`` itself
counts one walk twice — the 23 309 steps shown for about 13 300 on
2026-11-14. Every SQL aggregate over a sample's value therefore reads the
door's ``value`` column, never the table's: this guard walks every module
under ``src/`` and refuses a ``func.<aggregate>(...)`` call that reaches
``HealthSample.value`` directly, anywhere but in the door itself.

The guard was proven on a failing fixture (``test_the_guard_sees_a_direct_sum``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[4] / "src"
DOOR = SRC / "domains" / "health_metrics" / "fusion.py"
AGGREGATES = frozenset({"sum", "avg", "min", "max", "count", "percentile_cont", "stddev"})


def _reaches_sample_value(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Attribute)
        and child.attr == "value"
        and isinstance(child.value, ast.Name)
        and child.value.id == "HealthSample"
        for child in ast.walk(node)
    )


def _direct_aggregates(source: str) -> list[int]:
    """Lines of ``func.<aggregate>(...)`` calls reading ``HealthSample.value``."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in AGGREGATES
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "func"
            and any(_reaches_sample_value(argument) for argument in node.args)
        ):
            lines.append(node.lineno)
    return lines


def test_the_guard_sees_a_direct_sum() -> None:
    fixture = "total = select(func.sum(HealthSample.value)).where(HealthSample.kind == 'steps')"
    assert _direct_aggregates(fixture) == [1]
    assert _direct_aggregates("total = select(func.sum(counted.c.value))") == []


def test_no_reader_aggregates_sample_values_beside_the_door() -> None:
    offenders = [
        f"{path.relative_to(SRC)}:{line}"
        for path in sorted(SRC.rglob("*.py"))
        if path != DOOR
        for line in _direct_aggregates(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "Aggregate health values through fusion.counted_samples, which counts "
        f"overlapping samples once: {offenders}"
    )
