"""How long bulk indexing may wait for the embedding provider, and what bounds it.

An indexing path that declares itself patient serves the delay a quota refusal
names (ADR-254 amendment 2026-11-10). That wait happens inside one embedding
batch of one document, and a document's lease is renewed BEFORE each batch
(ADR-129): a patience as long as the lease would let the reaper take a document
that is merely waiting. The composed ``Settings`` refuses that contradiction at
boot — where the deployment's own preflight reads it before anything is
switched.
"""

from __future__ import annotations

import pytest

from src.core.config import Settings, get_settings
from src.core.constants import (
    EMBEDDING_PROVIDER_DELAY_JITTER_SECONDS,
    EMBEDDING_PROVIDER_DELAY_MARGIN_SECONDS,
)

pytestmark = pytest.mark.unit


_ONE_WAIT_MARGINS = (
    EMBEDDING_PROVIDER_DELAY_MARGIN_SECONDS + EMBEDDING_PROVIDER_DELAY_JITTER_SECONDS
)


def _waits_per_batch(settings: Settings) -> int:
    """How many times one embedding batch may sleep: once between two attempts."""
    return settings.embedding_retry_max_attempts - 1


def _longest_wait(settings: Settings) -> float:
    """The longest one embedding batch may sleep in all, waiting for the provider."""
    one_wait = settings.embedding_patient_retry_max_wait_seconds + _ONE_WAIT_MARGINS
    return _waits_per_batch(settings) * one_wait


def test_the_shipped_patience_covers_a_per_minute_quota() -> None:
    """Production, 2026-11-09: the provider asked for 20 to 49 seconds, and a
    per-minute quota cannot ask for more than its minute."""
    assert get_settings().embedding_patient_retry_max_wait_seconds >= 60


def test_the_shipped_patience_leaves_half_of_the_document_lease_to_the_calls() -> None:
    settings = get_settings()

    assert _waits_per_batch(settings) >= 1, "the shipped profile retries: this bound must bind"
    assert _longest_wait(settings) <= settings.rag_job_lease_ttl_seconds / 2


def test_every_wait_one_batch_may_make_is_counted() -> None:
    """A batch sleeps once between two attempts, so three retries are three
    waits under ONE lease renewal. A patience that fits once and not three
    times is refused, and the refusal names the setting that multiplied it."""
    base = get_settings().model_dump()
    base["rag_job_lease_ttl_seconds"] = 300
    base["rag_job_heartbeat_interval_seconds"] = 60
    base["embedding_patient_retry_max_wait_seconds"] = 60
    base["embedding_retry_max_attempts"] = 3
    assert Settings(**base).embedding_retry_max_attempts == 3  # two waits: 124 s of 150

    base["embedding_retry_max_attempts"] = 4  # three waits: 186 s of 150
    with pytest.raises(ValueError, match="embedding_retry_max_attempts"):
        Settings(**base)


def test_a_single_attempt_never_waits_whatever_the_patience() -> None:
    """No retry, no wait: nothing can outlast the lease, so nothing is refused."""
    base = get_settings().model_dump()
    base["embedding_retry_max_attempts"] = 1
    base["embedding_patient_retry_max_wait_seconds"] = base["rag_job_lease_ttl_seconds"]

    assert Settings(**base).embedding_retry_max_attempts == 1


def test_a_patience_longer_than_half_the_document_lease_is_refused() -> None:
    base = get_settings().model_dump()
    base["embedding_retry_max_attempts"] = 2  # one wait: the bound is the patience itself
    base["rag_job_lease_ttl_seconds"] = 60
    base["rag_job_heartbeat_interval_seconds"] = 20
    base["embedding_patient_retry_max_wait_seconds"] = 60

    with pytest.raises(ValueError, match="embedding_patient_retry_max_wait_seconds"):
        Settings(**base)


def test_shortening_the_lease_alone_is_refused_too() -> None:
    """The contradiction is caught from either side."""
    base = get_settings().model_dump()
    base["embedding_retry_max_attempts"] = 2
    base["embedding_patient_retry_max_wait_seconds"] = 60
    base["rag_job_lease_ttl_seconds"] = 90
    base["rag_job_heartbeat_interval_seconds"] = 30

    with pytest.raises(ValueError, match="embedding_patient_retry_max_wait_seconds"):
        Settings(**base)


def test_the_exact_boundary_is_accepted() -> None:
    base = get_settings().model_dump()
    base["embedding_retry_max_attempts"] = 3
    base["embedding_patient_retry_max_wait_seconds"] = (
        base["rag_job_lease_ttl_seconds"] / 2 / 2 - _ONE_WAIT_MARGINS
    )

    settings = Settings(**base)

    assert _longest_wait(settings) == settings.rag_job_lease_ttl_seconds / 2


def test_zero_switches_patience_off_and_is_always_consistent() -> None:
    base = get_settings().model_dump()
    base["rag_job_lease_ttl_seconds"] = 30
    base["rag_job_heartbeat_interval_seconds"] = 10
    base["embedding_patient_retry_max_wait_seconds"] = 0

    assert Settings(**base).embedding_patient_retry_max_wait_seconds == 0
