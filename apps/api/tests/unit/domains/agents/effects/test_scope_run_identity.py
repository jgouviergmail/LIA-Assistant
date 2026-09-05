"""An effect is filed under the RUN it belongs to (ADR-263).

Measured on the running instance, 2026-09-04: the first real effect the ledger
ever recorded — a confirmed e-mail draft — was filed with ``run_id`` equal to
the THREAD id. ``scope_from_config`` reads the run from ``config.configurable``,
a HITL resume carries none there, and the fallback is the thread. The row was
perfectly correct and completely unusable: the turn summary looks up BY RUN, so
it found nothing, no message ever carried ``performed_effects``, and the whole
proof surface was invisible for the one path that produces most effects.

The response node HOLDS the authoritative run id — it receives it as an
argument and passes it to the executor. A caller that knows must not be made to
guess, so the scope now takes it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects.scope import react_call_scope, scope_from_config, step_effect_key

pytestmark = [pytest.mark.unit]


def _context(thread_id: str = "thread-42") -> Any:
    return SimpleNamespace(
        user_id="u", thread_id=thread_id, execution_mode="react", is_automated_source=False
    )


class TestTheCallerSKnowledgeWins:
    def test_an_explicit_run_id_is_used_even_when_the_config_has_one(self) -> None:
        with patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=_context(),
        ):
            scope = scope_from_config(
                {"configurable": {"run_id": "from-config"}},
                idempotency_key="draft:d1",
                run_id="from-the-caller",
            )

        assert scope.run_id == "from-the-caller"

    def test_the_measured_defect_no_run_in_the_config(self) -> None:
        """A HITL resume: the config carries no run, the caller does."""
        with patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=_context(),
        ):
            scope = scope_from_config(
                {"configurable": {}}, idempotency_key="draft:d1", run_id="the-real-run"
            )

        assert scope.run_id == "the-real-run"
        assert scope.run_id != "thread-42", "filing under the thread makes the row unfindable"


class TestTheFallbacksAreUnchanged:
    def test_the_config_still_answers_when_the_caller_does_not(self) -> None:
        with patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=_context(),
        ):
            scope = scope_from_config(
                {"configurable": {"run_id": "from-config"}}, idempotency_key="step:s1"
            )

        assert scope.run_id == "from-config"

    def test_the_thread_remains_the_last_resort(self) -> None:
        """A correlation value, never an invented one."""
        with patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=_context(),
        ):
            scope = scope_from_config({"configurable": {}}, idempotency_key="step:s1")

        assert scope.run_id == "thread-42"

    def test_with_no_context_at_all_it_says_so(self) -> None:
        with patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=None,
        ):
            scope = scope_from_config({}, idempotency_key="step:s1")

        assert scope.run_id == "unknown"

    def test_the_react_scope_reads_the_running_graph_s_config(self) -> None:
        """ReAct runs INSIDE the graph, where the run id is always present."""
        with patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=_context(),
        ):
            scope = react_call_scope(
                {"configurable": {"run_id": "graph-run"}}, "call-1", approved=True
            )

        assert scope.run_id == "graph-run"
        assert scope.approved is True

    def test_the_step_key_stays_run_scoped(self) -> None:
        """Two turns of one thread must not share a step key."""
        with patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=_context(),
        ):
            first = step_effect_key({"configurable": {"run_id": "run-A"}}, "s1")
            second = step_effect_key({"configurable": {"run_id": "run-B"}}, "s1")

        assert first != second


class TestTheDraftExecutorPassesIt:
    def test_the_executor_hands_its_run_id_to_the_scope(self) -> None:
        """Read from the source: the argument exists and is forwarded.

        A behavioural test would need the whole response node; what matters
        here is that the executor stops rebuilding a fact it was given.
        """
        import inspect

        from src.domains.agents.services import draft_executor

        source = inspect.getsource(draft_executor)
        assert (
            "run_id=run_id," in source
        ), "the draft executor must forward the run id it received to the scope"
