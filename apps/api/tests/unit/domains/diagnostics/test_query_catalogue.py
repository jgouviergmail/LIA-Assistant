"""Named-query catalogue — the ONLY producer of PromQL in the subsystem.

Three properties are load-bearing:

1. structural completeness (asserted at boot): placeholders ⊆ declared params,
   params bounded, declared metrics actually present in the template;
2. every LIA-owned metric name resolves to a real producer (asserted HERE, in
   CI, against the live prometheus_client registry — the "dashboard query must
   resolve to an actual producer" rule, applied mechanically);
3. rendering clamps out-of-bounds parameters instead of erroring (ADR-184
   repair doctrine).
"""

from __future__ import annotations

import re

import pytest

from src.domains.diagnostics.query_catalogue import (
    EXTERNAL_METRICS_ALLOWLIST,
    QUERY_CATALOGUE,
    NamedQuery,
    QueryParam,
    assert_query_catalogue_completeness,
    render_query,
)


@pytest.mark.unit
class TestCatalogueStructure:
    def test_real_catalogue_passes_the_boot_assert(self) -> None:
        assert_query_catalogue_completeness()

    def test_catalogue_is_not_empty_and_keys_are_snake_case(self) -> None:
        assert QUERY_CATALOGUE
        for key in QUERY_CATALOGUE:
            assert re.fullmatch(r"[a-z0-9_]+", key), key

    def test_undeclared_placeholder_is_refused_by_the_assert(self) -> None:
        bad = NamedQuery(
            query_id="bad_query",
            title="Bad",
            promql_template="sum(rate(http_requests_total[{undeclared}m]))",
            params=(),
            unit="rps",
            lia_metrics=("http_requests_total",),
            external_metrics=(),
        )
        with pytest.raises(AssertionError):
            assert_query_catalogue_completeness({"bad_query": bad})

    def test_declared_metric_missing_from_template_is_refused(self) -> None:
        bad = NamedQuery(
            query_id="bad_query",
            title="Bad",
            promql_template="vector(1)",
            params=(),
            unit="count",
            lia_metrics=("http_requests_total",),
            external_metrics=(),
        )
        with pytest.raises(AssertionError):
            assert_query_catalogue_completeness({"bad_query": bad})

    def test_unknown_external_metric_is_refused(self) -> None:
        bad = NamedQuery(
            query_id="bad_query",
            title="Bad",
            promql_template="sum(mystery_exporter_bytes)",
            params=(),
            unit="bytes",
            lia_metrics=(),
            external_metrics=("mystery_exporter_bytes",),
        )
        with pytest.raises(AssertionError):
            assert_query_catalogue_completeness({"bad_query": bad})

    def test_every_external_metric_has_a_written_reason(self) -> None:
        for name, reason in EXTERNAL_METRICS_ALLOWLIST.items():
            assert isinstance(reason, str) and len(reason) > 10, name


@pytest.mark.unit
class TestLiaMetricsResolveToProducers:
    def test_lia_metric_names_exist_in_the_live_registry(self) -> None:
        # Importing the modules registers their metrics on the default REGISTRY.
        import prometheus_client

        import src.infrastructure.observability.metrics  # noqa: F401
        import src.infrastructure.observability.metrics_agents  # noqa: F401
        import src.infrastructure.observability.metrics_errors  # noqa: F401
        import src.infrastructure.resilience.circuit_breaker  # noqa: F401

        # A labelled metric with zero observations exposes NO samples, so we
        # resolve against family names + the sample suffixes their TYPE emits.
        suffixes_by_type = {
            "counter": ("_total",),
            "histogram": ("_bucket", "_count", "_sum"),
            "summary": ("_count", "_sum"),
            "gauge": ("",),
            "unknown": ("",),
        }
        resolvable: set[str] = set()
        for family in prometheus_client.REGISTRY.collect():
            for suffix in suffixes_by_type.get(family.type, ("",)):
                resolvable.add(f"{family.name}{suffix}")
        for query in QUERY_CATALOGUE.values():
            for metric in query.lia_metrics:
                assert (
                    metric in resolvable
                ), f"{query.query_id} references '{metric}' which no producer registers"


@pytest.mark.unit
class TestBootWiring:
    def test_failfast_validations_wire_the_catalogue_assert(self) -> None:
        """The validator only protects boot if the lifespan actually calls it."""
        import inspect

        import src.infrastructure.startup.registries as registries

        assert "_validate_diagnostics_registries" in inspect.getsource(
            registries.run_failfast_validations
        )
        assert "assert_query_catalogue_completeness" in inspect.getsource(
            registries._validate_diagnostics_registries
        )


@pytest.mark.unit
class TestRendering:
    def test_nominal_render_substitutes_the_window(self) -> None:
        promql = render_query("api_error_rate", window_minutes=15)
        assert "[15m]" in promql
        assert "{" not in promql.replace('{status=~"5.."}', "")  # no leftover placeholder

    def test_out_of_bounds_window_is_clamped_not_rejected(self) -> None:
        query = QUERY_CATALOGUE["api_error_rate"]
        max_window = int(query.params[0].max_value)
        promql = render_query("api_error_rate", window_minutes=10_000_000)
        assert f"[{max_window}m]" in promql
        promql_low = render_query("api_error_rate", window_minutes=0)
        min_window = int(query.params[0].min_value)
        assert f"[{min_window}m]" in promql_low

    def test_missing_param_uses_the_declared_default(self) -> None:
        query = QUERY_CATALOGUE["api_error_rate"]
        default = int(query.params[0].default)
        assert f"[{default}m]" in render_query("api_error_rate")

    def test_unknown_key_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            render_query("no_such_query")

    def test_param_bounds_are_published_on_the_definition(self) -> None:
        """An enforced bound is a published bound (ADR-184): tools read these."""
        param = QUERY_CATALOGUE["api_error_rate"].params[0]
        assert isinstance(param, QueryParam)
        assert param.min_value < param.max_value


@pytest.mark.unit
class TestRatioQueriesAreTotal:
    """A ratio whose numerator has no series must read 0, never "no data".

    Measured in production on 2026-08-28 (v1.34.0 first tick): on a healthy
    instance NO 5xx series exists, so `sum(rate(http_requests_total{status=~
    "5.."}[15m]))` is an EMPTY vector, the division yields empty, the check
    reports `unknown/no_data` — and `unknown` caps the snapshot at `degraded`.
    A permanently degraded panel on a perfectly healthy platform is a false
    alarm that teaches administrators to ignore it.
    """

    RATIO_KEYS = ("api_error_rate", "llm_failure_rate")

    @pytest.mark.parametrize("query_id", RATIO_KEYS)
    def test_numerator_falls_back_to_zero(self, query_id: str) -> None:
        promql = render_query(query_id, window_minutes=15)
        assert "or vector(0)" in promql, f"{query_id}: an absent numerator must read 0, not nothing"

    @pytest.mark.parametrize("query_id", RATIO_KEYS)
    def test_denominator_is_still_clamped(self, query_id: str) -> None:
        """Zero traffic must not divide by zero either."""
        assert "clamp_min(" in render_query(query_id, window_minutes=15)
