"""The NATURE of a provider refusal is a metric, not only a log line.

``embedding_api_calls_total{status="error"}`` says an attempt failed and nothing
more. On 2026-09-05 the diagnostician had to say "no error log is provided"
while 8 attempts had answered ``500 INTERNAL`` — the kind was in Loki only.
``embedding_provider_errors_total{reason}`` carries the classification the retry
already computes (``embedding_retry_reason``), so a rate can be told apart from a
quota (``http_429``), a provider outage (``http_500``) or a permanent refusal —
without a single log read.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.llm import gemini_embeddings as mod
from src.infrastructure.llm.gemini_embeddings import GeminiRetrievalEmbeddings
from src.infrastructure.rate_limiting.slot_waiter import SlotOutcome

pytestmark = pytest.mark.unit

_SLOT = "src.infrastructure.llm.gemini_embeddings.wait_for_slot"


def _embeddings() -> GeminiRetrievalEmbeddings:
    with patch("src.infrastructure.llm.gemini_embeddings.GoogleGenerativeAIEmbeddings"):
        return GeminiRetrievalEmbeddings(model="models/gemini-embedding-001")


class _CodedError(Exception):
    """A provider error carrying the status code the SDK sets on its errors."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


async def _run_one_attempt(error: Exception) -> list[tuple[str, str]]:
    """Run a single provider attempt that raises ``error``; return the
    ``(model, reason)`` label pairs the metric was incremented with."""
    embeddings = _embeddings()
    embeddings._client.aembed_query = AsyncMock(side_effect=error)
    seen: list[tuple[str, str]] = []
    with patch.object(mod, "embedding_provider_errors_total") as metric:
        metric.labels.side_effect = lambda **kw: type(
            "M", (), {"inc": lambda _s, *a: seen.append((kw["model"], kw["reason"]))}
        )()
        with patch(_SLOT, AsyncMock(return_value=SlotOutcome.ACQUIRED)):
            with patch("asyncio.sleep", AsyncMock()):
                with pytest.raises(Exception):  # noqa: B017 — the failure itself is not under test
                    await embeddings._attempt(
                        lambda: embeddings._client.aembed_query("x"),
                        token_count=1,
                        operation="embed_query",
                    )
    return seen


class TestTheReasonIsTheRetrysClassification:
    async def test_a_coded_500_is_counted_as_http_500(self) -> None:
        seen = await _run_one_attempt(_CodedError(500, "Internal error encountered."))
        assert seen == [("gemini-embedding-001", "http_500")]

    async def test_a_coded_429_is_counted_as_http_429(self) -> None:
        seen = await _run_one_attempt(_CodedError(429, "Quota exceeded"))
        assert seen == [("gemini-embedding-001", "http_429")]

    async def test_a_message_only_transient_keeps_its_message_prefix(self) -> None:
        seen = await _run_one_attempt(RuntimeError("Error embedding content: 500 INTERNAL."))
        assert seen == [("gemini-embedding-001", "message:http_500")]

    async def test_a_permanent_refusal_is_counted_as_permanent(self) -> None:
        seen = await _run_one_attempt(RuntimeError("400 INVALID_ARGUMENT: API key not valid"))
        assert seen == [("gemini-embedding-001", "permanent")]


class TestTheMetricIsDeclaredWhereTheOthersAre:
    def test_it_lives_in_tracked_embeddings_with_a_bounded_label_set(self) -> None:
        from src.infrastructure.llm.tracked_embeddings import embedding_provider_errors_total

        assert embedding_provider_errors_total._labelnames == ("model", "reason")
