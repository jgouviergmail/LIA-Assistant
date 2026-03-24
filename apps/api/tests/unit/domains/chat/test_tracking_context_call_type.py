"""
Unit tests for TrackingContext call_type and sequence tracking (v3.3).

Tests the new call_type and sequence fields on TokenUsageRecord,
ensuring proper recording, chronological ordering, and breakdown output.
"""

from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.domains.chat.service import TokenUsageRecord, TrackingContext


class TestTokenUsageRecordCallType:
    """Tests for TokenUsageRecord call_type and sequence fields."""

    def test_default_call_type_is_chat(self) -> None:
        """call_type defaults to 'chat' when not specified."""
        record = TokenUsageRecord(
            node_name="router",
            model_name="gpt-4.1-mini",
            prompt_tokens=100,
            completion_tokens=50,
            cached_tokens=0,
            cost_usd=0.01,
            cost_eur=0.009,
            usd_to_eur_rate=Decimal("0.92"),
        )
        assert record.call_type == "chat"

    def test_default_sequence_is_zero(self) -> None:
        """sequence defaults to 0 when not specified."""
        record = TokenUsageRecord(
            node_name="router",
            model_name="gpt-4.1-mini",
            prompt_tokens=100,
            completion_tokens=50,
            cached_tokens=0,
            cost_usd=0.01,
            cost_eur=0.009,
            usd_to_eur_rate=Decimal("0.92"),
        )
        assert record.sequence == 0

    def test_embedding_call_type(self) -> None:
        """call_type can be set to 'embedding'."""
        record = TokenUsageRecord(
            node_name="embedding_embed_query",
            model_name="text-embedding-3-small",
            prompt_tokens=200,
            completion_tokens=0,
            cached_tokens=0,
            cost_usd=0.000004,
            cost_eur=0.0000037,
            usd_to_eur_rate=Decimal("0.92"),
            call_type="embedding",
            sequence=1,
        )
        assert record.call_type == "embedding"
        assert record.sequence == 1


@pytest.mark.asyncio
class TestTrackingContextCallType:
    """Tests for TrackingContext with call_type and sequence."""

    async def test_record_node_tokens_default_call_type(self) -> None:
        """record_node_tokens defaults call_type to 'chat'."""
        ctx = TrackingContext(
            run_id="test-run",
            user_id=uuid4(),
            session_id="test-session",
            conversation_id=uuid4(),
            auto_commit=False,
        )
        ctx._context_token = None  # Skip ContextVar setup

        with (
            patch(
                "src.infrastructure.cache.pricing_cache.get_cached_cost_usd_eur",
                return_value=(0.01, 0.009),
            ),
            patch(
                "src.infrastructure.cache.pricing_cache.get_cached_usd_eur_rate",
                return_value=0.92,
            ),
        ):
            await ctx.record_node_tokens(
                node_name="router",
                model_name="gpt-4.1-mini",
                prompt_tokens=100,
                completion_tokens=50,
                cached_tokens=0,
            )

        assert len(ctx._node_records) == 1
        assert ctx._node_records[0].call_type == "chat"

    async def test_record_node_tokens_embedding_call_type(self) -> None:
        """record_node_tokens stores call_type='embedding' when specified."""
        ctx = TrackingContext(
            run_id="test-run",
            user_id=uuid4(),
            session_id="test-session",
            conversation_id=uuid4(),
            auto_commit=False,
        )
        ctx._context_token = None

        with (
            patch(
                "src.infrastructure.cache.pricing_cache.get_cached_cost_usd_eur",
                return_value=(0.01, 0.009),
            ),
            patch(
                "src.infrastructure.cache.pricing_cache.get_cached_usd_eur_rate",
                return_value=0.92,
            ),
        ):
            await ctx.record_node_tokens(
                node_name="embedding_embed_query",
                model_name="text-embedding-3-small",
                prompt_tokens=200,
                completion_tokens=0,
                cached_tokens=0,
                call_type="embedding",
            )

        assert len(ctx._node_records) == 1
        assert ctx._node_records[0].call_type == "embedding"

    async def test_sequence_monotonic_increment(self) -> None:
        """sequence increments monotonically with each call."""
        ctx = TrackingContext(
            run_id="test-run",
            user_id=uuid4(),
            session_id="test-session",
            conversation_id=uuid4(),
            auto_commit=False,
        )
        ctx._context_token = None

        with (
            patch(
                "src.infrastructure.cache.pricing_cache.get_cached_cost_usd_eur",
                return_value=(0.01, 0.009),
            ),
            patch(
                "src.infrastructure.cache.pricing_cache.get_cached_usd_eur_rate",
                return_value=0.92,
            ),
        ):
            await ctx.record_node_tokens(
                node_name="router",
                model_name="m",
                prompt_tokens=10,
                completion_tokens=5,
                cached_tokens=0,
            )
            await ctx.record_node_tokens(
                node_name="embedding_embed_query",
                model_name="e",
                prompt_tokens=20,
                completion_tokens=0,
                cached_tokens=0,
                call_type="embedding",
            )
            await ctx.record_node_tokens(
                node_name="planner",
                model_name="m",
                prompt_tokens=30,
                completion_tokens=15,
                cached_tokens=0,
            )

        sequences = [r.sequence for r in ctx._node_records]
        assert sequences == [1, 2, 3]

    async def test_get_llm_calls_breakdown_includes_new_fields(self) -> None:
        """get_llm_calls_breakdown returns call_type and sequence."""
        ctx = TrackingContext(
            run_id="test-run",
            user_id=uuid4(),
            session_id="test-session",
            conversation_id=uuid4(),
            auto_commit=False,
        )
        ctx._context_token = None

        with (
            patch(
                "src.infrastructure.cache.pricing_cache.get_cached_cost_usd_eur",
                return_value=(0.01, 0.009),
            ),
            patch(
                "src.infrastructure.cache.pricing_cache.get_cached_usd_eur_rate",
                return_value=0.92,
            ),
        ):
            await ctx.record_node_tokens(
                node_name="router",
                model_name="m",
                prompt_tokens=10,
                completion_tokens=5,
                cached_tokens=0,
            )
            await ctx.record_node_tokens(
                node_name="embedding_embed_query",
                model_name="e",
                prompt_tokens=20,
                completion_tokens=0,
                cached_tokens=0,
                call_type="embedding",
            )

        breakdown = ctx.get_llm_calls_breakdown()
        assert len(breakdown) == 2

        assert breakdown[0]["call_type"] == "chat"
        assert breakdown[0]["sequence"] == 1
        assert breakdown[1]["call_type"] == "embedding"
        assert breakdown[1]["sequence"] == 2

    async def test_committed_records_preserve_call_type(self) -> None:
        """_committed_records_copy preserves call_type and sequence after commit."""
        ctx = TrackingContext(
            run_id="test-run",
            user_id=uuid4(),
            session_id="test-session",
            conversation_id=uuid4(),
            auto_commit=False,
        )
        ctx._context_token = None

        with (
            patch(
                "src.infrastructure.cache.pricing_cache.get_cached_cost_usd_eur",
                return_value=(0.01, 0.009),
            ),
            patch(
                "src.infrastructure.cache.pricing_cache.get_cached_usd_eur_rate",
                return_value=0.92,
            ),
        ):
            await ctx.record_node_tokens(
                node_name="embedding_embed_query",
                model_name="e",
                prompt_tokens=20,
                completion_tokens=0,
                cached_tokens=0,
                call_type="embedding",
            )

        # Simulate commit: publish to run-level collector + copy records then clear
        from src.domains.chat.service import _run_records

        _run_records.setdefault(ctx.run_id, []).extend(ctx._node_records)
        ctx._committed_records_copy.extend(ctx._node_records)
        ctx._node_records.clear()

        # get_llm_calls_breakdown should use run-level collector after commit
        try:
            breakdown = ctx.get_llm_calls_breakdown()
            assert len(breakdown) == 1
            assert breakdown[0]["call_type"] == "embedding"
            assert breakdown[0]["sequence"] == 1
        finally:
            # Cleanup run-level collector to avoid leaking into other tests
            _run_records.pop(ctx.run_id, None)
