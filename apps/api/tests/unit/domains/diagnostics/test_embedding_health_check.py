"""Platform health must see the embedding provider.

Measured 2026-09-01: embeddings failed on 11 of 24 calls (46 %) for half an
hour, silently costing turns their RAG context, their journal context, their
memory extraction and their message indexing — and "Platform health" reported
everything fine the entire time.

The reason was not a missing metric. `embedding_api_calls_total` was already on
two Grafana dashboards. It was that the only LLM-shaped check reads
`llm_api_errors_total` / `llm_api_calls_total` — the CHAT COMPLETION series.
Embeddings emit a different one, so no check was looking.

A health page whose blind spots are invisible is worse than no health page: it
converts "we do not know" into "everything is fine".
"""

from __future__ import annotations

import pytest

from src.domains.diagnostics.checks import ALL_CHECKS, PROM_CHECKS
from src.domains.diagnostics.query_catalogue import QUERY_CATALOGUE

pytestmark = pytest.mark.unit


def _check(check_id: str):
    for check in ALL_CHECKS:
        if check.check_id == check_id:
            return check
    return None


class TestEmbeddingsAreWatched:
    def test_a_check_covers_the_embedding_provider(self) -> None:
        assert _check("embedding_failure_rate") is not None, (
            "No check reads the embedding series, so a provider refusing half "
            "the calls leaves the health page green."
        )

    def test_it_reads_the_EMBEDDING_series_not_the_completion_one(self) -> None:
        """The exact confusion that caused the blind spot: both are 'the LLM',
        they are not the same metric."""
        query = QUERY_CATALOGUE["embedding_failure_rate"]
        assert any("embedding" in metric for metric in query.lia_metrics)
        assert not any("llm_api" in metric for metric in query.lia_metrics)

    def test_it_reads_OUTCOMES_so_a_recovered_retry_is_not_an_incident(self) -> None:
        """With retries (ADR-254) one recovered failure is several provider
        calls. A check on attempts would open an incident for something that
        repaired itself before anyone looked."""
        query = QUERY_CATALOGUE["embedding_failure_rate"]
        assert "embedding_call_outcomes_total" in query.promql_template

    def test_an_idle_instance_reads_zero_percent_not_unknown(self) -> None:
        """A counter that never fired exposes no series; without the guard the
        health page would show 'no data' on a perfectly healthy instance."""
        query = QUERY_CATALOGUE["embedding_failure_rate"]
        assert "or vector(0)" in query.promql_template

    def test_it_is_correlated_with_the_alert_that_watches_the_same_thing(self) -> None:
        check = _check("embedding_failure_rate")
        assert check is not None
        assert check.alertname == "EmbeddingOperationsFailing"

    def test_its_thresholds_come_from_settings_like_every_other_check(self) -> None:
        from src.core.config import settings

        check = _check("embedding_failure_rate")
        assert check is not None
        warn = getattr(settings, check.warn_setting)
        crit = getattr(settings, check.crit_setting)
        assert (
            0 < warn < crit <= 100
        ), "A warn above its crit can never degrade before it is critical."


class TestTheCheckSetStaysCoherent:
    def test_every_prom_check_declares_a_query_that_exists(self) -> None:
        """Guards the whole family, not just the new one: a check pointing at a
        query id nobody defines fails silently at tick time."""
        known = set(QUERY_CATALOGUE)
        missing = [c.check_id for c in PROM_CHECKS if c.query_id not in known]
        assert not missing, f"checks with no query: {missing}"

    def test_every_check_id_is_unique(self) -> None:
        ids = [c.check_id for c in ALL_CHECKS]
        assert len(ids) == len(set(ids))
