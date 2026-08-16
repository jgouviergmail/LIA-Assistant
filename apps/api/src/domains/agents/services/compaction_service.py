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

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config import settings
from src.core.constants import (
    COMPACTION_SUMMARY_MARKER,
    COMPACTION_TOOL_OUTPUT_TRUNCATE_CHARS_DEFAULT,
)
from src.core.llm_config_helper import get_effective_context_window, get_llm_config_for_agent
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.token_counter_service import (
    TokenCounterService,
    get_token_counter,
)
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_compaction import (
    compaction_chunk_timeouts_total,
    compaction_cost_tokens_total,
    compaction_duration_seconds,
    compaction_errors_total,
    compaction_executions_total,
    compaction_global_timeouts_total,
    compaction_skipped_total,
    compaction_tokens_saved,
    compaction_total_duration_seconds,
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


CompactionStrategy = Literal[
    "single_chunk",
    "multi_chunk",
    "single_chunk_with_merge",
    "truncation",
    "noop",
]


@dataclass
class CompactionResult:
    """Result of a compaction operation."""

    summary: str
    tokens_before: int
    tokens_after: int
    tokens_saved: int
    identifiers_preserved: list[str]
    strategy: CompactionStrategy
    cost_prompt_tokens: int = 0
    cost_completion_tokens: int = 0
    chunks_used: int = 1
    duration_seconds: float = 0.0
    # v2 (2026-05): True iff the LLM merge step actually consolidated previous
    # "compaction #N" SystemMessages into the new summary. The node uses this
    # to decide whether to remove the prior summaries from state. False on
    # truncation fallback so prior summaries are preserved (no regression vs v1).
    consolidated_previous_summaries: bool = False


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
        # DB-backed catalogue first, hand-maintained table as safety net —
        # keeps the trigger aligned with what the admin LLM catalogue declares.
        context_window = get_effective_context_window(response_config.model)
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

        Priority (2026-05 fix):
        1. Disabled → skip immediately.
        2. Count tokens. If above threshold → compact, regardless of how many
           messages there are. A conversation can have only 13–17 messages but
           one of them is a 6 K-token AIMessage with embedded data — the token
           count is the real signal.
        3. Otherwise, apply the `compaction_min_messages` fast-path: under the
           floor the cost-benefit ratio is bad (few short messages don't
           benefit from summarization).
        """
        if not settings.compaction_enabled:
            compaction_skipped_total.labels(reason="disabled").inc()
            return False

        # Count tokens up-front so a small-but-token-heavy conversation still
        # triggers compaction. Tiktoken is cheap relative to the LLM round-trip
        # we are deciding about.
        token_count = self._token_counter.count_messages_tokens(messages)
        threshold = self.compute_effective_threshold()

        if token_count >= threshold:
            logger.info(
                "compaction_threshold_exceeded",
                token_count=token_count,
                threshold=threshold,
                message_count=len(messages),
            )
            return True

        # Below threshold: apply the message-count fast-path.
        if len(messages) < settings.compaction_min_messages:
            compaction_skipped_total.labels(reason="too_few_messages").inc()
            return False

        compaction_skipped_total.labels(reason="below_threshold").inc()
        logger.debug(
            "compaction_below_threshold",
            token_count=token_count,
            threshold=threshold,
            message_count=len(messages),
        )
        return False

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
            content = msg.text
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
        """Format messages as text for the compaction LLM prompt.

        `msg.content` can be a plain string (the common case) or a list of
        content blocks (`[{"type": "text", "text": "..."}, ...]` for tools and
        multimodal AIMessages). Calling `msg.text` would stringify the block
        list with Python's `repr`, leaking JSON-like wrappers into the prompt
        and degrading the summary quality. We serialise non-string content via
        `json.dumps` instead so the LLM sees structured data verbatim.
        """
        lines: list[str] = []
        for msg in messages:
            role = msg.type  # human / ai / system / tool
            if isinstance(msg.content, str):
                content = msg.content
            else:
                content = json.dumps(msg.content, ensure_ascii=False)
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

        Wraps the LLM call with `asyncio.wait_for` (per-chunk timeout) and a
        `tenacity` retry loop with exponential backoff on transient errors
        (`ConnectionError`, `asyncio.TimeoutError`, `TimeoutError`). Settings
        `compaction_per_chunk_timeout_seconds`, `compaction_max_retries`, and
        `compaction_retry_backoff_base_seconds` control these.

        Returns:
            Tuple of (summary, prompt_tokens, completion_tokens)

        Raises:
            asyncio.TimeoutError: if a single attempt exceeds the per-chunk timeout
                and tenacity has exhausted its retries.
            ConnectionError: on persistent transient errors after retries.
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

        response = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(settings.compaction_max_retries),
            wait=wait_exponential(
                multiplier=settings.compaction_retry_backoff_base_seconds,
                # min must be aligned with the multiplier so the first retry
                # actually waits one base unit instead of clamping to 0
                # (tenacity issue #175). Without this, the three retries can
                # fire back-to-back and exhaust the global timeout faster than
                # the exponential backoff would otherwise allow.
                min=settings.compaction_retry_backoff_base_seconds,
                max=30,
            ),
            retry=retry_if_exception_type((ConnectionError, TimeoutError)),
            reraise=True,
        ):
            with attempt:
                attempt_number = attempt.retry_state.attempt_number
                if attempt_number > 1:
                    logger.info(
                        "compaction_chunk_retry",
                        attempt=attempt_number,
                        max_attempts=settings.compaction_max_retries,
                    )
                try:
                    response = await asyncio.wait_for(
                        llm.ainvoke(messages, config=enriched_config),
                        timeout=settings.compaction_per_chunk_timeout_seconds,
                    )
                except TimeoutError:
                    logger.warning(
                        "compaction_chunk_timeout",
                        timeout_seconds=settings.compaction_per_chunk_timeout_seconds,
                        attempt=attempt_number,
                    )
                    compaction_chunk_timeouts_total.inc()
                    raise

        # Defensive: if AsyncRetrying yielded zero attempts (impossible with
        # stop_after_attempt(>=1)), guard against an unset response.
        if response is None:  # pragma: no cover
            raise RuntimeError("compaction chunk retry loop produced no response")

        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "output_tokens", 0) if usage else 0

        summary = response.text
        return summary, prompt_tokens, completion_tokens

    async def compact(
        self,
        messages: list[BaseMessage],
        preserve_recent_n: int,
        language: str,
        config: RunnableConfig | None = None,
    ) -> CompactionResult:
        """
        Compact old messages into a summary, with v2 hardening.

        Wraps `_compact_impl_llm()` in `asyncio.wait_for(global_timeout)`. On
        timeout or any other failure, falls back to `_truncation_fallback()`
        which returns a deterministic, LLM-less result. The fallback notice
        is user-readable and explicit about the cause, replacing the silent
        `descriptive_fallback` of v1.

        Args:
            messages: Full message list from state.
            preserve_recent_n: Number of recent messages to keep intact.
            language: Language for the summary (from state.user_language).
            config: RunnableConfig for LLM invocation (token tracking propagation).

        Returns:
            CompactionResult with summary, strategy, and metrics. `strategy` is
            one of: `noop`, `single_chunk`, `multi_chunk`, `truncation`.
        """
        try:
            return await asyncio.wait_for(
                self._compact_impl_llm(messages, preserve_recent_n, language, config),
                timeout=settings.compaction_global_timeout_seconds,
            )
        except TimeoutError:
            logger.error(
                "compaction_global_timeout_fallback_to_truncation",
                global_timeout_seconds=settings.compaction_global_timeout_seconds,
                message_count=len(messages),
            )
            compaction_global_timeouts_total.inc()
            return self._truncation_fallback(messages, preserve_recent_n, reason="global_timeout")
        except Exception as e:
            logger.exception(
                "compaction_unexpected_failure_fallback_to_truncation",
                error_type=type(e).__name__,
            )
            compaction_errors_total.labels(error_type="unexpected").inc()
            return self._truncation_fallback(
                messages, preserve_recent_n, reason=f"unexpected:{type(e).__name__}"
            )

    async def _compact_impl_llm(
        self,
        messages: list[BaseMessage],
        preserve_recent_n: int,
        language: str,
        config: RunnableConfig | None = None,
    ) -> CompactionResult:
        """
        Inner LLM-based compaction. Wrapped by `compact()` with a global timeout.

        On any LLM failure inside the chunk/merge loop (`ConnectionError`,
        `TimeoutError`, or anything else), re-raises so the outer `compact()`
        can route through `_truncation_fallback`. The legacy `descriptive_fallback`
        branch is removed: v2 always either returns a real LLM summary or
        an explicit truncation notice.
        """
        start_time = time.monotonic()

        non_system = [m for m in messages if not isinstance(m, SystemMessage)]

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

        # v2 (Task 1.5): collect previous "compaction #N" SystemMessages so they
        # get folded into the merge step. This prevents the linear accumulation
        # of prior summaries observed in v1. They are NOT removed unless the
        # merge actually succeeds (see consolidated_previous_summaries flag).
        previous_summaries: list[str] = []
        if settings.compaction_include_previous_summaries:
            for m in messages:
                content = m.content if isinstance(m, SystemMessage) else None
                if isinstance(content, str) and content.startswith(COMPACTION_SUMMARY_MARKER):
                    previous_summaries.append(content)

        tokens_before = self._token_counter.count_messages_tokens(to_compact)
        identifiers = self._extract_identifiers(to_compact)

        llm = get_llm("compaction")

        chunks = self._split_into_chunks(to_compact, settings.compaction_chunk_max_tokens)
        strategy: CompactionStrategy = "single_chunk" if len(chunks) == 1 else "multi_chunk"

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

            # Prepend any previous compaction summaries so they participate in
            # the merge step (recursive consolidation). When there is no merge
            # to run (single chunk + no priors), the new summary stands alone
            # and the priors remain in state — no information is lost.
            #
            # The strategy label is tagged `single_chunk_with_merge` (not
            # `multi_chunk`) when the current run only produced one chunk but
            # we still merge with priors. Otherwise Grafana sees an artificial
            # multi_chunk inflation that does not reflect the LLM workload.
            if previous_summaries:
                summaries = previous_summaries + summaries
                if strategy == "single_chunk":
                    strategy = "single_chunk_with_merge"

            consolidated_previous = False
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
                consolidated_previous = bool(previous_summaries)
            else:
                final_summary = summaries[0] if summaries else ""

        except Exception as e:
            # v2: re-raise so the outer compact() applies _truncation_fallback.
            # The legacy descriptive_fallback branch is removed — explicit
            # truncation with a user-readable notice replaces the silent stub.
            logger.warning(
                "compaction_llm_failed",
                error=str(e),
                error_type=type(e).__name__,
                message_count=len(to_compact),
            )
            compaction_errors_total.labels(error_type="llm_failure").inc()
            raise

        duration = time.monotonic() - start_time
        tokens_after = self._token_counter.count_tokens(final_summary)
        tokens_saved = tokens_before - tokens_after

        compaction_executions_total.labels(strategy=strategy).inc()
        compaction_tokens_saved.observe(max(0, tokens_saved))
        compaction_duration_seconds.observe(duration)
        compaction_total_duration_seconds.observe(duration)
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
            consolidated_previous_summaries=consolidated_previous,
        )

    def _truncation_fallback(
        self,
        messages: list[BaseMessage],
        preserve_recent_n: int,
        reason: str,
    ) -> CompactionResult:
        """
        Deterministic LLM-less fallback used when `_compact_impl_llm` fails or
        exceeds the global budget. Produces a user-readable SystemMessage that
        explains the truncation, preserves key identifiers, and is safe to
        feed back into the conversation. Sets `consolidated_previous_summaries=False`
        so the node leaves any prior "compaction #N" summaries in place.
        """
        non_system = [m for m in messages if not isinstance(m, SystemMessage)]
        to_drop = non_system[:-preserve_recent_n] if preserve_recent_n > 0 else non_system
        identifiers = self._extract_identifiers(to_drop)
        tokens_before = self._token_counter.count_messages_tokens(to_drop)
        notice = (
            f"[Older conversation truncated — {len(to_drop)} messages removed "
            f"because the automatic summary could not complete ({reason}). "
            f"Key identifiers preserved: {', '.join(identifiers[:30])}]"
        )
        tokens_after = self._token_counter.count_tokens(notice)
        compaction_executions_total.labels(strategy="truncation").inc()
        compaction_total_duration_seconds.observe(0.0)
        return CompactionResult(
            summary=notice,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            tokens_saved=max(0, tokens_before - tokens_after),
            identifiers_preserved=identifiers,
            strategy="truncation",
            chunks_used=0,
            duration_seconds=0.0,
            consolidated_previous_summaries=False,
        )
