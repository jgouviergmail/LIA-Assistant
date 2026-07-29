"""Cardinality + naming contract for product metrics (ADR-178).

What must hold (program spec, correction #8 and #5):
- no forbidden label name anywhere ('job' is reserved by the Prometheus
  scrape and would be mangled to 'exported_job'; identifiers are PII/
  cardinality bombs);
- counters carry at most 3 bounded labels, histograms at most 2;
- the freshness gauge uses the 'refresh_job' label;
- gauge vocabularies come from the bounded product constants.
"""

from __future__ import annotations

import inspect

from prometheus_client import Counter, Gauge, Histogram

import src.infrastructure.observability.metrics_product as mp

FORBIDDEN_LABELS = {"job", "user_id", "run_id", "result_id", "workflow_id", "uuid"}


def _collectors() -> list[tuple[str, object]]:
    return [
        (name, obj)
        for name, obj in inspect.getmembers(mp)
        if isinstance(obj, (Counter, Gauge, Histogram))
    ]


def test_module_exposes_the_contract_families() -> None:
    names = {name for name, _ in _collectors()}
    assert {
        "product_outcomes_total",
        "product_users_with_useful_outcome",
        "product_value_penetration_ratio",
        "product_activation_rate",
        "product_retention_rate",
        "product_funnel_users",
        "product_data_quality_ratio",
        "product_metrics_last_refresh_timestamp_seconds",
    } <= names


def test_no_forbidden_label_names() -> None:
    for name, collector in _collectors():
        labels = set(getattr(collector, "_labelnames", ()))
        assert not (labels & FORBIDDEN_LABELS), f"{name} carries forbidden labels"


def test_cardinality_budget() -> None:
    for name, collector in _collectors():
        labels = getattr(collector, "_labelnames", ())
        if isinstance(collector, Counter):
            assert len(labels) <= 3, f"{name}: counters carry <= 3 bounded labels"
        if isinstance(collector, Histogram):
            assert len(labels) <= 2, f"{name}: histograms carry <= 2 labels"


def test_freshness_gauge_uses_refresh_job_label() -> None:
    labels = mp.product_metrics_last_refresh_timestamp_seconds._labelnames
    assert tuple(labels) == ("refresh_job",)


def test_outcome_counter_label_names() -> None:
    assert tuple(mp.product_outcomes_total._labelnames) == (
        "result_type",
        "domain",
        "evidence",
    )
