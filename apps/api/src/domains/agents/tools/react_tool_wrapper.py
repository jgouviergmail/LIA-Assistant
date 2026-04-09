"""ReactToolWrapper — Wraps tools for the ReAct execution mode.

Converts tool outputs (UnifiedToolOutput, ToolResponse dict, etc.) to strings
for the ReAct LLM while accumulating registry items and draft metadata on the side.

Pattern: based on _MCPReActWrapper (mcp_react_tools.py) with draft collection.

The wrapper preserves the original tool's name, description, and args_schema so the
LLM sees the same interface. The _arun() method delegates to the original tool,
then extracts:
- registry_updates → _accumulated_registry (for frontend data cards)
- draft metadata (requires_confirmation) → _accumulated_drafts (for HITL)
"""

from typing import Any

import structlog
from langchain_core.tools import BaseTool
from pydantic import PrivateAttr

logger = structlog.get_logger(__name__)


class ReactToolWrapper(BaseTool):
    """Wraps a BaseTool for ReAct execution: collects registry items and draft metadata.

    The ReAct agent needs string results to reason about tool outputs. This wrapper
    intercepts structured outputs and converts them to strings while capturing
    side-channel data (registry items, draft metadata) for later propagation to
    the parent graph state.

    Attributes:
        _original_tool: The wrapped BaseTool instance.
        _accumulated_registry: Registry items collected from tool outputs.
        _accumulated_drafts: Draft metadata for tools requiring HITL confirmation.
        _hitl_required: Whether this tool requires HITL approval before execution.
    """

    _original_tool: BaseTool = PrivateAttr()
    _accumulated_registry: dict[str, Any] = PrivateAttr(default_factory=dict)
    _accumulated_drafts: list[dict[str, Any]] = PrivateAttr(default_factory=list)
    _hitl_required: bool = PrivateAttr(default=False)

    def __init__(
        self,
        original_tool: BaseTool,
        *,
        hitl_required: bool = False,
    ) -> None:
        """Initialize wrapper from a BaseTool.

        Args:
            original_tool: The original tool to wrap.
            hitl_required: Whether this tool requires HITL approval (mutation tool).
        """
        super().__init__(
            name=original_tool.name,
            description=original_tool.description,
            args_schema=original_tool.args_schema,
        )
        self._original_tool = original_tool
        self._hitl_required = hitl_required

    @property
    def hitl_required(self) -> bool:
        """Whether this tool requires HITL approval."""
        return self._hitl_required

    async def _arun(self, **kwargs: Any) -> str:
        """Execute the original tool and return string result.

        Note: In the actual ReAct flow, react_execute_tools_node calls
        wrapper._original_tool.coroutine() + wrapper._process_result() directly
        to inject ToolRuntime properly. This _arun() method is kept because
        LangChain's bind_tools() requires BaseTool subclasses to implement it,
        and it serves as a fallback path without ToolRuntime injection.

        Args:
            **kwargs: Tool arguments.

        Returns:
            String representation of the tool result for ReAct LLM context.
        """
        try:
            # Note: when called via _arun(), no config is available.
            # For proper ToolRuntime injection, use _original_tool.ainvoke(args, config=config)
            # directly from the node (see react_execute_tools_node).
            result = await self._original_tool.ainvoke(kwargs)
        except BaseException as exc:
            error_msg = str(exc)
            if hasattr(exc, "exceptions"):
                for sub in exc.exceptions:
                    error_msg = str(sub)
            logger.warning(
                "react_tool_wrapper_error",
                tool_name=self.name,
                error=error_msg,
                error_type=type(exc).__name__,
            )
            return f"ERROR: {error_msg}"

        return self._process_result(result)

    def _process_result(self, result: Any) -> str:
        """Extract registry items and draft metadata, return string for LLM.

        Args:
            result: Raw tool output (UnifiedToolOutput, dict, or string).

        Returns:
            String representation for the ReAct LLM.
        """
        # UnifiedToolOutput (Pydantic model with .message, .registry_updates, .tool_metadata)
        if hasattr(result, "registry_updates") and hasattr(result, "message"):
            if result.registry_updates:
                self._accumulated_registry.update(result.registry_updates)

            # Draft detection (mutation tools return requires_confirmation=True)
            tool_metadata = getattr(result, "tool_metadata", None) or {}
            if tool_metadata.get("requires_confirmation"):
                self._accumulated_drafts.append(
                    {
                        "draft_id": tool_metadata.get("draft_id", ""),
                        "draft_type": tool_metadata.get("draft_type", ""),
                        "draft_content": tool_metadata.get("draft_content", {}),
                        "draft_summary": getattr(result, "summary_for_llm", "") or "",
                        "registry_ids": list(
                            result.registry_updates.keys() if result.registry_updates else []
                        ),
                        "tool_name": self.name,
                    }
                )

            # Include data so the ReAct LLM can reason on actual values (dates, names, etc.)
            # Priority: structured_data > registry payload extraction > message only
            data_for_llm = self._extract_data_for_llm(result)
            if data_for_llm:
                return f"{result.message}\n\nData:\n{data_for_llm}"
            return result.message

        # Dict result (ToolResponse.model_dump() format)
        if isinstance(result, dict):
            if result.get("registry_updates"):
                self._accumulated_registry.update(result["registry_updates"])
            return result.get("message", str(result))

        # String passthrough
        return str(result)

    @staticmethod
    def _extract_data_for_llm(result: Any) -> str:
        """Extract structured data from tool output for LLM reasoning.

        Priority:
        1. structured_data (explicit, e.g., from UnifiedToolOutput.data_success)
        2. registry_updates payloads (fallback — extract payloads from RegistryItems)
        3. Empty string (message-only, no extra data)

        Args:
            result: Tool output with structured_data and/or registry_updates.

        Returns:
            JSON string of data, or empty string if no data available.
        """
        import json

        data: dict[str, Any] | None = None

        # Priority 1: explicit structured_data
        structured = getattr(result, "structured_data", None)
        if structured and isinstance(structured, dict) and structured:
            data = structured

        # Priority 2: extract payloads from registry_updates
        if data is None and result.registry_updates:
            grouped: dict[str, list[Any]] = {}
            for item in result.registry_updates.values():
                payload = getattr(item, "payload", None) or (
                    item.get("payload") if isinstance(item, dict) else None
                )
                if payload:
                    item_type = getattr(item, "type", None)
                    type_key = (
                        item_type.value.lower() + "s" if hasattr(item_type, "value") else "items"
                    )
                    grouped.setdefault(type_key, []).append(payload)
            if grouped:
                data = grouped

        if not data:
            return ""

        try:
            data_str = json.dumps(data, ensure_ascii=False, default=str)
            if len(data_str) > 8000:
                data_str = data_str[:8000] + "... (truncated)"
            return data_str
        except (TypeError, ValueError):
            return ""

    def _run(self, **kwargs: Any) -> str:
        """Synchronous execution not supported."""
        raise NotImplementedError("ReactToolWrapper is async only.")
