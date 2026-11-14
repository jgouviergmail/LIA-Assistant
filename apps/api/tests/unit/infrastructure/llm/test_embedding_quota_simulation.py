"""The 2026-11-09 indexing burst, replayed against a provider with a per-minute quota.

What production measured that evening, and what this simulation is calibrated on:

- the provider counts every embedded CONTENT as a request, 3,000 per minute
  (``embed_content_paid_tier_requests``, read in its own refusal);
- a label of about 2,500 threads, 15 chunks each, was pushed at roughly one and
  a half times that rate;
- every refusal named the delay to the next minute in its structure, rounded
  DOWN to whole seconds (``40s`` beside « retry in 40.38414246s »);
- the client retried one second later: 253 documents failed.

The provider here is a double with exactly those rules and a virtual clock, so
the run is instant and deterministic. Everything else is the real funnel: the
real retry loop, the real reading of the provider's delay, the real patience
scope. It answers the question a unit test of one refusal cannot: over a whole
burst, does every document end up embedded?
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from google.genai.errors import ClientError
from langchain_google_genai._common import GoogleGenerativeAIError

from src.core.exceptions import MaxRetriesExceededError
from src.infrastructure.llm.embedding_patience import patient_embeddings
from src.infrastructure.llm.gemini_embeddings import GeminiRetrievalEmbeddings
from src.infrastructure.rate_limiting.slot_waiter import SlotOutcome

pytestmark = pytest.mark.unit

_MODULE = "src.infrastructure.llm.gemini_embeddings"
#: The provider's quota, as its own refusal states it.
_CONTENTS_PER_MINUTE = 3000
#: The burst: documents, chunks per document, seconds one provider call takes.
#: 15 chunks every 0.2 s is 4,500 contents a minute — one and a half times the quota.
_DOCUMENTS = 2500
_CHUNKS_PER_DOCUMENT = 15
_CALL_SECONDS = 0.2
_WINDOW_SECONDS = 60.0


class _VirtualClock:
    """Time that moves only when something waits."""

    def __init__(self) -> None:
        self.now = 0.0

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


class _PerMinuteProvider:
    """The provider's quota as measured: fixed minutes, counted per content."""

    def __init__(self, clock: _VirtualClock) -> None:
        self._clock = clock
        self._minute = 0
        self._used = 0
        self.refusals = 0

    async def aembed_documents(self, texts: list[str], **_kwargs: object) -> list[list[float]]:
        await self._clock.sleep(_CALL_SECONDS)
        minute = int(self._clock.now // _WINDOW_SECONDS)
        if minute != self._minute:
            self._minute, self._used = minute, 0
        if self._used + len(texts) > _CONTENTS_PER_MINUTE:
            self.refusals += 1
            until_reset = _WINDOW_SECONDS - (self._clock.now % _WINDOW_SECONDS)
            raise self._refusal(retry_delay=f"{int(until_reset)}s")
        self._used += len(texts)
        return [[0.1] for _ in texts]

    @staticmethod
    def _refusal(*, retry_delay: str) -> Exception:
        provider_error = ClientError(
            429,
            {
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "message": "Embed content requests per minute limit exceeded on Tier 1.",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": retry_delay,
                        }
                    ],
                }
            },
        )
        try:
            raise GoogleGenerativeAIError("Error embedding content") from provider_error
        except GoogleGenerativeAIError as wrapped:
            return wrapped


@contextmanager
def _undeclared() -> Iterator[None]:
    """Work that says nothing about itself: the default of every caller."""
    yield


async def _index_the_label(
    *, patient: bool, margin: float | None = None
) -> tuple[int, int, float, int]:
    """Embed the whole label once, one document after the other.

    Returns:
        Documents embedded, documents failed, virtual minutes elapsed, and the
        refusals the provider issued.
    """
    clock = _VirtualClock()
    provider = _PerMinuteProvider(clock)
    with patch(f"{_MODULE}.GoogleGenerativeAIEmbeddings"):
        embeddings = GeminiRetrievalEmbeddings(model="models/gemini-embedding-001")
    embeddings._client.aembed_documents = provider.aembed_documents
    chunks = ["a chunk of a mail thread"] * _CHUNKS_PER_DOCUMENT
    embedded = failed = 0
    patches = [
        patch(f"{_MODULE}.wait_for_slot", AsyncMock(return_value=SlotOutcome.ACQUIRED)),
        patch("asyncio.sleep", clock.sleep),
        patch(f"{_MODULE}._jitter_seconds", return_value=0.5),
    ]
    if margin is not None:
        patches.append(patch(f"{_MODULE}.EMBEDDING_PROVIDER_DELAY_MARGIN_SECONDS", margin))
    for active in patches:
        active.start()
    try:
        with patient_embeddings() if patient else _undeclared():
            for _ in range(_DOCUMENTS):
                try:
                    await embeddings.aembed_documents(chunks)
                except MaxRetriesExceededError:
                    failed += 1
                else:
                    embedded += 1
    finally:
        for active in reversed(patches):
            active.stop()
    return embedded, failed, clock.now / 60, provider.refusals


async def test_declared_indexing_embeds_every_document_at_the_providers_own_pace() -> None:
    embedded, failed, minutes, refusals = await _index_the_label(patient=True)

    assert (embedded, failed) == (_DOCUMENTS, 0)
    # The quota is the pace: 37,500 contents at 3,000 a minute, the last minute
    # only partly used. Production took 13 minutes for 38,249 contents,
    # failures and their repeats included.
    expected = _DOCUMENTS * _CHUNKS_PER_DOCUMENT / _CONTENTS_PER_MINUTE
    assert expected - 1 <= minutes <= expected + 1
    # One refusal a minute tells the batch to wait; none is spent on a retry
    # that could not succeed.
    assert refusals <= minutes + 1


async def test_undeclared_work_fails_its_documents_instead_of_waiting() -> None:
    """The other side, and why the declaration matters: without it the burst
    keeps hitting a quota it was told to wait for. (An embedding on a chat turn
    is one call, not a burst — failing it at once is the point.)"""
    embedded, failed, _minutes, refusals = await _index_the_label(patient=False)

    assert failed > 0
    assert embedded + failed == _DOCUMENTS
    # Nearly every refusal ends its document at once: no retry is spent on a
    # delay the provider named as long. The few that ARE retried named a delay
    # within the ordinary one-second wait — the last second of a minute.
    assert failed <= refusals
    assert failed >= 0.95 * refusals


async def test_without_its_margin_the_wait_ends_before_the_quota_resets() -> None:
    """The structured delay is rounded down: waiting it to the second lands the
    retry a fraction early, the provider refuses again, and the document fails.
    The margin is what makes the wait sufficient."""
    with patch(f"{_MODULE}._jitter_seconds", return_value=0.0):
        embedded, failed, _minutes, _refusals = await _index_the_label(patient=True, margin=0.0)

    assert failed > 0, "a margin of zero must be shown to be too little"
    assert embedded + failed == _DOCUMENTS
