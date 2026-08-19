"""Deferred self-evaluation funnel counters (audit 2026-08-19, lot 0).

The T → T+1 loop produced zero evidence/contradiction signals since April
while every link existed in the code. Nothing distinguished "the previous-turn
section is never built" from "the LLM never signals". These tests pin the
funnel stages recorded by the extraction flow:

- ``no_previous_ids``  — extraction ran without T-1 injected ids;
- ``section_built``    — the directives section rendered with content;
- ``section_empty``    — ids were provided but no entry survived to render;
- ``signaled``         — the LLM emitted an ``evidence_outcome`` (counted
  BEFORE the hallucinated-id filter, so a filtered signal stays visible as
  a signaled-vs-applied gap; the applied terminal already exists as
  ``journal_evidence_total``).
"""

from __future__ import annotations

from src.domains.journals.schemas import ExtractedJournalEntry
from src.domains.journals.self_eval import (
    count_evidence_signals,
    record_self_eval_funnel,
)
from src.infrastructure.observability.metrics_journals import journal_self_eval_total


def _stage_value(stage: str) -> float:
    return journal_self_eval_total.labels(stage=stage)._value.get()


class TestFunnelHeadStages:
    def test_no_previous_ids(self) -> None:
        before = _stage_value("no_previous_ids")
        assert record_self_eval_funnel([], "") == "no_previous_ids"
        assert _stage_value("no_previous_ids") == before + 1

    def test_section_built(self) -> None:
        before = _stage_value("section_built")
        stage = record_self_eval_funnel(["a1"], "## DIRECTIVES INJECTED AT THE PREVIOUS TURN…")
        assert stage == "section_built"
        assert _stage_value("section_built") == before + 1

    def test_section_empty_when_entries_vanished(self) -> None:
        before = _stage_value("section_empty")
        assert record_self_eval_funnel(["a1", "a2"], "") == "section_empty"
        assert _stage_value("section_empty") == before + 1


class TestSignaledStage:
    def _update(self, outcome: str | None) -> ExtractedJournalEntry:
        return ExtractedJournalEntry(
            action="update",
            entry_id="00000000-0000-0000-0000-000000000001",
            evidence_outcome=outcome,  # type: ignore[arg-type]
        )

    def test_counts_evidence_and_contradiction_updates_only(self) -> None:
        actions = [
            self._update("evidence"),
            self._update("contradiction"),
            self._update(None),
            ExtractedJournalEntry(action="create", theme="learnings", title="t", content="c"),
        ]
        assert count_evidence_signals(actions) == 2

    def test_zero_signals_do_not_touch_the_counter(self) -> None:
        before = _stage_value("signaled")
        assert count_evidence_signals([self._update(None)]) == 0
        assert _stage_value("signaled") == before

    def test_signaled_counter_incremented_by_count(self) -> None:
        before = _stage_value("signaled")
        n = count_evidence_signals([self._update("evidence"), self._update("contradiction")])
        assert n == 2
        assert _stage_value("signaled") == before + 2
