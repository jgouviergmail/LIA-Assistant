"""Every wake outcome series exists from boot, at zero.

A label pair's FIRST increment is invisible to ``increase()`` when the pair had
no sample in the window: the series starts life at 1. PushWakeSweepStalled reads
``sum(increase(push_wakes_total[30m]))``, so a wake served under a pair nobody
had used since the deploy read as « none served » — the alert went pending in
production on 2026-10-03, seven hours after a deploy, while 18 wakes out of 18
had been served. Initialised at zero, every pair has a past.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry, Counter

from src.domains.rag_spaces import drive_push
from src.infrastructure.scheduler import heartbeat_wake_sweep
from src.infrastructure.scheduler.heartbeat_wake_sweep import WAKE_OUTCOMES

pytestmark = pytest.mark.unit


def test_every_provider_and_outcome_pair_is_exported_at_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A registry of its own: the process-wide one is shared with every test that
    # counts a wake, and what it holds depends on the order they ran in.
    registry = CollectorRegistry()
    counter = Counter(
        "push_wakes_total", "Isolated twin.", ["provider", "outcome"], registry=registry
    )
    monkeypatch.setattr(heartbeat_wake_sweep, "push_wakes_total", counter)

    heartbeat_wake_sweep._export_every_wake_series()

    samples = [
        sample
        for metric in registry.collect()
        for sample in metric.samples
        if sample.name == "push_wakes_total"
    ]
    providers = heartbeat_wake_sweep._PROVIDERS
    assert {(s.labels["provider"], s.labels["outcome"]) for s in samples} == {
        (p, o) for p in providers for o in WAKE_OUTCOMES
    }
    assert {s.value for s in samples} == {0.0}


def test_the_series_are_exported_when_the_module_is_imported() -> None:
    tree = ast.parse(Path(heartbeat_wake_sweep.__file__).read_text(encoding="utf-8"))

    module_level_calls = {
        node.value.func.id
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
    }

    assert "_export_every_wake_series" in module_level_calls


def test_every_outcome_the_sweep_returns_is_in_the_vocabulary() -> None:
    tree = ast.parse(Path(heartbeat_wake_sweep.__file__).read_text(encoding="utf-8"))
    literals: set[str] = set()
    for node in ast.walk(tree):
        value = node.value if isinstance(node, ast.Return) else None
        if isinstance(value, ast.Tuple) and value.elts:
            value = value.elts[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            literals.add(value.value)
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "outcome" for t in node.targets)
            and isinstance(node.value, ast.Constant)
        ):
            literals.add(node.value.value)

    # "signal" is the gate's pass-through between two steps, never counted.
    assert literals - {"signal"} <= set(WAKE_OUTCOMES)


def test_every_drive_outcome_is_in_the_vocabulary() -> None:
    drive = {
        drive_push._REINDEXED,
        drive_push._LOCKED,
        drive_push._NO_LINKED_FOLDER,
        drive_push._REBASED,
        "error",
    }

    assert drive <= set(WAKE_OUTCOMES)
