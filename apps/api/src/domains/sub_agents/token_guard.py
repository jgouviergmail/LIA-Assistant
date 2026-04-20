"""
Sub-Agent token budget guard.

Monitors token consumption during sub-agent execution and triggers
abort if the per-execution budget is exceeded. Uses a LangChain
callback that checks cumulative tokens after each LLM call.

Phase: F6 — Persistent Specialized Sub-Agents
"""

import asyncio
from typing import Any

import structlog
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from src.domains.chat.service import TrackingContext

logger = structlog.get_logger(__name__)


class SubAgentTokenGuard:
    """Monitors token consumption and triggers abort if budget exceeded.

    Integrates with the executor's asyncio.wait() loop via an Event signal.
    After each LLM call, the callback checks cumulative tokens against the
    budget. If exceeded, sets the abort_event which the executor detects.

    Attributes:
        max_tokens: Maximum allowed tokens for this execution.
        tokens_consumed: Current cumulative token count.
        abort_event: Set when budget is exceeded.
    """

    def __init__(self, max_tokens: int, tracker: TrackingContext) -> None:
        """Initialize the token guard.

        Args:
            max_tokens: Maximum allowed tokens for this execution.
            tracker: TrackingContext to read cumulative tokens from.
        """
        self.max_tokens = max_tokens
        self.tracker = tracker
        self.abort_event = asyncio.Event()
        self.tokens_consumed = 0
        self._callback = _TokenGuardCallback(self)

    def get_callback(self) -> BaseCallbackHandler:
        """Return the LangChain callback to inject in sub-agent config."""
        return self._callback

    def check_and_abort_if_exceeded(self) -> None:
        """Check cumulative tokens and set abort event if over budget.

        Called by _TokenGuardCallback.on_llm_end() after each LLM call.
        Uses TrackingContext.get_cumulative_tokens() (public API) to avoid
        accessing internal _node_records directly.
        """
        self.tokens_consumed = self.tracker.get_cumulative_tokens()
        if self.tokens_consumed > self.max_tokens:
            # Dashboard 19 token budget exceeded metric
            try:
                from src.infrastructure.observability.metrics_subagent import (
                    subagent_token_budget_exceeded_total,
                )

                subagent_token_budget_exceeded_total.labels(
                    agent_name=getattr(self, "agent_name", "unknown")
                ).inc()
            except Exception:
                pass
            logger.warning(
                "subagent_token_budget_exceeded",
                tokens_consumed=self.tokens_consumed,
                max_tokens=self.max_tokens,
            )
            self.abort_event.set()


class _TokenGuardCallback(BaseCallbackHandler):
    """LangChain callback that checks token budget after each LLM call.

    Lightweight callback — only implements on_llm_end to minimize overhead.
    The guard's check is synchronous (reads in-memory counter), so the
    response time is < 1ms per check.
    """

    def __init__(self, guard: SubAgentTokenGuard) -> None:
        super().__init__()
        self.guard = guard

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Check token budget after each LLM call completes."""
        self.guard.check_and_abort_if_exceeded()
