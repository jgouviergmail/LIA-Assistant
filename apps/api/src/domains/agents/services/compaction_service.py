"""
CompactionService: Intelligent conversation history summarization.

Replaces old messages with a concise LLM-generated summary preserving
critical identifiers (UUIDs, URLs, IDs). Triggered when conversation
token count exceeds a dynamic threshold derived from the response model's
context window.

Architecture:
- should_compact(): Fast-path check (message count, then token count)
- is_safe_to_compact(): Verify no HITL state would be corrupted
- compute_effective_threshold(): Dynamic threshold from response model context window
- compact(): LLM summarization with chunking for large histories

Phase: F4 — Intelligent Context Compaction
Created: 2026-03-16
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.config.llm import get_model_context_window
from src.core.constants import COMPACTION_TOOL_OUTPUT_TRUNCATE_CHARS_DEFAULT
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.token_counter_service import (
    TokenCounterService,
    get_token_counter,
)
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_compaction import (
    compaction_cost_tokens_total,
    compaction_duration_seconds,
    compaction_errors_total,
    compaction_executions_total,
    compaction_skipped_total,
    compaction_tokens_saved,
)

if TYPE_CHECKING:
    from src.domains.agents.models import MessagesState

logger = get_logger(__name__)

# Regex pattern to extract identifiers worth preserving in summaries
_IDENTIFIER_PATTERN = re.compile(
    r"(?:"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # UUID
    r"|https?://\S+"  # URL
    r"|people/c\d+"  # Google People resource name
    r"|tool_call_\w+"  # Tool call ID
    r"|run-[\w-]+"  # Run ID
    r"|mem_\w+"  # Memory ID
    r"|msg-[\w-]+"  # Message ID
    r"|[\w.+-]+@[\w-]+\.[\w.]+"  # Email address
    r")",
    re.IGNORECASE,
)


@dataclass
class CompactionResult:
    """Result of a compaction operation."""

    summary: str
    tokens_before: int
    tokens_after: int
    tokens_saved: int
    identifiers_preserved: list[str]
    strategy: str  # single_chunk / multi_chunk / descriptive_fallback
    cost_prompt_tokens: int = 0
    cost_completion_tokens: int = 0
    chunks_used: int = 1
    duration_seconds: float = 0.0


@dataclass
class SafetyCheckResult:
    """Result of is_safe_to_compact() check."""

    safe: bool
    reason: str = ""


class CompactionService:
    """
    Service for intelligent conversation history compaction.

    Uses a cheap LLM (GPT-4.1-nano by default) to summarize old messages,
    preserving critical identifiers. The compaction threshold is dynamically
    derived from the response model's context window.
    """

    def __init__(
        self,
        token_counter: TokenCounterService | None = None,
    ) -> None:
        self._token_counter = token_counter or get_token_counter(settings)

    def compute_effective_threshold(self) -> int:
        """
        Compute the effective compaction threshold.

        Priority:
        1. Absolute override (compaction_token_threshold > 0) → use it directly
        2. Dynamic ratio: response model context_window * compaction_threshold_ratio
        """
        if settings.compaction_token_threshold > 0:
            return settings.compaction_token_threshold

        response_config = get_llm_config_for_agent(settings, "response")
        context_window = get_model_context_window(response_config.model)
        effective = int(context_window * settings.compaction_threshold_ratio)

        logger.debug(
            "compaction_threshold_computed",
            response_model=response_config.model,
            context_window=context_window,
            ratio=settings.compaction_threshold_ratio,
            effective_threshold=effective,
        )
        return effective

    def should_compact(self, messages: list[BaseMessage]) -> bool:
        """
        Check if compaction should be triggered.

        Fast-path: skip token counting if fewer messages than compaction_min_messages.
        """
        if not settings.compaction_enabled:
            compaction_skipped_total.labels(reason="disabled").inc()
            return False

        # Fast-path: not enough messages to warrant compaction
        if len(messages) < settings.compaction_min_messages:
            compaction_skipped_total.labels(reason="too_few_messages").inc()
            return False

        # Count tokens and compare with dynamic threshold
        token_count = self._token_counter.count_messages_tokens(messages)
        threshold = self.compute_effective_threshold()

        if token_count < threshold:
            compaction_skipped_total.labels(reason="below_threshold").inc()
            logger.debug(
                "compaction_below_threshold",
                token_count=token_count,
                threshold=threshold,
                message_count=len(messages),
            )
            return False

        logger.info(
            "compaction_threshold_exceeded",
            token_count=token_count,
            threshold=threshold,
            message_count=len(messages),
        )
        return True

    def is_safe_to_compact(self, state: MessagesState) -> SafetyCheckResult:
        """
        Verify no HITL state would be corrupted by compaction.

        Checks 4 safety conditions:
        1. pending_draft_critique → mid-draft review, compaction would lose draft context
        2. pending_entity_disambiguation → disambiguation in progress
        3. pending_disambiguations_queue → sequential disambiguations queued
        4. pending_tool_confirmation → tool approval pending, context needed
        """
        if state.get("pending_draft_critique"):
            compaction_skipped_total.labels(reason="hitl_pending_draft").inc()
            return SafetyCheckResult(safe=False, reason="hitl_pending_draft")

        if state.get("pending_entity_disambiguation"):
            compaction_skipped_total.labels(reason="hitl_pending_disambiguation").inc()
            return SafetyCheckResult(safe=False, reason="hitl_pending_disambiguation")

        queue = state.get("pending_disambiguations_queue", [])
        if queue:
            compaction_skipped_total.labels(reason="hitl_pending_queue").inc()
            return SafetyCheckResult(safe=False, reason="hitl_pending_queue")

        if state.get("pending_tool_confirmation"):
            compaction_skipped_total.labels(reason="hitl_pending_tool_confirmation").inc()
            return SafetyCheckResult(safe=False, reason="hitl_pending_tool_confirmation")

        return SafetyCheckResult(safe=True)

    def _extract_identifiers(self, messages: list[BaseMessage]) -> list[str]:
        """Extract unique identifiers from messages for preservation tracking."""
        identifiers: set[str] = set()
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            identifiers.update(_IDENTIFIER_PATTERN.findall(content))
        return sorted(identifiers)

    def _split_into_chunks(
        self,
        messages: list[BaseMessage],
        max_tokens_per_chunk: int,
    ) -> list[list[BaseMessage]]:
        """
        Split messages into chunks respecting max_tokens_per_chunk.

        Never splits a single message across chunks. If a single message
        exceeds the limit, it gets its own chunk.
        """
        chunks: list[list[BaseMessage]] = []
        current_chunk: list[BaseMessage] = []
        current_tokens = 0

        for msg in messages:
            msg_tokens = self._token_counter.count_message_tokens(msg)

            if current_chunk and (current_tokens + msg_tokens) > max_tokens_per_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 0

            current_chunk.append(msg)
            current_tokens += msg_tokens

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _format_messages_for_summary(self, messages: list[BaseMessage]) -> str:
        """Format messages as text for the compaction LLM prompt."""
        lines: list[str] = []
        for msg in messages:
            role = msg.type  # human / ai / system / tool
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            # Truncate very long tool results to avoid blowing the compaction budget
            if role == "tool" and len(content) > COMPACTION_TOOL_OUTPUT_TRUNCATE_CHARS_DEFAULT:
                content = (
                    content[:COMPACTION_TOOL_OUTPUT_TRUNCATE_CHARS_DEFAULT]
                    + "\n[... truncated tool output ...]"
                )
            lines.append(f"[{role}] {content}")
        return "\n\n".join(lines)

    async def _summarize_chunk(
        self,
        llm: BaseChatModel,
        chunk_text: str,
        language: str,
        config: RunnableConfig,
    ) -> tuple[str, int, int]:
        """
        Summarize a single chunk of messages.

        Returns:
            Tuple of (summary, prompt_tokens, completion_tokens)
        """
        system_prompt = load_prompt("compaction_prompt")

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=(
                    f"Summarize the following conversation excerpt. "
                    f"Write the summary in: {language}.\n\n"
                    f"---\n{chunk_text}\n---"
                )
            ),
        ]

        enriched_config = enrich_config_with_node_metadata(config, "compaction")
        response = await llm.ainvoke(messages, config=enriched_config)

        # Extract token usage from response metadata
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "output_tokens", 0) if usage else 0

        summary = response.content if isinstance(response.content, str) else str(response.content)
        return summary, prompt_tokens, completion_tokens

    async def compact(
        self,
        messages: list[BaseMessage],
        preserve_recent_n: int,
        language: str,
        config: RunnableConfig | None = None,
    ) -> CompactionResult:
        """
        Compact old messages into a summary.

        Strategy:
        1. Separate preserve_recent_n most recent messages (untouched)
        2. Extract identifiers from messages to compact
        3. Chunk if needed (> compaction_chunk_max_tokens)
        4. Summarize each chunk via LLM
        5. Merge multi-chunk summaries if needed
        6. Fallback to descriptive note on LLM failure

        Args:
            messages: Full message list from state.
            preserve_recent_n: Number of recent messages to keep intact.
            language: Language for the summary (from state.user_language).
            config: RunnableConfig for LLM invocation (token tracking propagation).

        Returns:
            CompactionResult with summary and metrics.
        """
        start_time = time.monotonic()

        # Separate compactable messages and recent messages (system messages excluded)
        non_system = [m for m in messages if not isinstance(m, SystemMessage)]

        # Guard: need at least preserve_recent_n + 1 non-system messages to have something to compact
        if preserve_recent_n < 1 or len(non_system) <= preserve_recent_n:
            return CompactionResult(
                summary="",
                tokens_before=0,
                tokens_after=0,
                tokens_saved=0,
                identifiers_preserved=[],
                strategy="noop",
            )

        to_compact = non_system[:-preserve_recent_n]

        tokens_before = self._token_counter.count_messages_tokens(to_compact)
        identifiers = self._extract_identifiers(to_compact)

        # Get compaction LLM
        llm = get_llm("compaction")

        # Split into chunks
        chunks = self._split_into_chunks(to_compact, settings.compaction_chunk_max_tokens)
        strategy = "single_chunk" if len(chunks) == 1 else "multi_chunk"

        total_prompt_tokens = 0
        total_completion_tokens = 0
        summaries: list[str] = []

        try:
            for chunk in chunks:
                chunk_text = self._format_messages_for_summary(chunk)
                summary, pt, ct = await self._summarize_chunk(
                    llm, chunk_text, language, config or {}
                )
                summaries.append(summary)
                total_prompt_tokens += pt
                total_completion_tokens += ct

            # Merge multi-chunk summaries
            if len(summaries) > 1:
                merge_text = "\n\n---\n\n".join(
                    f"[Part {i + 1}]\n{s}" for i, s in enumerate(summaries)
                )
                final_summary, pt, ct = await self._summarize_chunk(
                    llm,
                    f"Merge the following partial summaries into a single coherent summary:\n\n"
                    f"{merge_text}",
                    language,
                    config or {},
                )
                total_prompt_tokens += pt
                total_completion_tokens += ct
            else:
                final_summary = summaries[0] if summaries else ""

        except Exception as e:
            # Fallback: descriptive note (no LLM needed)
            logger.warning(
                "compaction_llm_failed_fallback",
                error=str(e),
                message_count=len(to_compact),
            )
            compaction_errors_total.labels(error_type="llm_failure").inc()
            strategy = "descriptive_fallback"

            # Build a simple descriptive summary
            msg_types: dict[str, int] = {}
            for m in to_compact:
                msg_types[m.type] = msg_types.get(m.type, 0) + 1

            type_summary = ", ".join(f"{count} {t}" for t, count in sorted(msg_types.items()))
            final_summary = (
                f"[Previous conversation compacted — {len(to_compact)} messages "
                f"({type_summary}). Key identifiers: {', '.join(identifiers[:20])}]"
            )

        duration = time.monotonic() - start_time
        tokens_after = self._token_counter.count_tokens(final_summary)
        tokens_saved = tokens_before - tokens_after

        # Track metrics
        compaction_executions_total.labels(strategy=strategy).inc()
        compaction_tokens_saved.observe(max(0, tokens_saved))
        compaction_duration_seconds.observe(duration)
        compaction_cost_tokens_total.labels(token_type="prompt").inc(total_prompt_tokens)
        compaction_cost_tokens_total.labels(token_type="completion").inc(total_completion_tokens)

        logger.info(
            "compaction_completed",
            strategy=strategy,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            tokens_saved=tokens_saved,
            identifiers_count=len(identifiers),
            chunks_used=len(chunks),
            cost_prompt=total_prompt_tokens,
            cost_completion=total_completion_tokens,
            duration_seconds=round(duration, 2),
        )

        return CompactionResult(
            summary=final_summary,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            tokens_saved=tokens_saved,
            identifiers_preserved=identifiers,
            strategy=strategy,
            cost_prompt_tokens=total_prompt_tokens,
            cost_completion_tokens=total_completion_tokens,
            chunks_used=len(chunks),
            duration_seconds=duration,
        )
