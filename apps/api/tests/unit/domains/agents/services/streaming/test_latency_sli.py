"""The chat latency histograms are fed only while a person waits.

Measured on production 2026-10-18: three morning routines fed the TTFT
histogram one to two observations per ten minutes, every one above 90 s, and
``SSELatencyP95High`` fired every morning for a month — the p95 of a wait
nobody had. These tests pin the declaration (a run says whether someone waits),
its scope (it never leaks into the next turn) and the single door the two
histograms are fed through.
"""

from __future__ import annotations

import ast
import asyncio

import pytest
from prometheus_client import REGISTRY

from src.domains.agents.services.streaming.latency_sli import (
    a_person_is_waiting,
    awaited_by_a_person,
    observe_first_token,
    observe_pre_graph_phase,
    observe_stream_duration,
)
from tests._repo_paths import find_apps_api_root

pytestmark = pytest.mark.unit

_SRC = find_apps_api_root() / "src"
_GUARDED = {
    "sse_time_to_first_token_seconds",
    "sse_streaming_duration_seconds",
    "chat_pre_graph_phase_seconds",
    "chat_journey_first_token_seconds",
    "chat_journey_unanswered_seconds",
}
_ALLOWED = {
    "infrastructure/observability/metrics_agents.py",  # the definitions
    "infrastructure/observability/metrics_chat_journey.py",  # the definitions
    "domains/agents/services/streaming/latency_sli.py",  # the one door
}


def _count(metric: str, intention: str) -> float:
    return REGISTRY.get_sample_value(f"{metric}_count", {"intention": intention}) or 0.0


class TestAPersonIsWaitingUnlessARunSaysOtherwise:
    def test_an_ordinary_turn_is_awaited(self) -> None:
        assert a_person_is_waiting() is True

    def test_a_run_nobody_waits_for_observes_nothing(self) -> None:
        intention = "latency_sli_unattended"
        before = _count("sse_time_to_first_token_seconds", intention)
        before_duration = _count("sse_streaming_duration_seconds", intention)

        with awaited_by_a_person(False):
            observe_first_token(intention, 95.0)
            observe_stream_duration(intention, 120.0)

        assert _count("sse_time_to_first_token_seconds", intention) == before
        assert _count("sse_streaming_duration_seconds", intention) == before_duration

    def test_a_waited_turn_is_observed(self) -> None:
        intention = "latency_sli_awaited"
        before = _count("sse_time_to_first_token_seconds", intention)
        before_duration = _count("sse_streaming_duration_seconds", intention)

        with awaited_by_a_person(True):
            observe_first_token(intention, 1.5)
            observe_stream_duration(intention, 4.0)

        assert _count("sse_time_to_first_token_seconds", intention) == before + 1
        assert _count("sse_streaming_duration_seconds", intention) == before_duration + 1

    def test_the_declaration_never_leaks_into_the_next_turn(self) -> None:
        with awaited_by_a_person(False):
            assert a_person_is_waiting() is False
            with awaited_by_a_person(True):
                assert a_person_is_waiting() is True
            assert a_person_is_waiting() is False
        assert a_person_is_waiting() is True

    async def test_a_task_started_inside_the_run_inherits_it(self) -> None:
        """The attempt runs under ``asyncio.wait_for``: a task, a context copy."""
        with awaited_by_a_person(False):
            seen = await asyncio.create_task(_probe())
        assert seen is False


async def _probe() -> bool:
    return a_person_is_waiting()


def _phase_count(phase: str) -> float:
    return REGISTRY.get_sample_value("chat_pre_graph_phase_seconds_count", {"phase": phase}) or 0.0


def test_pre_graph_phases_are_observed_only_while_a_person_waits() -> None:
    """The wait before the graph is a person's wait too: a routine never feeds it."""
    before = _phase_count("mcp")

    with awaited_by_a_person(False):
        observe_pre_graph_phase("mcp", 19.0)
    assert _phase_count("mcp") == before

    with awaited_by_a_person(True):
        observe_pre_graph_phase("mcp", 0.4)
    assert _phase_count("mcp") == before + 1


def test_the_two_histograms_are_fed_through_one_door() -> None:
    """A direct ``.observe`` elsewhere would bring the routines back into the
    SLI. Read as AST names, so a comment mentioning a metric is no reference."""
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        relative = path.relative_to(_SRC).as_posix()
        if relative in _ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = (
                node.id
                if isinstance(node, ast.Name)
                else node.attr if isinstance(node, ast.Attribute) else None
            )
            imported = (
                {alias.name for alias in node.names} if isinstance(node, ast.ImportFrom) else set()
            )
            if name in _GUARDED or imported & _GUARDED:
                offenders.append(f"{relative}:{getattr(node, 'lineno', '?')}")
    assert offenders == []
