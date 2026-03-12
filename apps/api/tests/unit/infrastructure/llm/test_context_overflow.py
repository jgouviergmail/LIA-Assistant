"""
Unit tests for ContextOverflowError classification.

Validates that ContextOverflowError (langchain-core 1.2.10+) is classified
via isinstance (type-safe) in _classify_llm_error, while preserving the
string-based fallback for non-LangChain providers.
"""

import pytest


@pytest.mark.unit
class TestContextOverflowClassification:

    def test_classify_context_overflow_error_by_type(self):
        """ContextOverflowError is classified via isinstance (type-safe)."""
        from langchain_core.exceptions import ContextOverflowError

        from src.infrastructure.observability.callbacks import MetricsCallbackHandler

        error = ContextOverflowError("Context window exceeded for model gpt-4.1")
        result = MetricsCallbackHandler._classify_llm_error(error)
        assert result == "context_length_exceeded"

    def test_classify_context_overflow_string_fallback(self):
        """String-based detection still works for non-LangChain providers."""
        from src.infrastructure.observability.callbacks import MetricsCallbackHandler

        error = ValueError("maximum context length exceeded")
        result = MetricsCallbackHandler._classify_llm_error(error)
        assert result == "context_length_exceeded"

    def test_classify_other_errors_unchanged(self):
        """Other error types are not affected by the new type check."""
        from src.infrastructure.observability.callbacks import MetricsCallbackHandler

        assert (
            MetricsCallbackHandler._classify_llm_error(ValueError("rate_limit exceeded"))
            == "rate_limit"
        )
        assert MetricsCallbackHandler._classify_llm_error(TimeoutError("timeout")) == "timeout"
        assert (
            MetricsCallbackHandler._classify_llm_error(ValueError("some random error")) == "unknown"
        )

    def test_context_overflow_is_exception_subclass(self):
        """Confirms ContextOverflowError is catchable as Exception."""
        from langchain_core.exceptions import ContextOverflowError

        assert issubclass(ContextOverflowError, Exception)
