"""rag_jobs_recovered_total is defined with the expected labels (F001, T7).

The reaper integration tests exercise the increments end-to-end; this guards the
metric definition (label set) so a rename/removal fails fast in CI.
"""

from __future__ import annotations

from src.infrastructure.observability.metrics_rag_spaces import rag_jobs_recovered_total


def test_recovered_metric_accepts_expected_labels() -> None:
    # Both job types and both outcomes must resolve without raising.
    rag_jobs_recovered_total.labels(job_type="document", outcome="requeued").inc(0)
    rag_jobs_recovered_total.labels(job_type="document", outcome="failed").inc(0)
    rag_jobs_recovered_total.labels(job_type="sync", outcome="requeued").inc(0)
    rag_jobs_recovered_total.labels(job_type="sync", outcome="failed").inc(0)
