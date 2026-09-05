"""Collecting what a turn consulted, without paying for it (ADR-263, lot 4).

The register of ACTIONS is written before each effect, in its own transaction,
because an effect that is not recorded before it happens can never be proven
afterwards. A consultation needs none of that: it is observed, and observing
must stay free. The measured property that makes the gate acceptable on the
hot path — **0.64 µs and zero database session on a read** — is exactly what a
row-per-call would destroy.

Hence: the turn's parent publishes a LIVE LIST, the gate appends to it, and one
batch is written at the end. Two traps this file pins, both measured:

1. a collector built on ``ContextVar.set()`` inside the call would work in
   ReAct (sequential awaits) and **silently lose the pipeline**
   (``asyncio.gather`` children do not propagate a ``set``) — a register that
   lies by omission, on one execution mode only;
2. collecting must never be able to break the tool it observes.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.treatments import (
    collected_treatments,
    treatment_collector,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _running_turn() -> Any:
    gate_runtime.reset_policy_cache()
    with patch(
        "src.domains.agents.context.runtime_context.runtime_context_if_running",
        return_value=SimpleNamespace(
            user_id="11111111-1111-4111-8111-111111111111",
            thread_id="thread-1",
            execution_mode="pipeline",
            is_automated_source=False,
        ),
    ):
        yield


async def _read(query: str = "x") -> dict[str, Any]:
    return {"success": True, "data": {"q": query}}


async def _failing_read(query: str = "x") -> dict[str, Any]:
    return {"success": False, "error": "provider down"}


async def _raising_read(query: str = "x") -> dict[str, Any]:
    raise RuntimeError("the provider exploded")


class TestEveryConsultationIsCollected:
    async def test_a_read_is_collected(self) -> None:
        gated = gate_runtime.gated("get_emails_tool", _read)
        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            treatment_collector(),
        ):
            await gated(query="x")
            collected = list(collected_treatments())

        assert len(collected) == 1
        assert collected[0].tool_name == "get_emails_tool"
        assert collected[0].outcome == "ok"
        assert collected[0].mutation_policy == "read"

    async def test_the_PIPELINE_shape_is_not_lost(self) -> None:
        """``asyncio.gather``: the trap a ContextVar-based collector falls into."""
        gated = gate_runtime.gated("get_emails_tool", _read)
        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            treatment_collector(),
        ):
            await asyncio.gather(*(gated(query=f"q{index}") for index in range(5)))
            collected = list(collected_treatments())

        assert len(collected) == 5, "a concurrent tool call was lost"

    async def test_the_REACT_shape_is_not_lost(self) -> None:
        gated = gate_runtime.gated("get_emails_tool", _read)
        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            treatment_collector(),
        ):
            await gated(query="a")
            await gated(query="b")
            collected = list(collected_treatments())

        assert len(collected) == 2

    async def test_a_tool_with_no_declared_policy_is_collected_too(self) -> None:
        """23 registered tools declare none; a register must not skip them."""
        gated = gate_runtime.gated("browser_snapshot_tool", _read)
        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: None),
            treatment_collector(),
        ):
            await gated(query="x")
            collected = list(collected_treatments())

        assert len(collected) == 1
        assert collected[0].mutation_policy is None

    async def test_two_calls_of_one_tool_are_two_rows(self) -> None:
        """A consultation is not idempotent."""
        gated = gate_runtime.gated("get_emails_tool", _read)
        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            treatment_collector(),
        ):
            await gated(query="same")
            await gated(query="same")
            collected = list(collected_treatments())

        assert len(collected) == 2


class TestWhatIsObserved:
    async def test_a_failure_is_recorded_as_a_failure(self) -> None:
        gated = gate_runtime.gated("get_emails_tool", _failing_read)
        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            treatment_collector(),
        ):
            await gated(query="x")
            collected = list(collected_treatments())

        assert collected[0].outcome == "failed"

    async def test_a_raising_tool_is_recorded_and_still_raises(self) -> None:
        """The turn must see the exception; the register must see the call."""
        gated = gate_runtime.gated("get_emails_tool", _raising_read)
        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            treatment_collector(),
        ):
            with pytest.raises(RuntimeError):
                await gated(query="x")
            collected = list(collected_treatments())

        assert len(collected) == 1
        assert collected[0].outcome == "failed"

    async def test_the_duration_is_measured(self) -> None:
        async def _slow(query: str = "x") -> dict[str, Any]:
            await asyncio.sleep(0.02)
            return {"success": True}

        gated = gate_runtime.gated("get_emails_tool", _slow)
        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            treatment_collector(),
        ):
            await gated(query="x")
            collected = list(collected_treatments())

        assert collected[0].duration_ms >= 10

    async def test_nothing_of_what_was_asked_is_kept(self) -> None:
        """The PII line: a consultation records the capability, never the query."""
        gated = gate_runtime.gated("search_emails_tool", _read)
        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            treatment_collector(),
        ):
            await gated(query="emails from Marie about the divorce")
            collected = list(collected_treatments())

        assert "Marie" not in repr(collected[0])
        assert "divorce" not in repr(collected[0])
        assert not hasattr(collected[0], "arguments")


class TestTheTwoRegistersStayApart:
    async def test_an_ACTION_is_not_collected_as_a_treatment(self) -> None:
        """No overlap: otherwise the two totals could be added by mistake."""

        class _Ledger:
            async def claim(self, request: Any) -> Any:
                return None

            async def close(self, *args: Any, **kwargs: Any) -> None:
                return None

            async def refuse(self, request: Any, *, error_code: str) -> None:
                return None

        from src.domains.agents.effects.scope import EffectScope, effect_scope

        gated = gate_runtime.gated("control_hue_light_tool", _read)
        with (
            patch.object(gate_runtime, "_LEDGER", _Ledger()),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "reversible"),
            effect_scope(EffectScope(run_id="r", idempotency_key="k", source="user")),
            treatment_collector(),
        ):
            await gated(query="x")
            collected = list(collected_treatments())

        assert collected == [], "an action was also recorded as a consultation"


class TestObservingNeverBreaksWhatItObserves:
    async def test_a_broken_collector_does_not_fail_the_tool(self) -> None:
        gated = gate_runtime.gated("get_emails_tool", _read)

        def _explode(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("the collector is broken")

        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            patch("src.domains.agents.effects.treatments.observe", _explode),
            treatment_collector(),
        ):
            result = await gated(query="x")

        assert result["success"] is True

    async def test_no_collector_published_is_not_an_error(self) -> None:
        """Outside a turn (a script, a test), the gate must simply not collect."""
        gated = gate_runtime.gated("get_emails_tool", _read)
        with patch.object(gate_runtime, "resolve_policy", lambda _n: "read"):
            result = await gated(query="x")

        assert result["success"] is True
        assert list(collected_treatments()) == []

    async def test_the_read_path_opens_no_database_session(self) -> None:
        """The property that makes the gate acceptable on the hot path."""
        opened: list[str] = []

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _context() -> Any:
            opened.append("session")
            yield object()

        gated = gate_runtime.gated("get_emails_tool", _read)
        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            patch("src.infrastructure.database.session.get_db_context", _context),
            treatment_collector(),
        ):
            await gated(query="x")

        assert opened == [], "a read touched the database"


class TestALostRegisterIsNeverSILENT:
    """A turn running with no register open must SAY so.

    The collector is published in exactly one place — the chat entry point. A
    second way to run the graph (a background worker, a new API, a future
    execution mode) would consult capabilities with nobody collecting them, and
    the register would simply be incomplete with nothing to notice it.

    That is the ADR-148 failure mode, verbatim: a source failing open dropped
    the health signals on 46.5 % of heartbeat ticks for a week because no
    metric existed. A gap that produces no signal is a gap nobody fixes — so
    the gap is counted, and an alert reads it.

    Note the asymmetry that makes the counter meaningful: OUTSIDE a turn there
    is nothing to record and no gap (a script, a test, a boot probe), so it
    stays silent there.
    """

    @staticmethod
    def _uncollected() -> float:
        from src.infrastructure.observability.metrics_effects import (
            treatments_uncollected_total,
        )

        total = 0.0
        for metric in treatments_uncollected_total.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    total += float(sample.value)
        return total

    async def test_a_turn_with_no_register_open_is_counted(self) -> None:
        before = self._uncollected()
        gated = gate_runtime.gated("get_emails_tool", _read)

        # A turn IS running (the fixture publishes a runtime context) but no
        # collector was opened — exactly what a new entry point would produce.
        with patch.object(gate_runtime, "resolve_policy", lambda _n: "read"):
            await gated(query="x")

        assert self._uncollected() - before == 1

    async def test_a_call_OUTSIDE_a_turn_is_not_counted(self) -> None:
        """A script or a probe is not a lost register."""
        before = self._uncollected()
        gated = gate_runtime.gated("get_emails_tool", _read)

        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            patch(
                "src.domains.agents.context.runtime_context.runtime_context_if_running",
                return_value=None,
            ),
        ):
            await gated(query="x")

        assert self._uncollected() == before

    async def test_a_collected_turn_is_not_counted(self) -> None:
        before = self._uncollected()
        gated = gate_runtime.gated("get_emails_tool", _read)

        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
            treatment_collector(),
        ):
            await gated(query="x")

        assert self._uncollected() == before
