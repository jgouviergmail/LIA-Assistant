"""One classifier decides whether an embedding failure is worth another try.

Two retry loops used to answer this independently. The RAG system indexer read
the SDK's status code structurally; the embedding client did not classify at
all, because it could not retry. A single provider judged by two rules is a
rule that drifts, and the drift is invisible: the same failure retried in one
place and abandoned in the other looks like two different providers.

The order matters and is the whole design. Structural first — a status code
survives a vendor rewording, a sentence does not. Message second, and only when
the chain carries no code at all, because that is exactly how the production
incident of 2026-09-01 arrived.
"""

from __future__ import annotations

import pytest

from src.infrastructure.llm.embedding_errors import (
    embedding_retry_reason,
    is_transient_embedding_error,
)

pytestmark = pytest.mark.unit


class _Coded(Exception):
    """Stands in for ``google.genai.errors.APIError``, which carries ``code``."""

    def __init__(self, code: int, message: str = "provider said no") -> None:
        super().__init__(message)
        self.code = code


class TestStructuralClassificationComesFirst:
    @pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504])
    def test_a_retryable_status_is_read_from_the_exception(self, code: int) -> None:
        assert embedding_retry_reason(_Coded(code)) == f"http_{code}"

    @pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
    def test_a_permanent_status_is_not_retried(self, code: int) -> None:
        assert embedding_retry_reason(_Coded(code)) is None

    def test_the_code_is_found_through_the_langchain_WRAPPER(self) -> None:
        """langchain re-raises every provider failure wrapped, so the code that
        matters is almost never on the exception the caller catches."""
        wrapped = RuntimeError("Error embedding content")
        wrapped.__cause__ = _Coded(429)
        assert embedding_retry_reason(wrapped) == "http_429"

    def test_the_structural_reading_WINS_over_a_misleading_message(self) -> None:
        """A permanent failure whose text happens to contain a retryable-looking
        number must not be retried: the code is the fact, the prose is not."""
        wrapped = RuntimeError("gave up after 429 attempts")
        wrapped.__cause__ = _Coded(400)
        assert embedding_retry_reason(wrapped) is None

    def test_transport_failures_are_retryable_on_their_type(self) -> None:
        """The production host is a Raspberry Pi on WiFi: these are ordinary."""
        assert embedding_retry_reason(TimeoutError()) == "TimeoutError"
        assert embedding_retry_reason(ConnectionError()) == "ConnectionError"

    def test_a_cause_cycle_terminates_instead_of_hanging(self) -> None:
        first = RuntimeError("a")
        second = RuntimeError("b")
        first.__cause__ = second
        second.__cause__ = first
        assert embedding_retry_reason(first) is None


class TestMessageFallback:
    def test_the_real_production_payload_is_retryable(self) -> None:
        """Measured 2026-09-01. No status code anywhere in the chain — dropping
        the fallback would have made the actual incident unretryable."""
        exc = RuntimeError(
            "Error embedding content (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. "
            "{'error': {'code': 429, 'message': 'Quota exceeded for "
            "aiplatform.googleapis.com/global_embed_content_requests_per_minute_per_base_model'}}"
        )
        reason = embedding_retry_reason(exc)
        assert reason is not None and reason.startswith("message:")

    def test_the_other_failure_seen_in_production_is_retryable(self) -> None:
        exc = RuntimeError("Error embedding content: 500 INTERNAL. Internal error encountered.")
        assert is_transient_embedding_error(exc) is True

    @pytest.mark.parametrize(
        "message",
        [
            "400 INVALID_ARGUMENT: text is empty",
            "403 PERMISSION_DENIED: API key not valid",
            "401 UNAUTHENTICATED",
            "404 NOT_FOUND: model does not exist",
        ],
    )
    def test_a_permanent_message_is_not_retried(self, message: str) -> None:
        assert is_transient_embedding_error(RuntimeError(message)) is False

    def test_the_reason_says_WHICH_route_classified_it(self) -> None:
        """A log that cannot tell a structural verdict from a text guess cannot
        tell you the fallback has quietly become the only thing working."""
        assert embedding_retry_reason(_Coded(429)).startswith("http_")
        assert embedding_retry_reason(RuntimeError("429")).startswith("message:")


class TestBothLoopsAskTheSameQuestion:
    def test_the_rag_indexer_uses_this_module_rather_than_a_copy(self) -> None:
        from src.domains.rag_spaces import system_indexer
        from src.infrastructure.llm import embedding_errors

        assert system_indexer._retry_reason is embedding_errors.embedding_retry_reason

    def test_the_embedding_client_uses_it_too(self) -> None:
        from src.infrastructure.llm import embedding_errors, gemini_embeddings

        assert (
            gemini_embeddings.is_transient_embedding_error
            is embedding_errors.is_transient_embedding_error
        )


class TestANumberInsideAnotherNumberIsNotAStatusCode:
    """The text fallback matched "500" as a plain substring.

    "500" occurs inside "1500", so a PERMANENT failure whose message quotes a
    limit — "input token count 1500 exceeds the maximum" — was classified
    transient and retried until the budget ran out. A hard failure turned into
    a slow one, and the caller learned the truth several seconds later.
    """

    @pytest.mark.parametrize(
        "message",
        [
            "input token count 1500 exceeds the maximum",
            "output_dimensionality 3072 is above 1502",
            "batch of 5040 texts is too large",
        ],
    )
    def test_a_limit_quoted_in_a_permanent_error_is_not_retried(self, message: str) -> None:
        assert embedding_retry_reason(Exception(message)) is None

    @pytest.mark.parametrize(
        "message",
        [
            "429 Resource has been exhausted",
            "got status 503 from the backend",
            "HTTP 500: internal",
        ],
    )
    def test_a_real_status_number_is_still_recognised(self, message: str) -> None:
        reason = embedding_retry_reason(Exception(message))
        assert reason is not None and reason.startswith("message:")
