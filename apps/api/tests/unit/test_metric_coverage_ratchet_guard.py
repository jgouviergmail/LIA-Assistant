"""Every Prometheus metric must reach a dashboard, a rule, or an alert.

A metric nobody can see is a metric nobody acts on. ADR-148 exists because a
heartbeat source that failed open left no trace: the health signals were dropped
on 46.5 % of ticks for a week and only a manual log dig found it. Adding
``heartbeat_source_dropped_total`` fixed that ONE blind spot; this guard makes
the class impossible to reintroduce silently.

Shrink-only, same doctrine as the file-size and CC ratchets: metrics knowingly
not wired live in ``metric_coverage_baseline.json`` and that list may only get
shorter. Two failure directions, both deliberate:

- a NEW uncovered metric (regression: shipping a blind counter);
- a baselined metric that is NOW covered (the ratchet must be tightened, or the
  next blind metric silently takes its slot).

Repair: wire the metric to a panel, then
``python scripts/audit/measure_metric_coverage.py --update``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
MEASURE_PATH = REPO_ROOT / "scripts" / "audit" / "measure_metric_coverage.py"
BASELINE_PATH = REPO_ROOT / "apps" / "api" / "tests" / "unit" / "metric_coverage_baseline.json"


def _measurer():
    if not MEASURE_PATH.exists():
        pytest.skip("guard needs the full repository checkout (scripts/audit/).")
    spec = importlib.util.spec_from_file_location("measure_metric_coverage", MEASURE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def measured() -> tuple[dict[str, str], list[str], list[str]]:
    """(defined metrics, uncovered metrics, baseline) — measured once per module."""
    measurer = _measurer()
    defined = measurer.metrics_defined_in_code()
    uncovered = measurer.uncovered_metrics(defined)
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["uncovered"]
    return defined, uncovered, baseline


class TestMetricCoverageRatchet:
    """The ratchet itself."""

    def test_no_new_uncovered_metric(
        self, measured: tuple[dict[str, str], list[str], list[str]]
    ) -> None:
        """A metric reaching no dashboard/rule/alert must be baselined explicitly."""
        defined, uncovered, baseline = measured
        new_blind = sorted(set(uncovered) - set(baseline))

        assert not new_blind, (
            "These metrics are defined but referenced by NO dashboard, recording rule "
            "or alert — an operator cannot see them:\n"
            + "\n".join(f"  - {name}  ({defined[name]})" for name in new_blind)
            + "\n\nWire each to a panel, or add it to metric_coverage_baseline.json "
            "with a written reason in review."
        )

    def test_baseline_only_shrinks(
        self, measured: tuple[dict[str, str], list[str], list[str]]
    ) -> None:
        """A metric that became covered must leave the baseline (shrink-only)."""
        _, uncovered, baseline = measured
        now_covered = sorted(set(baseline) - set(uncovered))

        assert not now_covered, (
            "These metrics are now wired to observability but still listed as "
            "uncovered:\n"
            + "\n".join(f"  - {name}" for name in now_covered)
            + "\n\nRun: python scripts/audit/measure_metric_coverage.py --update"
        )


class TestBaselineIntegrity:
    """The baseline itself must stay meaningful — a guard nobody can trust is noise."""

    def test_baseline_entries_are_real_metrics(
        self, measured: tuple[dict[str, str], list[str], list[str]]
    ) -> None:
        """A stale entry (deleted metric) silently widens the allowlist."""
        defined, _, baseline = measured
        ghosts = sorted(set(baseline) - set(defined))

        assert not ghosts, (
            "Baseline lists metrics that no longer exist in code:\n"
            + "\n".join(f"  - {name}" for name in ghosts)
            + "\n\nRun: python scripts/audit/measure_metric_coverage.py --update"
        )

    def test_baseline_has_no_duplicates(
        self, measured: tuple[dict[str, str], list[str], list[str]]
    ) -> None:
        """Duplicates would let a metric be removed once and still pass."""
        _, _, baseline = measured

        assert len(baseline) == len(set(baseline))

    def test_measurement_sees_the_codebase(
        self, measured: tuple[dict[str, str], list[str], list[str]]
    ) -> None:
        """A broken extractor would report zero uncovered and pass vacuously."""
        defined, _, _ = measured

        assert len(defined) > 400, f"only {len(defined)} metrics found — extractor broken?"


class TestMeasurementLogic:
    """Pin the detection itself, so the ratchet cannot pass by measuring nothing."""

    def test_histogram_suffixes_count_as_covered(self) -> None:
        """A dashboard charting ``foo_bucket`` covers the ``foo`` histogram."""
        measurer = _measurer()

        assert measurer.uncovered_metrics({"foo": "x.py"}, corpus="rate(foo_bucket[5m])") == []
        assert measurer.uncovered_metrics({"foo": "x.py"}, corpus="rate(foo_count[5m])") == []

    def test_unreferenced_metric_is_reported(self) -> None:
        """The positive control: an absent metric must be flagged."""
        measurer = _measurer()

        assert measurer.uncovered_metrics({"foo": "x.py"}, corpus="rate(bar[5m])") == ["foo"]

    def test_partial_name_is_not_a_match(self) -> None:
        """``foo_total`` in a panel must not silently cover a distinct ``foo``.

        Word-boundary matching, not substring: otherwise deleting the only panel
        of ``foo`` would keep passing because ``foo_extended_total`` exists.
        """
        measurer = _measurer()

        assert measurer.uncovered_metrics({"foo": "x.py"}, corpus="rate(prefix_foo[5m])") == ["foo"]

    def test_ast_extraction_catches_multiline_constructors(self, tmp_path: Path) -> None:
        """Metrics are declared across several lines — a regex over source misses them."""
        measurer = _measurer()
        module = tmp_path / "metrics_sample.py"
        module.write_text(
            "from prometheus_client import Counter, Histogram\n"
            "wrapped = Counter(\n"
            '    "wrapped_total",\n'
            '    "doc",\n'
            '    ["label"],\n'
            ")\n"
            'inline = Histogram("inline_seconds", "doc")\n',
            encoding="utf-8",
        )

        found = measurer.metrics_defined_in_code(tmp_path)

        assert set(found) == {"wrapped_total", "inline_seconds"}


class TestRatchetDirection:
    """``--update`` must SHRINK the baseline and never widen it.

    Found by adversarial review of the first implementation, which rewrote the
    baseline with the full current uncovered set: running the repair task after
    adding a blind metric would have silently baselined it. A ratchet that grows
    is not a ratchet — it is a rubber stamp for the very defect ADR-148 exists to
    prevent (a signal disappearing with nobody noticing).
    """

    def _isolated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entries: list[str]):
        measurer = _measurer()
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"_doc": "test", "uncovered": entries}), encoding="utf-8")
        monkeypatch.setattr(measurer, "BASELINE_PATH", baseline)
        return measurer, baseline

    def _entries(self, baseline: Path) -> list[str]:
        return json.loads(baseline.read_text(encoding="utf-8"))["uncovered"]

    def test_refuses_to_absorb_a_newly_blind_metric(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An uncovered metric absent from the baseline must fail, not be added."""
        measurer, baseline = self._isolated(tmp_path, monkeypatch, ["known_blind_total"])

        exit_code = measurer._update_baseline(
            {"known_blind_total": "a.py", "brand_new_total": "b.py"},
            ["known_blind_total", "brand_new_total"],
        )

        assert exit_code == 1
        assert self._entries(baseline) == ["known_blind_total"], "the baseline must NOT grow"

    def test_removes_entries_that_became_covered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A metric now wired to a panel leaves the baseline (the ratchet tightens)."""
        measurer, baseline = self._isolated(
            tmp_path, monkeypatch, ["still_blind_total", "now_wired_total"]
        )

        exit_code = measurer._update_baseline({"still_blind_total": "a.py"}, ["still_blind_total"])

        assert exit_code == 0
        assert self._entries(baseline) == ["still_blind_total"]

    def test_is_idempotent_when_already_in_sync(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Re-running the repair task on a synced baseline changes nothing."""
        measurer, baseline = self._isolated(tmp_path, monkeypatch, ["blind_total"])

        first = measurer._update_baseline({"blind_total": "a.py"}, ["blind_total"])
        entries_after_first = self._entries(baseline)
        second = measurer._update_baseline({"blind_total": "a.py"}, ["blind_total"])

        assert (first, second) == (0, 0)
        assert entries_after_first == self._entries(baseline) == ["blind_total"]


class TestRuleParsing:
    """Coverage must come from EXPRESSIONS, never from prose around them."""

    def test_a_metric_named_only_in_a_comment_is_not_covered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Found by cold review: raw-text matching let a TODO comment fake coverage.

        A metric mentioned as ``# TODO: wire foo_total`` would have counted as
        wired while reaching no operator — the guard would then bless exactly the
        blind spot it exists to catch.
        """
        measurer = _measurer()
        rules = tmp_path / "rules"
        rules.mkdir()
        (rules / "r.yml").write_text(
            "groups:\n"
            "  - name: sample\n"
            "    rules:\n"
            "      # TODO: wire foo_total to a panel one day\n"
            "      - record: job:other:rate5m\n"
            "        expr: rate(other_total[5m])\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(measurer, "PROM_DIR", rules)

        exprs = measurer._rule_expressions()

        assert exprs == ["rate(other_total[5m])"]
        assert not any("foo_total" in expr for expr in exprs)

    def test_recording_rule_expressions_are_collected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A metric consumed only by a recording rule IS observable — it counts."""
        measurer = _measurer()
        rules = tmp_path / "rules"
        rules.mkdir()
        (rules / "r.yml").write_text(
            "groups:\n"
            "  - name: sample\n"
            "    rules:\n"
            "      - record: job:foo:rate5m\n"
            "        expr: sum(rate(foo_total[5m]))\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(measurer, "PROM_DIR", rules)

        assert (
            measurer.uncovered_metrics(
                {"foo_total": "x.py"}, corpus="\n".join(measurer._rule_expressions())
            )
            == []
        )
