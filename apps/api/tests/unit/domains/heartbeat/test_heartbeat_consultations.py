"""The sweep says what it opened, or nobody can know it happened.

The largest instance of a defect the briefing and the debrief already paid for:
``record_treatment`` fires from the tool gate alone, and this aggregator reads
its sources through direct calls. Measured on production 2026-09-07: **824
sweeps over thirty days, not one row**.

It is also the case where the gap matters most. A conversation can be re-read;
a sweep that opened someone's mail at four in the morning leaves them nothing
to consult.
"""

from __future__ import annotations

import uuid

import pytest

from src.domains.agents.effects.treatments import treatment_collector
from src.domains.heartbeat.consultations import (
    SECOND_PASS_SOURCES,
    SECTION_DOMAINS,
    consultation_capability,
    record_source_consultations,
)

pytestmark = pytest.mark.unit


class TestTheVocabularyIsReadable:
    """A consultation nobody can name is worse than none."""

    def test_every_source_resolves_to_a_real_domain(self) -> None:
        from src.domains.agents.effects.treatment_labels import (
            UNKNOWN_DOMAIN,
            treatment_domain,
        )

        for source, domain in SECTION_DOMAINS.items():
            resolved = treatment_domain(consultation_capability(source))
            assert resolved != UNKNOWN_DOMAIN, f"{source} headlines as Unknown"
            assert resolved == domain

    def test_the_aggregator_declares_every_source_it_fetches(self) -> None:
        """The two halves cannot drift: the specs are the source of truth.

        Read from the aggregator's own module rather than re-listed here — a
        hand-kept copy is how a fourteenth source would start recording
        nothing while every test stayed green.
        """
        import ast
        import inspect

        from src.domains.heartbeat.context_aggregator import ContextAggregator

        source = inspect.getsource(ContextAggregator.aggregate)
        tree = ast.parse(source.lstrip())
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Tuple) and node.elts:
                first = node.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    names.add(first.value)
        missing = names - set(SECTION_DOMAINS) - {"", "unknown"}
        assert names, "no source found in the aggregator's specs"
        assert not missing, f"the aggregator fetches sources nothing declares: {sorted(missing)}"

    def test_the_second_pass_declares_every_source_IT_gates(self) -> None:
        """The blind spot that hid three defects at once (2026-09-07).

        This guard read ``aggregate`` and nothing else, so ``_second_pass``
        — a second, gated set of reads in the same class — was invisible:
        ``departure`` reached the person's home location and the Routes API
        while being declared nowhere, journals and memories were recorded even
        when the person had switched them off, and a failed journal search was
        filed as a successful read.

        Reading the GATE, not the fetch: ``is_source_enabled(user, "x")`` is
        what decides whether a source is opened at all.
        """
        import ast
        import inspect

        from src.domains.heartbeat.context_aggregator import ContextAggregator

        tree = ast.parse(inspect.getsource(ContextAggregator._second_pass).lstrip())
        gated: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name != "is_source_enabled":
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    gated.add(arg.value)

        assert gated, "no gated source found in _second_pass"
        undeclared = gated - set(SECTION_DOMAINS)
        assert not undeclared, (
            f"the second pass opens sources nothing declares: {sorted(undeclared)} "
            "— add each to CONSULTATION_SURFACES['heartbeat'].domains"
        )
        assert gated == set(SECOND_PASS_SOURCES), (
            f"SECOND_PASS_SOURCES says {sorted(SECOND_PASS_SOURCES)} while the "
            f"pass gates {sorted(gated)} — the declaration and the code disagree"
        )

    def test_every_gated_source_reports_its_own_failure(self) -> None:
        """« Unreadable is not empty », checked on the code that decides it.

        Two of the three except-blocks recorded nothing, so a failed journal
        search reached the register as a successful read.
        """
        import inspect

        from src.domains.heartbeat.context_aggregator import ContextAggregator

        source = inspect.getsource(ContextAggregator._second_pass).lstrip()
        for name in SECOND_PASS_SOURCES:
            assert f'context.failed_sources.append("{name}")' in source, (
                f"a failed {name} read is filed as a success — append it to "
                "context.failed_sources in its except block"
            )


class TestWhatASweepRecords:
    """Observed on the collector the run published."""

    def test_every_opened_source_is_recorded(self) -> None:
        with treatment_collector(run_id="sweep-1") as rows:
            record_source_consultations(
                user_id=uuid.uuid4(),
                opened=["emails", "calendar"],
                failed=[],
                duration_ms=210,
            )

        assert {row.tool_name for row in rows} == {"heartbeat:emails", "heartbeat:calendar"}
        assert {row.outcome for row in rows} == {"ok"}

    def test_a_source_that_raised_reads_as_failed(self) -> None:
        with treatment_collector(run_id="sweep-2") as rows:
            record_source_consultations(
                user_id=uuid.uuid4(),
                opened=["emails", "tasks"],
                failed=["tasks"],
                duration_ms=90,
            )

        assert {row.tool_name: row.outcome for row in rows} == {
            "heartbeat:emails": "ok",
            "heartbeat:tasks": "failed",
        }

    def test_a_silenced_source_records_nothing(self) -> None:
        """``is_source_enabled`` already skipped it: nothing was opened."""
        with treatment_collector(run_id="sweep-3") as rows:
            record_source_consultations(
                user_id=uuid.uuid4(),
                opened=["emails"],
                failed=[],
                duration_ms=5,
            )

        assert [row.tool_name for row in rows] == ["heartbeat:emails"]

    def test_the_sweep_is_lias_own_initiative(self) -> None:
        """Nobody asked, which is what puts it in the initiative reading."""
        with treatment_collector(run_id="sweep-4") as rows:
            record_source_consultations(
                user_id=uuid.uuid4(), opened=["weather"], failed=[], duration_ms=1
            )

        assert rows[0].source == "proactive"

    def test_the_run_id_comes_from_the_collector(self) -> None:
        """A fetcher deep in the aggregation is handed no identifier."""
        with treatment_collector(run_id="sweep-5") as rows:
            record_source_consultations(
                user_id=uuid.uuid4(), opened=["emails"], failed=[], duration_ms=1
            )

        assert rows[0].run_id == "sweep-5"

    def test_outside_a_run_nothing_is_recorded_and_nothing_raises(self) -> None:
        record_source_consultations(
            user_id=uuid.uuid4(), opened=["emails"], failed=[], duration_ms=1
        )
