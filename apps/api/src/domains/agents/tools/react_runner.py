"""
ReAct Sub-Agent Runner — Generic runner for LangGraph ReAct agents.

Factorizes the common pattern used by browser_task_tool and mcp_server_task_tool:
LLM setup -> prompt loading -> create_agent -> invoke -> extract result.

Designed for composition: any tool needing an iterative agent loop can
instantiate ReactSubAgentRunner with its own LLM type, prompt, and tools.

Extensible via optional hooks:
- registry_collector: Collects registry items from tools after execution.
  Default: checks for ``_accumulated_registry`` PrivateAttr on tool wrappers.

A loop's budget end is a closing pass, never an answer of LangGraph's
(ADR-083 amendment 2026-10-13): the last call it can make gets no tool and
writes from what the loop gathered (``react_runner_closing``), and the result
says how the run ended (``outcome``, ``closed_on_budget``, ``truncated``).

Phase: ADR-062 — Agent Initiative Phase + MCP Iterative Support
Created: 2026-03-24
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog
from langchain.agents import create_agent
from langchain.tools import ToolRuntime
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    derive_sub_agent_context,
    runtime_context_if_running,
    runtime_user_id_str,
)
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.python_sandbox.egress.settlement import outside_settlement
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.react_runner_closing import (
    ClosingMiddleware,
    ClosingState,
    ClosingTrace,
)
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.llm.output_truncation import is_output_truncated
from src.infrastructure.observability.error_taxonomy import LLM_FAILURE_KINDS, classify_llm_error
from src.infrastructure.observability.metrics_subagent import (
    subagent_active_count,
    subagent_duration_seconds,
    subagent_errors_total,
    subagent_outcomes_total,
    subagent_spawned_total,
    subagent_tokens_in_total,
    subagent_tokens_out_total,
)

logger = structlog.get_logger(__name__)

# Type alias for the registry collector hook
RegistryCollector = Callable[[list[BaseTool]], dict[str, Any]]


class SubAgentOutcome(StrEnum):
    """How a sub-loop ended: only ANSWERED carries an answer.

    A closed or cut answer is still ANSWERED — what it lacks travels in the
    result's flags, never in the status (ADR-303's partial doctrine).
    """

    ANSWERED = "answered"
    EMPTY = "empty"
    ERROR = "error"


@dataclass(frozen=True)
class ReactSubAgentResult:
    """Immutable result from a ReAct sub-agent execution.

    Attributes:
        final_message: Text content of the last AI message.
        messages: Full message list from the ReAct loop.
        accumulated_registry: Registry items collected from all tool calls
            (e.g., MCP App HTML widgets via _MCPReActWrapper).
        iteration_count: Number of tool-calling iterations the agent performed.
        duration_ms: Wall-clock duration in milliseconds.
        outcome: How the loop ended (an answer, nothing, or an error).
        closed_on_budget: The answer was written by the closing pass: the budget
            ended the research, not the model.
        truncated: The provider cut the answer at its output budget — kept on an
            EMPTY run too, where a thinking model spent the cap before writing.
        failure_kind: On an error, its class in ``LLM_FAILURE_KINDS``.
    """

    final_message: str
    messages: list[BaseMessage]
    accumulated_registry: dict[str, Any] = field(default_factory=dict)
    iteration_count: int = 0
    duration_ms: int = 0
    outcome: SubAgentOutcome = SubAgentOutcome.ANSWERED
    closed_on_budget: bool = False
    truncated: bool = False
    failure_kind: str | None = None


#: The structured-data keys a reader adds when an answer is partial — present,
#: and true, only then: the partial travels in a field, never in the status.
BUDGET_EXHAUSTED_FIELD = "budget_exhausted"
OUTPUT_TRUNCATED_FIELD = "output_truncated"

#: How a sub-loop's model failure reads as a tool error code (ADR-303): one code
#: per ``LLM_FAILURE_KINDS`` member, so the honesty directive can tell « retry
#: later » (a limit, a timeout) from « the configuration is wrong ».
_FAILURE_KIND_CODES: dict[str, ToolErrorCode] = {
    "rate_limit": ToolErrorCode.RATE_LIMIT_EXCEEDED,
    "timeout": ToolErrorCode.TIMEOUT,
    "api_error": ToolErrorCode.EXTERNAL_API_ERROR,
    "context_length_exceeded": ToolErrorCode.CONSTRAINT_VIOLATION,
    "content_filter": ToolErrorCode.CONSTRAINT_VIOLATION,
    "authentication": ToolErrorCode.CONFIGURATION_ERROR,
    "model_not_found": ToolErrorCode.CONFIGURATION_ERROR,
    "invalid_request": ToolErrorCode.INTERNAL_ERROR,
    "unknown": ToolErrorCode.INTERNAL_ERROR,
}


def _assert_failure_codes_complete() -> None:
    """Refuse to import with a failure kind the code table does not cover.

    Raises:
        RuntimeError: When ``_FAILURE_KIND_CODES`` and ``LLM_FAILURE_KINDS`` disagree.
    """
    missing = LLM_FAILURE_KINDS - _FAILURE_KIND_CODES.keys()
    unknown = _FAILURE_KIND_CODES.keys() - LLM_FAILURE_KINDS
    if missing or unknown:
        raise RuntimeError(
            f"Sub-loop failure code table incomplete: missing={sorted(missing)}, "
            f"unknown={sorted(unknown)}"
        )


_assert_failure_codes_complete()


def failure_code_of(result: ReactSubAgentResult) -> ToolErrorCode:
    """The tool error code of a run that produced no answer.

    Args:
        result: A run whose outcome is EMPTY or ERROR.

    Returns:
        ``EMPTY_RESULT`` for an empty run; the code of its failure kind otherwise.
    """
    if result.outcome is SubAgentOutcome.EMPTY:
        return ToolErrorCode.EMPTY_RESULT
    return _FAILURE_KIND_CODES.get(result.failure_kind or "unknown", ToolErrorCode.INTERNAL_ERROR)


def failure_sentence(result: ReactSubAgentResult) -> str:
    """How a run without an answer ended, for the reader's failure message.

    Technical English, completing « <subject> … » (ADR-256): never the exception's
    text, which can quote the request (ADR-317).

    Args:
        result: A run whose outcome is EMPTY or ERROR.

    Returns:
        The predicate of the sentence.
    """
    if result.outcome is SubAgentOutcome.ERROR:
        return f"failed: its model call ended in error ({result.failure_kind or 'unknown'})"
    if result.truncated:
        return "ended without an answer: its output budget was spent before it wrote one"
    return "ended without an answer"


def partial_fields(result: ReactSubAgentResult) -> dict[str, bool]:
    """What an answered run lacks, as structured-data fields (empty when complete).

    Args:
        result: An answered run.

    Returns:
        ``{BUDGET_EXHAUSTED_FIELD: True}`` when the budget ended the research,
        ``{OUTPUT_TRUNCATED_FIELD: True}`` when the provider cut the answer.
    """
    fields: dict[str, bool] = {}
    if result.closed_on_budget:
        fields[BUDGET_EXHAUSTED_FIELD] = True
    if result.truncated:
        fields[OUTPUT_TRUNCATED_FIELD] = True
    return fields


def outcome_label(result: ReactSubAgentResult) -> str:
    """The run's outcome as one bounded metric label, the most telling first.

    Args:
        result: A finished run.

    Returns:
        ``error``, ``empty``, ``truncated``, ``closed_on_budget`` or ``answered``.
    """
    if result.outcome is not SubAgentOutcome.ANSWERED:
        return result.outcome.value
    if result.truncated:
        return "truncated"
    if result.closed_on_budget:
        return "closed_on_budget"
    return result.outcome.value


def _message_text(message: BaseMessage | None) -> str:
    """A message's text: str (most providers) and list[dict] blocks (Gemini 3.x) alike."""
    if message is None:
        return ""
    return coerce_content_to_text(message.content) if hasattr(message, "content") else str(message)


def _failed_result(
    exc: Exception, elapsed_ms: int, *, registry: dict[str, Any]
) -> ReactSubAgentResult:
    """The result of a loop the provider (or LangGraph) aborted.

    It carries no text: the outcome says the run failed, and an exception's text
    reaching a model is the leak CLAUDE.md forbids (it can quote the request). It
    keeps what the tools produced before the failure: a widget they created exists.

    Args:
        exc: What the loop raised.
        elapsed_ms: The run's wall-clock duration.
        registry: Registry items the tools accumulated before the failure.

    Returns:
        An ERROR result carrying the failure's class in ``LLM_FAILURE_KINDS``.
    """
    return ReactSubAgentResult(
        final_message="",
        messages=[],
        accumulated_registry=registry,
        duration_ms=elapsed_ms,
        outcome=SubAgentOutcome.ERROR,
        failure_kind=classify_llm_error(exc),
    )


def _finished_result(
    messages: list[BaseMessage],
    *,
    registry: dict[str, Any],
    closed: bool,
    elapsed_ms: int,
) -> ReactSubAgentResult:
    """The result of a loop that ran to its end.

    Args:
        messages: The loop's messages, its answer last.
        registry: Registry items the tools accumulated.
        closed: Whether the closing pass wrote the answer.
        elapsed_ms: The run's wall-clock duration.

    Returns:
        ANSWERED when the last message says something, EMPTY otherwise, with the
        provider's own verdict on a cut answer — an empty one included: a thinking
        model bills its reasoning inside the output budget (ADR-285).
    """
    last_msg = messages[-1] if messages else None
    final_message = _message_text(last_msg)
    answered = bool(final_message.strip())
    return ReactSubAgentResult(
        final_message=final_message,
        messages=messages,
        accumulated_registry=registry,
        iteration_count=sum(1 for m in messages if getattr(m, "tool_calls", None)),
        duration_ms=elapsed_ms,
        outcome=SubAgentOutcome.ANSWERED if answered else SubAgentOutcome.EMPTY,
        closed_on_budget=closed,
        truncated=last_msg is not None and is_output_truncated(last_msg),
    )


def _default_registry_collector(tools: list[BaseTool]) -> dict[str, Any]:
    """Collect registry items from tools that have _accumulated_registry.

    Works with any BaseTool subclass that stores registry items
    via a Pydantic PrivateAttr (e.g., _MCPReActWrapper).
    Tools without this attribute are silently skipped.

    Args:
        tools: List of BaseTool instances used by the ReAct agent.

    Returns:
        Merged dict of all accumulated registry items.
    """
    registry: dict[str, Any] = {}
    for tool in tools:
        accumulated = getattr(tool, "_accumulated_registry", None)
        if accumulated and isinstance(accumulated, dict):
            registry.update(accumulated)
    return registry


class ReactSubAgentRunner:
    """Generic ReAct sub-agent runner.

    Encapsulates the full lifecycle of a ReAct agent execution:
    1. Load LLM by type (admin-configurable via LLM Config panel)
    2. Load and format prompt from versioned prompt file
    3. Create ReAct agent with tools and parent store
    4. Execute with nested config (isolated thread, propagated callbacks)
    5. Extract result and collect registry items via extensible hook

    Usage::

        # Simple (browser-like, tools return strings):
        runner = ReactSubAgentRunner("browser_agent", "browser_agent_prompt")
        result = await runner.run(task="Search for ...", tools=[...], ...)

        # With registry capture (MCP-like, tools return UnifiedToolOutput):
        runner = ReactSubAgentRunner("mcp_react_agent", "mcp_react_agent_prompt")
        result = await runner.run(task="Create diagram", tools=wrapped_tools, ...)
        # result.accumulated_registry contains MCP App widgets

    Args:
        llm_type: LLM type key for get_llm() (e.g., "browser_agent", "mcp_react_agent").
        prompt_name: Prompt file name in prompts/v1/ (without .txt extension).
        prompt_version: Prompt version directory (default: "v1").
        registry_collector: Optional hook to collect registry items from tools.
            Default: _default_registry_collector (checks _accumulated_registry).
    """

    def __init__(
        self,
        llm_type: str,
        prompt_name: str,
        prompt_version: str = "v1",
        registry_collector: RegistryCollector | None = None,
    ) -> None:
        self.llm_type = llm_type
        self.prompt_name = prompt_name
        self.prompt_version = prompt_version
        self._registry_collector = registry_collector or _default_registry_collector

    @staticmethod
    def _sum_tokens(messages: list[BaseMessage]) -> tuple[int, int]:
        """Sum prompt/completion tokens from messages' ``usage_metadata``.

        Best-effort: providers that omit ``usage_metadata`` contribute 0.

        Args:
            messages: Messages returned by the ReAct loop.

        Returns:
            Tuple ``(input_tokens, output_tokens)`` summed across messages.
        """
        tokens_in = tokens_out = 0
        for msg in messages:
            usage = getattr(msg, "usage_metadata", None)
            if isinstance(usage, dict):
                tokens_in += int(usage.get("input_tokens") or 0)
                tokens_out += int(usage.get("output_tokens") or 0)
        return tokens_in, tokens_out

    def _emit_spawn(self, agent_name: str) -> None:
        """Emit spawn + active-count metrics. Never raises (hot-path safety).

        Args:
            agent_name: Sub-agent ``llm_type`` used as the metric label.
        """
        try:
            subagent_spawned_total.labels(agent_name=agent_name, mode="sync").inc()
            subagent_active_count.inc()
        except Exception:  # noqa: BLE001 - metrics must never break execution
            logger.debug("subagent_spawn_metric_failed", exc_info=True)

    def _emit_result(
        self,
        agent_name: str,
        elapsed_s: float,
        result: ReactSubAgentResult,
        error_type: str | None,
    ) -> None:
        """Emit duration, outcome, token and error metrics for a finished run.

        Does NOT touch ``subagent_active_count`` — that gauge is balanced in a
        ``finally`` (see :meth:`_emit_active_dec`) so it stays correct even when
        setup (``get_llm`` / ``load_prompt`` / ``create_agent``) raises.

        Args:
            agent_name: Sub-agent ``llm_type`` used as the metric label.
            elapsed_s: Wall-clock execution time in seconds.
            result: The run's result (its outcome; its messages for the tokens).
            error_type: Exception class name if the run failed, else ``None``.
        """
        messages = result.messages
        try:
            subagent_duration_seconds.labels(agent_name=agent_name).observe(elapsed_s)
            subagent_outcomes_total.labels(
                agent_name=agent_name, outcome=outcome_label(result)
            ).inc()
            if error_type is not None:
                subagent_errors_total.labels(agent_name=agent_name, error_type=error_type).inc()
                return
            tokens_in, tokens_out = self._sum_tokens(messages)
            if tokens_in:
                subagent_tokens_in_total.labels(agent_name=agent_name).inc(tokens_in)
            if tokens_out:
                subagent_tokens_out_total.labels(agent_name=agent_name).inc(tokens_out)
        except Exception:  # noqa: BLE001 - metrics must never break execution
            logger.debug("subagent_result_metric_failed", exc_info=True)

    def _emit_active_dec(self) -> None:
        """Decrement the active-sub-agents gauge. Never raises (hot-path safety)."""
        try:
            subagent_active_count.dec()
        except Exception:  # noqa: BLE001 - metrics must never break execution
            logger.debug("subagent_active_dec_metric_failed", exc_info=True)

    async def run(
        self,
        task: str,
        tools: list[BaseTool],
        prompt_vars: dict[str, str],
        parent_runtime: ToolRuntime[LiaRuntimeContext, Any] | None = None,
        thread_prefix: str = "react",
        recursion_limit: int = 15,
        display_name: str | None = None,
    ) -> ReactSubAgentResult:
        """Execute a task using a ReAct agent loop.

        Args:
            task: Natural language task for the agent.
            tools: BaseTool instances available to the agent.
            prompt_vars: Variables to format the prompt template.
                ``current_datetime`` is injected automatically.
            parent_runtime: ToolRuntime from parent graph (store/config propagation).
            thread_prefix: Prefix for the nested thread_id (isolation).
            recursion_limit: LangGraph recursion limit, in graph STEPS: the loop
                runs ``tool_rounds_for(limit)`` tool rounds, then a closing pass
                without tools (``react_runner_budget``).
            display_name: User-friendly name for the debug panel (e.g.,
                "MCP Iterative: excalidraw"). If None, defaults to llm_type.

        Returns:
            ReactSubAgentResult with final message, messages, accumulated
            registry items, iteration count, duration and how the run ended.
        """
        start = time.perf_counter()
        agent_name = self.llm_type
        self._emit_spawn(agent_name)

        # try/finally guarantees the active-count gauge is balanced even if the
        # setup below (get_llm / load_prompt / create_agent) raises and the
        # exception propagates to the caller.
        try:
            llm = get_llm(self.llm_type)
            prompt = load_prompt(self.prompt_name, version=self.prompt_version).format(
                current_datetime=get_prompt_datetime_formatted(),
                **prompt_vars,
            )

            parent_store = parent_runtime.store if parent_runtime else None
            parent_config = parent_runtime.config if parent_runtime else {}
            parent_configurable = parent_config.get("configurable", {})
            user_id = runtime_user_id_str("unknown")

            # One trace per run: the selector records that the budget ended the
            # research, so the result can say it.
            trace = ClosingTrace()
            react_agent = create_agent(
                llm,
                tools=tools,
                system_prompt=prompt,
                middleware=[ClosingMiddleware(trace)],
                state_schema=ClosingState,
                store=parent_store,
                # Declared so the sub-agent's own nodes and tools read the SAME
                # typed context as the parent run, rather than an untyped dict.
                context_schema=LiaRuntimeContext,
            )

            # Propagate parent metadata and inject node_name_override so
            # TokenTrackingCallback displays a user-friendly name in the
            # debug panel instead of the ReAct internal node name ("agent").
            parent_metadata = parent_config.get("metadata") or {}
            effective_display_name = display_name or self.llm_type
            nested_metadata = {
                **parent_metadata,
                "node_name_override": effective_display_name,
            }

            nested_thread_id = f"{thread_prefix}_{user_id}"

            # The sub-run inherits the parent's context WHOLE: deriving instead of
            # re-listing keys is what stops the next field added to the context
            # from being silently dropped here (ADR-231). ``__parent_thread_id``
            # stays in ``configurable`` — it is thread plumbing, not run context,
            # and ``browser_tools`` reads it deliberately.
            parent_context = runtime_context_if_running()
            nested_context = (
                derive_sub_agent_context(parent_context, thread_id=nested_thread_id)
                if parent_context is not None
                else None
            )

            # The bag now carries LangGraph plumbing ONLY. Everything run-scoped
            # (identity, preferences, dependencies, side channel) reaches the
            # sub-run through ``nested_context`` above — re-listing it here is
            # what used to lose 11 of the parent's 17 values in silence.
            nested_config = RunnableConfig(
                configurable={
                    "thread_id": nested_thread_id,
                    # Read deliberately by browser_tools to attribute a sub-run's
                    # artefacts to the conversation that spawned it.
                    "__parent_thread_id": parent_configurable.get("thread_id"),
                },
                callbacks=parent_config.get("callbacks"),
                metadata=nested_metadata,
                recursion_limit=recursion_limit,
            )

            logger.info(
                "react_sub_agent_start",
                llm_type=self.llm_type,
                tool_count=len(tools),
                tool_names=[t.name for t in tools],
                thread_prefix=thread_prefix,
                recursion_limit=recursion_limit,
            )

            try:
                # A nested loop settles no egress question: only the ReAct
                # loop's own call can resume on the answer (ADR-327 lot 3).
                with outside_settlement():
                    result = await react_agent.ainvoke(
                        {"messages": [HumanMessage(content=task)]},
                        config=nested_config,
                        context=nested_context,
                    )
            except Exception as exc:
                failed = _failed_result(
                    exc,
                    int((time.perf_counter() - start) * 1000),
                    registry=self._registry_collector(tools),
                )
                # The type and the kind, never the message: an error text can quote
                # the request (ADR-317).
                logger.warning(
                    "react_sub_agent_error",
                    llm_type=self.llm_type,
                    error_type=type(exc).__name__,
                    failure_kind=failed.failure_kind,
                    duration_ms=failed.duration_ms,
                )
                self._emit_result(
                    agent_name, failed.duration_ms / 1000.0, failed, type(exc).__name__
                )
                return failed

            finished = _finished_result(
                result.get("messages", []),
                # Collect registry items via extensible hook
                registry=self._registry_collector(tools),
                closed=trace.closed,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
            logger.info(
                "react_sub_agent_complete",
                llm_type=self.llm_type,
                iterations=finished.iteration_count,
                registry_items=len(finished.accumulated_registry),
                final_message_length=len(finished.final_message),
                outcome=finished.outcome.value,
                closed_on_budget=finished.closed_on_budget,
                truncated=finished.truncated,
                duration_ms=finished.duration_ms,
            )
            self._emit_result(agent_name, finished.duration_ms / 1000.0, finished, None)
            return finished
        finally:
            self._emit_active_dec()
