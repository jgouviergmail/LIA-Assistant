"""Unit tests for CompactionService v2 hardening.

Covers behaviour introduced after the 2026-05-16 production incident:
- Per-chunk timeout via `asyncio.wait_for`.
- Exponential retry via `tenacity` on transient errors (ConnectionError, TimeoutError).
- Global timeout around `compact()` with fallback to truncation.
- Consolidation of previous "compaction #N" SystemMessages without losing them
  when the merge falls back to truncation.

Phase: F4.5 — Compaction v2
Created: 2026-05-18
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from src.domains.agents.services.compaction_service import CompactionService


@pytest.fixture
def service() -> CompactionService:
    """CompactionService with a deterministic token counter for v2 tests."""
    svc = CompactionService()
    svc._token_counter = MagicMock()
    svc._token_counter.count_messages_tokens.return_value = 50_000
    svc._token_counter.count_message_tokens.side_effect = lambda m: 1_000
    svc._token_counter.count_tokens.side_effect = lambda t: max(1, len(t) // 4)
    return svc


# ============================================================================
# Per-chunk timeout
# ============================================================================


async def test_summarize_chunk_times_out(
    monkeypatch: pytest.MonkeyPatch, service: CompactionService
) -> None:
    """When llm.ainvoke hangs longer than per-chunk timeout, raise TimeoutError."""
    monkeypatch.setattr("src.core.config.settings.compaction_per_chunk_timeout_seconds", 0.05)
    monkeypatch.setattr("src.core.config.settings.compaction_max_retries", 1)

    async def hang(*_a: object, **_kw: object) -> None:
        await asyncio.sleep(2)
        raise AssertionError("should have timed out")

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=hang)

    with pytest.raises(TimeoutError):
        await service._summarize_chunk(fake_llm, "x", "en", config={})


# ============================================================================
# Retry on transient errors
# ============================================================================


async def test_summarize_chunk_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, service: CompactionService
) -> None:
    """Tenacity retries on ConnectionError up to max_retries and then succeeds."""
    monkeypatch.setattr("src.core.config.settings.compaction_per_chunk_timeout_seconds", 5.0)
    monkeypatch.setattr("src.core.config.settings.compaction_max_retries", 3)
    monkeypatch.setattr("src.core.config.settings.compaction_retry_backoff_base_seconds", 0.01)

    fake_response = MagicMock(
        text="summary text",
        usage_metadata=MagicMock(input_tokens=10, output_tokens=5),
    )
    calls = {"n": 0}

    async def flaky(*_a: object, **_kw: object):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return fake_response

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=flaky)

    summary, pt, ct = await service._summarize_chunk(fake_llm, "x", "en", config={})
    assert summary == "summary text"
    assert pt == 10
    assert ct == 5
    assert calls["n"] == 3


async def test_summarize_chunk_exhausts_retries(
    monkeypatch: pytest.MonkeyPatch, service: CompactionService
) -> None:
    """When all retries fail with ConnectionError, the last exception is re-raised."""
    monkeypatch.setattr("src.core.config.settings.compaction_per_chunk_timeout_seconds", 5.0)
    monkeypatch.setattr("src.core.config.settings.compaction_max_retries", 2)
    monkeypatch.setattr("src.core.config.settings.compaction_retry_backoff_base_seconds", 0.01)

    async def always_fail(*_a: object, **_kw: object) -> None:
        raise ConnectionError("permanent")

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=always_fail)

    with pytest.raises(ConnectionError):
        await service._summarize_chunk(fake_llm, "x", "en", config={})


# ============================================================================
# Global timeout + truncation fallback (Task 1.3)
# ============================================================================


async def test_compact_global_timeout_falls_back_to_truncation(
    monkeypatch: pytest.MonkeyPatch, service: CompactionService
) -> None:
    """When _compact_impl_llm exceeds the global budget, compact() returns strategy='truncation'."""
    monkeypatch.setattr("src.core.config.settings.compaction_global_timeout_seconds", 0.1)
    monkeypatch.setattr("src.core.config.settings.compaction_per_chunk_timeout_seconds", 5.0)
    monkeypatch.setattr("src.core.config.settings.compaction_max_retries", 1)
    monkeypatch.setattr("src.core.config.settings.compaction_chunk_max_tokens", 100_000)

    async def slow(*_a: object, **_kw: object):
        await asyncio.sleep(1)
        return MagicMock(
            text="should never arrive",
            usage_metadata=MagicMock(input_tokens=1, output_tokens=1),
        )

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=slow)
    monkeypatch.setattr(
        "src.domains.agents.services.compaction_service.get_llm",
        lambda _t: fake_llm,
    )
    monkeypatch.setattr(
        "src.domains.agents.services.compaction_service.load_prompt",
        lambda _name: "Summarize.",
    )

    msgs = [HumanMessage(content=f"msg {i}: " + "x " * 200, id=f"h{i}") for i in range(30)]
    result = await service.compact(messages=msgs, preserve_recent_n=5, language="en", config={})
    assert result.strategy == "truncation"
    assert "truncated" in result.summary.lower()
    assert result.consolidated_previous_summaries is False


async def test_compact_llm_unexpected_failure_falls_back_to_truncation(
    monkeypatch: pytest.MonkeyPatch, service: CompactionService
) -> None:
    """A non-retryable exception inside _compact_impl_llm routes through the truncation fallback."""
    monkeypatch.setattr("src.core.config.settings.compaction_global_timeout_seconds", 10.0)
    monkeypatch.setattr("src.core.config.settings.compaction_per_chunk_timeout_seconds", 5.0)
    monkeypatch.setattr("src.core.config.settings.compaction_max_retries", 1)
    monkeypatch.setattr("src.core.config.settings.compaction_chunk_max_tokens", 100_000)

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("provider misconfigured"))
    monkeypatch.setattr(
        "src.domains.agents.services.compaction_service.get_llm",
        lambda _t: fake_llm,
    )
    monkeypatch.setattr(
        "src.domains.agents.services.compaction_service.load_prompt",
        lambda _name: "Summarize.",
    )

    msgs = [HumanMessage(content=f"msg {i}", id=f"h{i}") for i in range(20)]
    result = await service.compact(messages=msgs, preserve_recent_n=5, language="en", config={})
    assert result.strategy == "truncation"
    assert "RuntimeError" in result.summary or "truncated" in result.summary.lower()


async def test_truncation_fallback_preserves_previous_summaries_flag(
    monkeypatch: pytest.MonkeyPatch, service: CompactionService
) -> None:
    """The truncation fallback always sets consolidated_previous_summaries=False, even with prior summaries present."""
    monkeypatch.setattr("src.core.config.settings.compaction_global_timeout_seconds", 0.05)
    monkeypatch.setattr("src.core.config.settings.compaction_max_retries", 1)
    monkeypatch.setattr("src.core.config.settings.compaction_per_chunk_timeout_seconds", 5.0)
    monkeypatch.setattr("src.core.config.settings.compaction_chunk_max_tokens", 100_000)

    async def slow(*_a: object, **_kw: object):
        await asyncio.sleep(1)
        return MagicMock(text="x", usage_metadata=MagicMock(input_tokens=1, output_tokens=1))

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=slow)
    monkeypatch.setattr(
        "src.domains.agents.services.compaction_service.get_llm",
        lambda _t: fake_llm,
    )
    monkeypatch.setattr(
        "src.domains.agents.services.compaction_service.load_prompt",
        lambda _name: "Summarize.",
    )

    prior = SystemMessage(
        content="[Conversation history compacted — compaction #1.] PRIOR_KEY_42",
        id="prior-1",
    )
    msgs = [prior] + [HumanMessage(content=f"msg {i}", id=f"h{i}") for i in range(30)]
    result = await service.compact(messages=msgs, preserve_recent_n=5, language="en", config={})
    assert result.strategy == "truncation"
    assert result.consolidated_previous_summaries is False


# ============================================================================
# Consolidation of previous summaries (Task 1.5)
# ============================================================================


async def test_previous_compaction_summaries_are_consolidated(
    monkeypatch: pytest.MonkeyPatch, service: CompactionService
) -> None:
    """Prior 'compaction #N' SystemMessages get folded into the merge prompt.

    On success, `consolidated_previous_summaries=True` so the node will know it
    can remove the prior summaries from state without losing context.
    """
    monkeypatch.setattr("src.core.config.settings.compaction_include_previous_summaries", True)
    monkeypatch.setattr("src.core.config.settings.compaction_global_timeout_seconds", 10.0)
    monkeypatch.setattr("src.core.config.settings.compaction_per_chunk_timeout_seconds", 5.0)
    monkeypatch.setattr("src.core.config.settings.compaction_max_retries", 1)
    monkeypatch.setattr("src.core.config.settings.compaction_chunk_max_tokens", 100_000)

    captured_prompts: list[str] = []

    async def echo(messages_arg, config=None):
        text = " | ".join(getattr(m, "content", "") for m in messages_arg)
        captured_prompts.append(text)
        return MagicMock(
            text=f"MERGED[{text[:300]}]",
            usage_metadata=MagicMock(input_tokens=10, output_tokens=5),
        )

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=echo)
    monkeypatch.setattr(
        "src.domains.agents.services.compaction_service.get_llm",
        lambda _t: fake_llm,
    )
    monkeypatch.setattr(
        "src.domains.agents.services.compaction_service.load_prompt",
        lambda _name: "Summarize.",
    )

    prior = SystemMessage(
        content="[Conversation history compacted — compaction #1.] PRIOR_MARKER_77",
        id="prior-1",
    )
    msgs = [prior] + [HumanMessage(content=f"msg {i}", id=f"h{i}") for i in range(30)]
    result = await service.compact(messages=msgs, preserve_recent_n=5, language="en", config={})
    # `single_chunk_with_merge` is emitted when a single chunk was produced
    # but a merge step still ran to consolidate prior summaries — it tags the
    # difference from a true multi-chunk LLM workload for Grafana.
    assert result.strategy in {"single_chunk", "multi_chunk", "single_chunk_with_merge"}
    assert result.consolidated_previous_summaries is True
    # The merge step (the second LLM call) included the prior summary text.
    assert any("PRIOR_MARKER_77" in prompt for prompt in captured_prompts)


async def test_no_previous_summaries_keeps_consolidated_flag_false(
    monkeypatch: pytest.MonkeyPatch, service: CompactionService
) -> None:
    """When no prior compaction summary exists, consolidated_previous_summaries=False."""
    monkeypatch.setattr("src.core.config.settings.compaction_include_previous_summaries", True)
    monkeypatch.setattr("src.core.config.settings.compaction_global_timeout_seconds", 10.0)
    monkeypatch.setattr("src.core.config.settings.compaction_per_chunk_timeout_seconds", 5.0)
    monkeypatch.setattr("src.core.config.settings.compaction_max_retries", 1)
    monkeypatch.setattr("src.core.config.settings.compaction_chunk_max_tokens", 100_000)

    async def ok(*_a, **_kw):
        return MagicMock(
            text="summary",
            usage_metadata=MagicMock(input_tokens=10, output_tokens=5),
        )

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=ok)
    monkeypatch.setattr(
        "src.domains.agents.services.compaction_service.get_llm",
        lambda _t: fake_llm,
    )
    monkeypatch.setattr(
        "src.domains.agents.services.compaction_service.load_prompt",
        lambda _name: "Summarize.",
    )

    msgs = [HumanMessage(content=f"msg {i}", id=f"h{i}") for i in range(20)]
    result = await service.compact(messages=msgs, preserve_recent_n=5, language="en", config={})
    assert result.strategy in {"single_chunk", "multi_chunk"}
    assert result.consolidated_previous_summaries is False
