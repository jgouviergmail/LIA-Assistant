"""Durable-job settings + heartbeat<lease invariant (audit F001, Phase 1 T2)."""

from __future__ import annotations


def test_rag_job_defaults_present_and_sane() -> None:
    from src.core.config import settings

    assert settings.rag_job_lease_ttl_seconds >= 1
    assert settings.rag_job_heartbeat_interval_seconds >= 1
    assert settings.rag_job_max_attempts >= 1
    assert settings.rag_job_reaper_interval_seconds >= 1
    assert settings.rag_job_reaper_grace_seconds >= 1
    assert settings.rag_job_reaper_batch_size >= 1
    assert settings.rag_job_reaper_concurrency >= 1


def test_heartbeat_interval_strictly_below_lease_ttl() -> None:
    # The lease must be renewed before it expires, otherwise the reaper would
    # requeue a live job.
    from src.core.config import settings

    assert settings.rag_job_heartbeat_interval_seconds < settings.rag_job_lease_ttl_seconds
