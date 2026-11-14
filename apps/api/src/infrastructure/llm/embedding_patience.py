"""Which embeddings may wait for the provider (ADR-254 amendment 2026-11-10).

One embedding client serves a person's turn and a background batch, so the
resilience budget is ONE tight profile: an embedding on somebody's turn must
never wait for a quota. Bulk indexing is the opposite case. Measured on
2026-11-09, a label of 2,502 threads met the provider's per-minute quota 581
times; every refusal named the delay to serve (20 to 49 seconds), every one was
retried a second later, and 253 documents failed for it.

Patience is therefore DECLARED by the work that can afford it, never inherited
and never the default: forgetting to declare costs nobody a second. It travels
in a ``ContextVar`` - no per-call flag to thread through five layers, no
per-request state on the shared client - and into the tasks a declared scope
starts, which is how a document's concurrent batches stay patient.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_PATIENT: ContextVar[bool] = ContextVar("embedding_patient", default=False)


@contextmanager
def patient_embeddings() -> Iterator[None]:
    """Declare the enclosed embeddings as bulk work that may wait for the provider.

    Yields:
        Nothing: the body is the indexing work.
    """
    token = _PATIENT.set(True)
    try:
        yield
    finally:
        _PATIENT.reset(token)


def embeddings_may_wait() -> bool:
    """Whether the current work declared it may wait for the provider."""
    return _PATIENT.get()
