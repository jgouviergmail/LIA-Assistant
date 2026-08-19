"""
ReAct Sub-Agent Runner — Generic runner for LangGraph ReAct agents.

Factorizes the common pattern used by browser_task_tool and mcp_server_task_tool:
LLM setup -> prompt loading -> create_react_agent -> invoke -> extract result.

Designed for composition: any tool needing an iterative agent loop can
instantiate ReactSubAgentRunner with its own LLM type, prompt, and tools.

Extensible via optional hooks:
- registry_collector: Collects registry items from tools after execution.
  Default: checks for ``_accumulated_registry`` PrivateAttr on tool wrappers.

Phase: ADR-062 — Agent Initiative Phase + MCP Iterative Support
Created: 2026-03-24
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog
from langchain.tools import ToolRuntime
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from src.core.config import settings
from src.core.constants import DEFAULT_TIMEZONE
from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    derive_sub_agent_context,
    runtime_context_if_running,
)
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.metrics_subagent import (
    subagent_active_count,
    subagent_duration_seconds,
    subagent_errors_total,
    subagent_spawned_total,
    subagent_tokens_in_total,
    subagent_tokens_out_total,
)

logger = structlog.get_logger(__name__)

# Type alias for the registry collector hook
RegistryCollector = Callable[[list[BaseTool]], dict[str, Any]]


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
    """

    final_message: str
    messages: list[BaseMessage]
    accumulated_registry: dict[str, Any] = field(default_factory=dict)
    iteration_count: int = 0
    duration_ms: int = 0


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
        messages: list[BaseMessage],
        error_type: str | None,
    ) -> None:
        """Emit duration, token and error metrics for a finished run.

        Does NOT touch ``subagent_active_count`` — that gauge is balanced in a
        ``finally`` (see :meth:`_emit_active_dec`) so it stays correct even when
        setup (``get_llm`` / ``load_prompt`` / ``create_react_agent``) raises.

        Args:
            agent_name: Sub-agent ``llm_type`` used as the metric label.
            elapsed_s: Wall-clock execution time in seconds.
            messages: ReAct messages (for token extraction on success).
            error_type: Exception class name if the run failed, else ``None``.
        """
        try:
            subagent_duration_seconds.labels(agent_name=agent_name).observe(elapsed_s)
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
            recursion_limit: Max ReAct iterations (safety limit).
            display_name: User-friendly name for the debug panel (e.g.,
                "MCP Iterative: excalidraw"). If None, defaults to llm_type.

        Returns:
            ReactSubAgentResult with final message, messages, accumulated
            registry items, iteration count, and duration.
        """
        start = time.perf_counter()
        agent_name = self.llm_type
        self._emit_spawn(agent_name)

        # try/finally guarantees the active-count gauge is balanced even if the
        # setup below (get_llm / load_prompt / create_react_agent) raises and the
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
            user_id = parent_configurable.get("user_id", "unknown")

            react_agent = create_react_agent(
                llm,
                tools=tools,
                prompt=prompt,
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

            nested_config = RunnableConfig(
                configurable={
                    "user_id": user_id,
                    "thread_id": nested_thread_id,
                    "__deps": parent_configurable.get("__deps"),
                    "__side_channel_queue": parent_configurable.get("__side_channel_queue"),
                    "__parent_thread_id": parent_configurable.get("thread_id"),
                    # Canonical defaults, same sources as the chokepoint that
                    # builds the parent configurable — an inline literal here
                    # answered in French to a German user whenever the parent
                    # lacked the key (ADR-231).
                    "user_timezone": parent_configurable.get("user_timezone", DEFAULT_TIMEZONE),
                    "user_language": parent_configurable.get(
                        "user_language", settings.default_language
                    ),
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
                result = await react_agent.ainvoke(
                    {"messages": [HumanMessage(content=task)]},
                    config=nested_config,
                    context=nested_context,
                )
            except Exception as exc:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                logger.warning(
                    "react_sub_agent_error",
                    llm_type=self.llm_type,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    duration_ms=elapsed_ms,
                )
                self._emit_result(agent_name, elapsed_ms / 1000.0, [], type(exc).__name__)
                return ReactSubAgentResult(
                    final_message=f"Error: {exc}",
                    messages=[],
                    duration_ms=elapsed_ms,
                )

            messages = result.get("messages", [])
            final_message = ""
            if messages:
                last_msg = messages[-1]
                # Normalize str (most providers) and list[dict] blocks (Gemini 3.x) to text.
                final_message = (
                    coerce_content_to_text(last_msg.content)
                    if hasattr(last_msg, "content")
                    else str(last_msg)
                )

            # Collect registry items via extensible hook
            accumulated_registry = self._registry_collector(tools)

            iteration_count = sum(1 for m in messages if hasattr(m, "tool_calls") and m.tool_calls)
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            logger.info(
                "react_sub_agent_complete",
                llm_type=self.llm_type,
                iterations=iteration_count,
                registry_items=len(accumulated_registry),
                final_message_length=len(final_message),
                duration_ms=elapsed_ms,
            )

            self._emit_result(agent_name, elapsed_ms / 1000.0, messages, None)

            return ReactSubAgentResult(
                final_message=final_message,
                messages=messages,
                accumulated_registry=accumulated_registry,
                iteration_count=iteration_count,
                duration_ms=elapsed_ms,
            )
        finally:
            self._emit_active_dec()
