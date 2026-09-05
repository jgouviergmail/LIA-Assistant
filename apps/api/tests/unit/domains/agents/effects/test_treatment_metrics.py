"""What an operator can SEE of the consultation register (ADR-263, lot 4).

The register was shipped without a single counter: dashboard 28 could say what
the two tables cost on disk and nothing at all about what the assistant looks
at. A register nobody can watch is a table, not an instrument.

Three properties, each of them a rule this codebase already pays for:

- **counted from what was PERSISTED**, never from what was collected: a flush
  that failed must not leave a counter claiming rows that do not exist;
- **bounded labels only** — `domain` comes from our own taxonomy (31 values,
  MCP collapsed to one), never `tool_name`, whose value set belongs to
  third-party servers;
- **counting never breaks the turn**, like every other emission on this path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects.treatments import Treatment

pytestmark = [pytest.mark.unit]


def _row(tool_name: str = "get_emails_tool", outcome: str = "ok", **overrides: Any) -> Treatment:
    values: dict[str, Any] = {
        "user_id": "11111111-1111-4111-8111-111111111111",
        "thread_id": "thread-1",
        "run_id": "run-1",
        "source": "user",
        "execution_mode": "react",
        "tool_name": tool_name,
        "mutation_policy": "read",
        "outcome": outcome,
        "duration_ms": 12,
        "occurred_at": datetime.now(UTC),
    }
    values.update(overrides)
    return Treatment(**values)


def _observed() -> list[tuple[str, str, str, int]]:
    """Read the counter's series as (domain, outcome, execution_mode, value)."""
    from src.infrastructure.observability.metrics_effects import treatments_total

    series: list[tuple[str, str, str, int]] = []
    for metric in treatments_total.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total"):
                series.append(
                    (
                        sample.labels["domain"],
                        sample.labels["outcome"],
                        sample.labels["execution_mode"],
                        int(sample.value),
                    )
                )
    return series


def _counts() -> dict[tuple[str, str, str], int]:
    """The counter's series keyed by their labels — read before and after."""
    return {(domain, outcome, mode): value for domain, outcome, mode, value in _observed()}


class TestTheCounterExistsAndIsBounded:
    def test_the_metric_is_declared(self) -> None:
        from src.infrastructure.observability.metrics_effects import treatments_total

        assert treatments_total is not None

    def test_its_labels_are_the_three_bounded_ones(self) -> None:
        from src.infrastructure.observability.metrics_effects import treatments_total

        assert set(treatments_total._labelnames) == {"domain", "outcome", "execution_mode"}

    def test_it_never_carries_a_tool_name(self) -> None:
        """A third-party server names its own tools; that is unbounded."""
        from src.infrastructure.observability.metrics_effects import treatments_total

        assert "tool_name" not in treatments_total._labelnames


class TestItCountsWhatWasPersisted:
    async def test_a_written_batch_is_counted_by_domain(self) -> None:
        from src.domains.agents.effects import treatment_recorder as recorder

        before = _counts()

        class _Repository:
            def __call__(self, _db: Any) -> Any:
                return self

            async def record_batch(self, rows: list[Treatment]) -> int:
                return len(rows)

        class _Db:
            async def commit(self) -> None:
                return None

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _session() -> Any:
            yield _Db()

        with (
            patch.object(recorder, "TreatmentRepository", _Repository()),
            patch("src.infrastructure.database.session.get_db_context", _session),
        ):
            await recorder._flush([_row(), _row("get_events_tool"), _row()])

        after = _counts()
        assert after.get(("email", "ok", "react"), 0) - before.get(("email", "ok", "react"), 0) == 2
        assert after.get(("event", "ok", "react"), 0) - before.get(("event", "ok", "react"), 0) == 1

    async def test_a_failed_flush_counts_NOTHING_as_persisted(self) -> None:
        """A counter must not claim rows the database refused."""
        from src.domains.agents.effects import treatment_recorder as recorder

        before = _counts()

        class _Repository:
            def __call__(self, _db: Any) -> Any:
                return self

            async def record_batch(self, rows: list[Treatment]) -> int:
                raise RuntimeError("the register is unwritable")

        from contextlib import asynccontextmanager

        class _Db:
            async def commit(self) -> None:
                return None

        @asynccontextmanager
        async def _session() -> Any:
            yield _Db()

        with (
            patch.object(recorder, "TreatmentRepository", _Repository()),
            patch("src.infrastructure.database.session.get_db_context", _session),
        ):
            await recorder._flush([_row(), _row()])

        after = _counts()
        assert after.get(("email", "ok", "react"), 0) == before.get(("email", "ok", "react"), 0)

    async def test_a_failed_flush_is_counted_as_a_ledger_failure(self) -> None:
        """The gap is loud, never silent — the same rule the ledger follows."""
        from src.domains.agents.effects import treatment_recorder as recorder
        from src.infrastructure.observability.metrics_effects import (
            effect_ledger_failures_total,
        )

        def _value() -> float:
            for metric in effect_ledger_failures_total.collect():
                for sample in metric.samples:
                    if (
                        sample.name.endswith("_total")
                        and sample.labels.get("operation") == "treatments_flush"
                    ):
                        return float(sample.value)
            return 0.0

        before = _value()

        class _Repository:
            def __call__(self, _db: Any) -> Any:
                return self

            async def record_batch(self, rows: list[Treatment]) -> int:
                raise RuntimeError("nope")

        from contextlib import asynccontextmanager

        class _Db:
            async def commit(self) -> None:
                return None

        @asynccontextmanager
        async def _session() -> Any:
            yield _Db()

        with (
            patch.object(recorder, "TreatmentRepository", _Repository()),
            patch("src.infrastructure.database.session.get_db_context", _session),
        ):
            await recorder._flush([_row()])

        assert _value() - before == 1


class TestCountingNeverBreaksTheTurn:
    async def test_a_broken_counter_does_not_fail_the_flush(self) -> None:
        from src.domains.agents.effects import treatment_recorder as recorder

        written: list[int] = []

        class _Repository:
            def __call__(self, _db: Any) -> Any:
                return self

            async def record_batch(self, rows: list[Treatment]) -> int:
                written.append(len(rows))
                return len(rows)

        from contextlib import asynccontextmanager

        class _Db:
            async def commit(self) -> None:
                return None

        @asynccontextmanager
        async def _session() -> Any:
            yield _Db()

        def _explode(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("the counter is broken")

        with (
            patch.object(recorder, "TreatmentRepository", _Repository()),
            patch("src.infrastructure.database.session.get_db_context", _session),
            patch.object(recorder, "count_persisted_treatments", _explode),
        ):
            await recorder._flush([_row()])

        assert written == [1], "a broken counter lost the register"
