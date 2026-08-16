"""Error classification reads the HTTP status first (ADR-220, ex-F6).

``_classify_error`` guessed on ``str(exception)`` substrings: any message
containing "429"/"500"/"502"/"503"/"529" became "transient" — a context-length
error citing "4290 tokens" told the user "the service is saturated, retry"
(retrying can never fix it), and a Pydantic bound of 503 did the same. The
three most frequent OPERATIONS failures (bad key → 401, model not allowed →
403, model name typo → 404) all fell into "unknown" and produced the least
useful message, while the SDK exposed ``status_code`` on the exception the
whole time.

Truth table: status code first, SDK exception type second, guarded keywords
last. The historical false positives are pinned as regression cases.
"""

from __future__ import annotations

import pytest

from src.domains.agents.api.error_messages import SSEErrorMessages

LANGS = ("fr", "en", "es", "de", "it", "zh-CN")


class _WithStatus(Exception):
    """Provider-SDK-shaped exception: ``status_code`` on the exception."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class _WithResponseStatus(Exception):
    """httpx-shaped exception: status on ``exc.response.status_code``."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)

        class _Resp:
            pass

        self.response = _Resp()
        self.response.status_code = status_code


def _named(name: str, message: str = "boom") -> Exception:
    """An exception whose class NAME matches an SDK type (no status attr)."""
    return type(name, (Exception,), {})(message)


class TestStatusCodeFirst:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (401, "auth"),
            (403, "auth"),
            (402, "quota"),
            (404, "not_found"),
            (408, "timeout"),
            (429, "transient"),
            (500, "transient"),
            (502, "transient"),
            (503, "transient"),
            (529, "transient"),
            (400, "unknown"),
            (422, "unknown"),
        ],
    )
    def test_status_code_decides(self, status: int, expected: str) -> None:
        assert SSEErrorMessages._classify_error(_WithStatus("x", status)) == expected

    def test_response_status_code_path(self) -> None:
        assert SSEErrorMessages._classify_error(_WithResponseStatus("x", 401)) == "auth"

    def test_status_beats_misleading_text(self) -> None:
        """A 401 whose message mentions a timeout is still an auth failure."""
        exc = _WithStatus("connection timeout while validating api key", 401)
        assert SSEErrorMessages._classify_error(exc) == "auth"


class TestHistoricalFalsePositives:
    """The audit's measured misclassifications — all must stop being transient."""

    @pytest.mark.parametrize(
        "message",
        [
            "maximum context length is 4096 tokens, however you requested 4290 tokens",
            "max_tokens must be <= 5000 for this model",
            "Input should be less than or equal to 503",
        ],
    )
    def test_token_and_validation_messages_are_not_transient(self, message: str) -> None:
        assert SSEErrorMessages._classify_error(ValueError(message)) == "unknown"

    def test_google_style_leading_code_stays_transient(self) -> None:
        """google-api-core prefixes the numeric code — that context is real."""
        exc = Exception("429 Quota exceeded for quota metric 'Generate requests'")
        assert SSEErrorMessages._classify_error(exc) == "transient"

    def test_error_code_context_stays_transient(self) -> None:
        assert SSEErrorMessages._classify_error(Exception("Error code: 529")) == "transient"


class TestSdkTypeNames:
    @pytest.mark.parametrize(
        ("type_name", "expected"),
        [
            ("RateLimitError", "transient"),
            ("InternalServerError", "transient"),
            ("APIConnectionError", "transient"),
            ("AuthenticationError", "auth"),
            ("PermissionDeniedError", "auth"),
            ("NotFoundError", "not_found"),
            ("APITimeoutError", "timeout"),
        ],
    )
    def test_type_name_decides_without_status(self, type_name: str, expected: str) -> None:
        assert SSEErrorMessages._classify_error(_named(type_name)) == expected


class TestLastResortKeywords:
    @pytest.mark.parametrize(
        ("message", "expected"),
        [
            ("Incorrect API key provided: sk-***", "auth"),
            ("invalid_api_key", "auth"),
            ("Insufficient Balance", "quota"),
            ("insufficient_quota: check your plan and billing details", "quota"),
            ("model_not_found: the model `gpt-x` does not exist", "not_found"),
            ("overloaded, try again", "transient"),
            ("request timeout", "timeout"),
        ],
    )
    def test_keywords(self, message: str, expected: str) -> None:
        assert SSEErrorMessages._classify_error(Exception(message)) == expected


class TestMessagesForNewCategories:
    """Every dispatcher names the failure instead of the vaguest message."""

    @pytest.mark.parametrize("lang", LANGS)
    def test_six_languages_and_distinct_from_generic(self, lang: str) -> None:
        auth = SSEErrorMessages.generic_error(_WithStatus("x", 401), language=lang)
        not_found = SSEErrorMessages.generic_error(_WithStatus("x", 404), language=lang)
        quota = SSEErrorMessages.generic_error(_WithStatus("x", 402), language=lang)
        generic = SSEErrorMessages.generic_error(ValueError("boom"), language=lang)

        assert len({auth, not_found, quota, generic}) == 4  # four distinct texts

    @pytest.mark.parametrize(
        "dispatcher",
        [
            SSEErrorMessages.generic_error,
            SSEErrorMessages.stream_error,
            SSEErrorMessages.hitl_resumption_error,
            SSEErrorMessages.graph_execution_error,
        ],
    )
    def test_every_dispatcher_routes_the_new_categories(self, dispatcher) -> None:
        """The four category ladders stay in lockstep (single helper)."""
        auth = dispatcher(_WithStatus("x", 401), language="en")
        generic = dispatcher(ValueError("boom"), language="en")

        assert auth != generic
        assert "key" in auth or "credentials" in auth or "configuration" in auth
