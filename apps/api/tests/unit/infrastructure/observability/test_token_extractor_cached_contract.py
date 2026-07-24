"""The billing invariant of ``TokenExtractor``: input tokens EXCLUDE cached ones.

``get_cached_cost_usd_eur`` prices the three buckets **additively**::

    input_tokens × input_price + cached_tokens × cached_price + output × output_price

Both OpenAI and Anthropic report a total that ALREADY CONTAINS the cache reads,
so the extractor must subtract them before handing the numbers over. Skip that
subtraction and every cached token is billed twice — once at the full input
rate, once at the discounted cached rate. Nothing raises; the invoice is simply
wrong, which is exactly the kind of defect that survives for months.

The extractor has three strategies and only the modern one documented (and
performed) the subtraction; these tests pin the invariant for all of them.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.infrastructure.observability.token_extractor import TokenExtractor

pytestmark = pytest.mark.unit


@pytest.fixture
def extractor() -> TokenExtractor:
    return TokenExtractor()


def _modern_result(usage_metadata: dict[str, Any], model: str = "gpt-4.1-mini") -> LLMResult:
    """Strategy 1 shape: usage on the message itself."""
    message = AIMessage(content="ok")
    message.usage_metadata = usage_metadata  # type: ignore[assignment]
    message.response_metadata = {"model_name": model}
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def _legacy_result(token_usage: dict[str, Any], model: str = "gpt-4.1-mini") -> LLMResult:
    """Strategy 2 shape: no usage on the message, only in llm_output."""
    message = AIMessage(content="ok")
    return LLMResult(
        generations=[[ChatGeneration(message=message)]],
        llm_output={"token_usage": token_usage, "model_name": model},
    )


# ============================================================================
# Strategy 1 — modern usage_metadata
# ============================================================================


class TestModernExtraction:
    def test_cache_read_is_subtracted_from_input(self, extractor: TokenExtractor) -> None:
        """1000 reported input tokens of which 400 were cache hits → 600 billed
        at the input rate and 400 at the cached rate."""
        usage = extractor.extract(
            _modern_result(
                {
                    "input_tokens": 1000,
                    "output_tokens": 50,
                    "input_token_details": {"cache_read": 400},
                }
            )
        )
        assert usage is not None
        assert usage.input_tokens == 600
        assert usage.cached_tokens == 400
        assert usage.output_tokens == 50

    def test_no_cache_leaves_input_untouched(self, extractor: TokenExtractor) -> None:
        usage = extractor.extract(_modern_result({"input_tokens": 1000, "output_tokens": 50}))
        assert usage is not None
        assert usage.input_tokens == 1000
        assert usage.cached_tokens == 0

    def test_cache_creation_stays_billed_as_input(self, extractor: TokenExtractor) -> None:
        """Cache WRITES are charged at (roughly) the input rate, so they must NOT
        be subtracted — only cache reads are."""
        usage = extractor.extract(
            _modern_result(
                {
                    "input_tokens": 1000,
                    "output_tokens": 50,
                    "input_token_details": {"cache_read": 0, "cache_creation": 300},
                }
            )
        )
        assert usage is not None
        assert usage.input_tokens == 1000
        assert usage.cached_tokens == 0

    def test_model_name_is_read_from_response_metadata(self, extractor: TokenExtractor) -> None:
        usage = extractor.extract(
            _modern_result({"input_tokens": 10, "output_tokens": 5}, model="claude-opus-4-8")
        )
        assert usage is not None
        assert usage.model_name == "claude-opus-4-8"


# ============================================================================
# Strategy 2 — legacy llm_output
# ============================================================================


class TestLegacyExtraction:
    def test_legacy_usage_is_extracted(self, extractor: TokenExtractor) -> None:
        usage = extractor.extract(_legacy_result({"prompt_tokens": 800, "completion_tokens": 40}))
        assert usage is not None
        assert usage.input_tokens == 800
        assert usage.output_tokens == 40

    def test_legacy_cached_tokens_are_also_subtracted(self, extractor: TokenExtractor) -> None:
        """Regression: the legacy branch read ``input_tokens`` and
        ``cached_tokens`` side by side WITHOUT subtracting, while the modern
        branch documents that providers include cache reads in the input total.
        Left as-is, every cached token was priced twice — full input rate on top
        of the discounted cached rate.
        """
        usage = extractor.extract(
            _legacy_result({"prompt_tokens": 1000, "completion_tokens": 50, "cached_tokens": 400})
        )
        assert usage is not None
        assert usage.cached_tokens == 400
        assert usage.input_tokens == 600, (
            "cached tokens must be removed from the input bucket, otherwise the "
            "cost function bills them twice"
        )

    def test_legacy_without_cache_is_unchanged(self, extractor: TokenExtractor) -> None:
        usage = extractor.extract(_legacy_result({"input_tokens": 700, "output_tokens": 30}))
        assert usage is not None
        assert usage.input_tokens == 700
        assert usage.cached_tokens == 0


# ============================================================================
# Absent usage
# ============================================================================


class TestNoUsage:
    def test_no_usage_anywhere_returns_none(self, extractor: TokenExtractor) -> None:
        """No invented numbers: an unusable response must yield None so the
        caller records nothing rather than a fabricated zero-cost call."""
        result = LLMResult(generations=[[ChatGeneration(message=AIMessage(content="ok"))]])
        assert extractor.extract(result) is None

    def test_empty_generations_returns_none(self, extractor: TokenExtractor) -> None:
        assert extractor.extract(LLMResult(generations=[])) is None


# ============================================================================
# The invariant, stated once
# ============================================================================


class TestBillingInvariant:
    @pytest.mark.parametrize(
        "result_factory",
        [
            lambda: _modern_result(
                {
                    "input_tokens": 1000,
                    "output_tokens": 10,
                    "input_token_details": {"cache_read": 250},
                }
            ),
            lambda: _legacy_result(
                {"prompt_tokens": 1000, "completion_tokens": 10, "cached_tokens": 250}
            ),
        ],
        ids=["modern", "legacy"],
    )
    def test_buckets_never_overlap(self, extractor: TokenExtractor, result_factory: Any) -> None:
        """Whatever the strategy, the reported total must be partitioned — not
        double-counted — across the input and cached buckets."""
        usage = extractor.extract(result_factory())
        assert usage is not None
        assert usage.input_tokens + usage.cached_tokens == 1000
