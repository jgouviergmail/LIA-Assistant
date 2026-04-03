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

from src.core.time_utils import get_prompt_datetime_formatted
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.infrastructure.llm.factory import get_llm

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

    async def run(
        self,
        task: str,
        tools: list[BaseTool],
        prompt_vars: dict[str, str],
        parent_runtime: ToolRuntime | None = None,
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

        nested_config = RunnableConfig(
            configurable={
                "user_id": user_id,
                "thread_id": f"{thread_prefix}_{user_id}",
                "__deps": parent_configurable.get("__deps"),
                "__side_channel_queue": parent_configurable.get("__side_channel_queue"),
                "__parent_thread_id": parent_configurable.get("thread_id"),
                "user_timezone": parent_configurable.get("user_timezone", "UTC"),
                "user_language": parent_configurable.get("user_language", "fr"),
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
            return ReactSubAgentResult(
                final_message=f"Error: {exc}",
                messages=[],
                duration_ms=elapsed_ms,
            )

        messages = result.get("messages", [])
        final_message = ""
        if messages:
            last_msg = messages[-1]
            raw_content = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
            # Normalize content: Anthropic returns list of content blocks
            # (e.g., [{"type": "text", "text": "..."}]), other providers return str.
            if isinstance(raw_content, list):
                final_message = "\n".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in raw_content
                )
            else:
                final_message = str(raw_content) if raw_content else ""

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

        return ReactSubAgentResult(
            final_message=final_message,
            messages=messages,
            accumulated_registry=accumulated_registry,
            iteration_count=iteration_count,
            duration_ms=elapsed_ms,
        )
