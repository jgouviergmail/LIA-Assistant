"""Every spend site reads a provider's usage through the ONE reader (prompt audit 2026-09-12, lot F).

``tokens_from_usage_metadata`` was written once and copied five times; the copies read
only Anthropic's top-level ``cache_read_input_tokens`` (so an OpenAI-family slot billed
cached prompts at full price) and handed the RAW input total to a pricer that adds the
cached bucket on top — double billing wherever the cache was read. These tests feed an
OpenAI-shaped payload to each site and read what it bills.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

OPENAI_SHAPED = {
    "input_tokens": 1500,
    "output_tokens": 40,
    "total_tokens": 1540,
    "input_token_details": {"cache_read": 1024},
}


def _ai_message() -> AIMessage:
    return AIMessage(content="Bonjour !", usage_metadata=OPENAI_SHAPED)  # type: ignore[arg-type]


class TestHeartbeatMessage:
    async def test_bills_prompt_and_cache_separately(self) -> None:
        from src.domains.heartbeat import prompts as heartbeat_prompts

        context = MagicMock()
        context.to_prompt_context.return_value = "ctx"
        with (
            patch("src.infrastructure.llm.get_llm", return_value=MagicMock()),
            patch(
                "src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation",
                AsyncMock(return_value=_ai_message()),
            ),
            patch.object(
                heartbeat_prompts,
                "load_prompt",
                return_value="{personality_instruction}{language}{current_datetime}{message_draft}{psyche_context}",
            ),
        ):
            _text, tokens_in, tokens_out, tokens_cache = (
                await heartbeat_prompts.generate_heartbeat_message("draft", context, "fr")
            )
        assert (tokens_in, tokens_out, tokens_cache) == (476, 40, 1024)


class TestPeerDelivery:
    async def test_bills_prompt_and_cache_separately(self) -> None:
        from src.infrastructure.scheduler import peer_message_delivery as delivery

        message = MagicMock(id="m1", sender_id="s1", content="hello", relay_count_today=0)
        sender = MagicMock(full_name="Alice", email="a@b.c")
        recipient = MagicMock(
            language="fr",
            personality_id=None,
            id="00000000-0000-4000-8000-000000000002",
            timezone="Europe/Paris",
        )
        with (
            patch("src.infrastructure.llm.get_llm", return_value=MagicMock()),
            patch(
                "src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation",
                AsyncMock(return_value=_ai_message()),
            ),
        ):
            # The real versioned prompt: the test must never skip on its shape (ADR-155).
            _text, tokens_in, tokens_out, tokens_cache = await delivery._generate_delivery_text(
                message, sender, recipient, 0
            )
        assert (tokens_in, tokens_out, tokens_cache) == (476, 40, 1024)


class TestJournalExtractionCost:
    async def test_prices_the_cached_bucket(self) -> None:
        from src.domains.journals import extraction_service

        pricer = MagicMock(return_value=(0.0, 0.0))
        db = MagicMock()
        db.__aenter__ = AsyncMock(return_value=db)
        db.__aexit__ = AsyncMock(return_value=False)
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        with (
            patch("src.infrastructure.cache.pricing_cache.get_cached_cost_usd_eur", pricer),
            patch("src.infrastructure.database.get_db_context", return_value=db),
        ):
            await extraction_service._update_user_last_cost(
                "00000000-0000-4000-8000-000000000001", _ai_message(), "some-model"
            )
        assert pricer.call_args.kwargs["prompt_tokens"] == 476
        assert pricer.call_args.kwargs["completion_tokens"] == 40
        assert pricer.call_args.kwargs["cached_tokens"] == 1024


class TestTokenEfficiency:
    def test_ratio_is_over_the_whole_input_cached_included(self) -> None:
        from src.infrastructure.observability import token_efficiency

        callback = MagicMock()
        callback._last_usage_metadata = OPENAI_SHAPED
        observed: list[float] = []
        gauge = MagicMock()
        gauge.labels.return_value.observe.side_effect = observed.append
        with patch.object(token_efficiency, "token_efficiency_ratio", gauge):
            token_efficiency.track_token_efficiency(
                config={"callbacks": [callback]}, node_name="response", agent_type="conversational"
            )
        assert observed == [pytest.approx(40 / 1500)]

    def test_a_fully_cached_prompt_is_not_a_zero_input(self) -> None:
        """prompt = input − cached may be 0; the ratio must still be recorded."""
        from src.infrastructure.observability import token_efficiency

        callback = MagicMock()
        callback._last_usage_metadata = {
            "input_tokens": 1024,
            "output_tokens": 8,
            "input_token_details": {"cache_read": 1024},
        }
        observed: list[float] = []
        gauge = MagicMock()
        gauge.labels.return_value.observe.side_effect = observed.append
        with patch.object(token_efficiency, "token_efficiency_ratio", gauge):
            token_efficiency.track_token_efficiency(
                config={"callbacks": [callback]}, node_name="response", agent_type="conversational"
            )
        assert observed == [pytest.approx(8 / 1024)]


class TestTokenExtractor:
    def test_anthropic_top_level_spelling_is_read(self) -> None:
        from src.infrastructure.observability.token_extractor import TokenExtractor

        message = AIMessage(
            content="x",
            usage_metadata={"input_tokens": 1500, "output_tokens": 40, "total_tokens": 1540, "cache_read_input_tokens": 1024},  # type: ignore[typeddict-item]
        )
        generation = MagicMock(message=message)
        response = MagicMock(generations=[[generation]], llm_output={})
        usage: Any = TokenExtractor().extract(response, llm=None)
        assert (usage.input_tokens, usage.output_tokens, usage.cached_tokens) == (476, 40, 1024)
