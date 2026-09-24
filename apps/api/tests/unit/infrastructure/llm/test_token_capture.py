"""Unit tests for the shared :class:`TokenCaptureHandler`.

Moved from ``tests/unit/domains/heartbeat/test_proactive_task.py`` when the
handler was hoisted out of ``heartbeat/prompts.py`` (it had a second private
copy in ``open_loop_extractor.py`` reading a different ``LLMResult`` surface —
the shared handler reads both, fallback-only, never double-counting).

Since ADR-306 it counts in the ONE reader's buckets (``usage_metadata.py``):
``tokens_in`` EXCLUDES the cache reads. It used to hand the RAW input to
callers that priced ``tokens_cache`` on top, so four of its five consumers
billed every cached token twice — at the full input rate and at the cached one.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.outputs import ChatGeneration, LLMResult

from src.infrastructure.llm.token_capture import TokenCaptureHandler


def _generation_with_usage(usage: dict | None) -> MagicMock:
    """Build a ChatGeneration mock whose message carries ``usage_metadata``."""
    message = MagicMock()
    message.usage_metadata = usage
    gen = MagicMock(spec=ChatGeneration)
    gen.message = message
    return gen


@pytest.mark.unit
class TestTokenCaptureHandler:
    """Behavioral contract of the shared token-capture callback."""

    def test_initial_state_zero(self):
        handler = TokenCaptureHandler()
        assert handler.tokens_in == 0
        assert handler.tokens_out == 0
        assert handler.tokens_cache == 0
        assert handler.tokens_cache_write == 0
        assert handler.has_usage is False

    def test_captures_tokens_from_usage_metadata(self):
        """The canonical per-generation ``usage_metadata`` surface is read."""
        handler = TokenCaptureHandler()
        gen = _generation_with_usage(
            {"input_tokens": 500, "output_tokens": 120, "cache_read_input_tokens": 50}
        )
        handler.on_llm_end(LLMResult(generations=[[gen]]))

        # The cache reads leave the billable input: they are priced apart.
        assert handler.tokens_in == 450
        assert handler.tokens_out == 120
        assert handler.tokens_cache == 50
        assert handler.has_usage is True

    def test_reads_nested_cache_details_shape(self):
        """Newer integrations report cache reads under ``input_token_details``."""
        handler = TokenCaptureHandler()
        gen = _generation_with_usage(
            {
                "input_tokens": 200,
                "output_tokens": 30,
                "input_token_details": {"cache_read": 80},
            }
        )
        handler.on_llm_end(LLMResult(generations=[[gen]]))
        assert handler.tokens_cache == 80
        assert handler.tokens_in == 120

    def test_captures_claude_cache_writes(self):
        """A write stays a billable input token; it is ALSO counted apart,
        because it owes the write surcharge on top (ADR-306)."""
        handler = TokenCaptureHandler()
        gen = _generation_with_usage(
            {
                "input_tokens": 6000,
                "output_tokens": 40,
                "input_token_details": {
                    "cache_read": 0,
                    "cache_creation": 0,
                    "ephemeral_5m_input_tokens": 5074,
                    "ephemeral_1h_input_tokens": 0,
                },
            }
        )
        handler.on_llm_end(LLMResult(generations=[[gen]]))
        assert handler.tokens_in == 6000
        assert handler.tokens_cache_write == 5074

    def test_accumulates_across_multiple_calls(self):
        """Counters accumulate across calls (retries are paid too)."""
        handler = TokenCaptureHandler()
        for _ in range(3):
            gen = _generation_with_usage(
                {"input_tokens": 100, "output_tokens": 30, "cache_read_input_tokens": 10}
            )
            handler.on_llm_end(LLMResult(generations=[[gen]]))

        assert handler.tokens_in == 270
        assert handler.tokens_out == 90
        assert handler.tokens_cache == 30

    def test_falls_back_to_llm_output_token_usage(self):
        """OpenAI-compatible aggregate shape is read when no usage_metadata."""
        handler = TokenCaptureHandler()
        gen = _generation_with_usage(None)
        result = LLMResult(
            generations=[[gen]],
            llm_output={
                "token_usage": {
                    "prompt_tokens": 400,
                    "completion_tokens": 90,
                    "prompt_tokens_details": {"cached_tokens": 25},
                }
            },
        )
        handler.on_llm_end(result)

        # The aggregate's prompt_tokens includes the cached ones, as usage_metadata does.
        assert handler.tokens_in == 375
        assert handler.tokens_out == 90
        assert handler.tokens_cache == 25

    def test_never_double_counts_when_both_surfaces_present(self):
        """usage_metadata wins; the aggregate fallback must NOT be added on top."""
        handler = TokenCaptureHandler()
        gen = _generation_with_usage({"input_tokens": 500, "output_tokens": 120})
        result = LLMResult(
            generations=[[gen]],
            llm_output={"token_usage": {"prompt_tokens": 500, "completion_tokens": 120}},
        )
        handler.on_llm_end(result)

        assert handler.tokens_in == 500  # not 1000
        assert handler.tokens_out == 120  # not 240

    def test_handles_missing_usage_metadata_gracefully(self):
        handler = TokenCaptureHandler()
        handler.on_llm_end(LLMResult(generations=[[_generation_with_usage(None)]]))
        assert handler.has_usage is False

    def test_handles_missing_message_gracefully(self):
        handler = TokenCaptureHandler()
        gen = MagicMock(spec=ChatGeneration)
        del gen.message
        handler.on_llm_end(LLMResult(generations=[[gen]]))
        assert handler.tokens_in == 0

    def test_handles_empty_generations(self):
        handler = TokenCaptureHandler()
        handler.on_llm_end(LLMResult(generations=[]))
        assert handler.tokens_in == 0
        assert handler.has_usage is False
