"""ReactToolWrapper — Wraps tools for the ReAct execution mode.

Converts tool outputs (UnifiedToolOutput, ToolResponse dict, etc.) to strings
for the ReAct LLM while accumulating registry items on the side.

Pattern: based on _MCPReActWrapper (mcp_react_tools.py).

The wrapper preserves the original tool's name, description, and args_schema so the
LLM sees the same interface. The _arun() method delegates to the original tool,
then extracts registry_updates → _accumulated_registry (for frontend data cards).

Draft detection (mutation tools returning requires_confirmation) is handled at the
node level in react_execute_tools_node via _extract_draft_info(), which reads the
executable draft content from the registry payload (the wrapper does not collect
drafts — see ADR-070 amendment 2026-05-20).

**The Data block is projected item by item under a token budget (ADR-286).**
Until 2026-09-15 it was a JSON dump cut at 8 000 CHARACTERS: a Gmail
``format=full`` message carries its raw provider tree before its readable
fields, so the budget went to the first item's SMTP headers and base64 and the
model read no subject, id or date of any e-mail. :func:`render_data_block`
pages the FIRST item list of the data at item boundaries — an admitted item is
complete, the block stays valid JSON — and :func:`compose_tool_message` states
a cut to the model and counts it per tool.
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import structlog
from langchain_core.tools import BaseTool
from pydantic import PrivateAttr

logger = structlog.get_logger(__name__)


def mark_untrusted_data(result: Any, data_for_llm: str) -> str:
    """Wrap the Data block unless its provenance is established INTERNAL.

    The provenance travels with ``registry_updates`` (a typed
    :class:`RegistryItemType`, classified by ``data_registry.trust``): a block
    whose registry items are all INTERNAL is handed over bare, a block with
    any EXTERNAL item is wrapped. A block with NO registry items is wrapped
    too — that is the trust module's own rule, fail closed. Until 2026-09-15
    it was handed over bare on the claim that ``structured_data`` alone is
    "authored by the tool": false — ``get_context_list`` and
    ``resolve_reference`` re-serve registry items (e-mail bodies, event
    descriptions) from ``structured_data`` with no registry at all, and the
    documents tool lists third-party text the same way. A wrongly wrapped
    tool-authored shape costs a few tokens; an unmarked third-party text is
    an injection vector.

    Unlike the pipeline surface, this block is a JSON dump with no
    per-item lines to prefix, so the whole block is wrapped with the
    canonical ``<external_content>`` markers already used by the browser and
    web-fetch tools (a tool that wrapped its own text is wrapped again; the
    inner tags are escaped, never trusted).

    Args:
        result: The tool output being serialised.
        data_for_llm: The JSON data block extracted from it.

    Returns:
        The block, wrapped and annotated unless every registry item is internal.
    """
    from src.domains.agents.data_registry.trust import is_external

    registry_updates = getattr(result, "registry_updates", None) or {}
    external_types = {
        str(getattr(item_type, "value", item_type))
        for item in registry_updates.values()
        if (item_type := getattr(item, "type", None)) is not None and is_external(item_type)
    }
    if registry_updates and not external_types:
        return data_for_llm
    source = ",".join(sorted(external_types)) if external_types else "structured_data"

    from src.domains.agents.utils.content_wrapper import (
        injection_notice,
        wrap_external_content,
    )

    notice = injection_notice(data_for_llm, item_type=source, surface="react")
    return wrap_external_content(
        f"{data_for_llm}{notice}",
        source_url=source,
        source_type="registry_payload" if external_types else "structured_data",
    )


@dataclass(frozen=True)
class DataBlock:
    """One tool result projected for the model: complete items under a budget.

    Attributes:
        text: The block handed to the model — valid JSON whenever at least one
            whole item fit.
        shown: Items that reached the model.
        total: Items the tool returned (``1`` for a result with no item list).
        key: The item list's key, ``None`` when the data carried none.
        truncated: Whether anything was left out or cut.
        used_tokens: What the full result would have cost.
        budget_tokens: The budget that decided.
    """

    text: str
    shown: int
    total: int
    key: str | None
    truncated: bool
    used_tokens: int
    budget_tokens: int


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _is_item_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(x, dict) for x in value)


def _cut_text(text: str, used_tokens: int, budget_tokens: int) -> str:
    """Cut a block that has no item boundary to cut at, and SAY so."""
    keep = max(1, int(len(text) * budget_tokens / used_tokens))
    return f"{text[:keep]}... [cut: {budget_tokens} of {used_tokens} tokens]"


def render_data_block(data: dict[str, Any], budget_tokens: int) -> DataBlock:
    """Project ``data`` for the model, item by item, under ``budget_tokens``.

    The HEAVIEST value that is a non-empty list of dicts is the item list —
    the shape every ``_build_items_structured_data`` payload and every registry
    grouping has (heaviest rather than first: a small ``errors`` list ahead of
    the rows must not be the one paged). Its items are admitted one by one
    while the budget holds;
    the scalars and the other keys travel whole, in their original order, so
    an exact ``count`` stays next to a possibly shortened list, and
    ``<key>_shown`` says how many made it. At least one item is always
    admitted, WHOLE: a first item that alone exceeds the budget still passes
    complete (measured on a real mailbox, 2026-09-15: cut mid-JSON it was
    unparseable, and a cut item is useless where an oversized one merely
    costs — the budget is exceeded by at most one item, never silently:
    ``used_tokens`` says by how much). A result with no item list has no
    boundary to cut at: it is dumped whole, or cut explicitly.

    Args:
        data: The tool's structured data (or grouped registry payloads).
        budget_tokens: Tokens the block may occupy.

    Returns:
        The block and its accounting.
    """
    from src.domains.agents.utils.token_utils import count_tokens

    candidates = [k for k, v in data.items() if _is_item_list(v)]
    key = max(candidates, key=lambda k: len(_dumps(data[k]))) if candidates else None
    if key is None:
        text = _dumps(data)
        used = count_tokens(text)
        if used <= budget_tokens:
            return DataBlock(text, 1, 1, None, False, used, budget_tokens)
        return DataBlock(
            _cut_text(text, used, budget_tokens), 1, 1, None, True, used, budget_tokens
        )

    items: list[dict[str, Any]] = data[key]
    used = count_tokens(_dumps({k: v for k, v in data.items() if k != key}))
    shown: list[dict[str, Any]] = []
    for item in items:
        cost = count_tokens(_dumps(item))
        if shown and used + cost > budget_tokens:
            break
        shown.append(item)
        used += cost

    rendered: dict[str, Any] = {}
    for k, v in data.items():
        if k != key:
            rendered[k] = v
            continue
        rendered[key] = shown
        if len(shown) < len(items):
            rendered[f"{key}_shown"] = len(shown)
    return DataBlock(
        text=_dumps(rendered),
        shown=len(shown),
        total=len(items),
        key=key,
        truncated=len(shown) < len(items),
        used_tokens=used,
        budget_tokens=budget_tokens,
    )


def extract_data_block(result: Any, budget_tokens: int) -> DataBlock | None:
    """Pick the data a tool result carries and project it.

    Priority:
    1. structured_data (explicit, e.g., from UnifiedToolOutput.data_success)
    2. registry_updates payloads (fallback — extract payloads from RegistryItems)
    3. None (message-only, no extra data)

    Args:
        result: Tool output with structured_data and/or registry_updates.
        budget_tokens: Tokens the block may occupy.

    Returns:
        The projected block, or ``None`` when the result carries no data.
    """
    data: dict[str, Any] | None = None

    structured = getattr(result, "structured_data", None)
    if structured and isinstance(structured, dict):
        data = structured

    # getattr, not a bare attribute: the MCP sub-agent wrapper also feeds
    # message-only outputs through here.
    if data is None and getattr(result, "registry_updates", None):
        grouped: dict[str, list[Any]] = {}
        for item in result.registry_updates.values():
            payload = getattr(item, "payload", None) or (
                item.get("payload") if isinstance(item, dict) else None
            )
            if payload:
                item_type = getattr(item, "type", None)
                type_key = item_type.value.lower() + "s" if hasattr(item_type, "value") else "items"
                grouped.setdefault(type_key, []).append(payload)
        if grouped:
            data = grouped

    if not data:
        return None
    try:
        return render_data_block(data, budget_tokens)
    except TypeError, ValueError:
        return None


def _default_budget() -> int:
    from src.core.config import get_settings

    return get_settings().react_tool_result_max_tokens


def extract_data_for_llm(result: Any, budget_tokens: int | None = None) -> str:
    """The string door: the projected Data block, or an empty string.

    Args:
        result: Tool output with structured_data and/or registry_updates.
        budget_tokens: Tokens the block may occupy; the settings ceiling when
            omitted.

    Returns:
        JSON text of the projected data, or ``""`` when the result has none.
    """
    budget = budget_tokens if budget_tokens is not None else _default_budget()
    block = extract_data_block(result, budget)
    return block.text if block is not None else ""


def compose_tool_message(result: Any, *, tool_name: str, budget_tokens: int | None = None) -> str:
    """Build the ToolMessage body: message, Data block, budget note.

    The Data block is wrapped as external content when it carries third-party
    text (:func:`mark_untrusted_data`); the budget note is OURS and therefore
    goes AFTER the closing tag, so the model never reads it as third-party text.
    A cut is counted per tool (the name comes from the bound catalogue, so its
    cardinality is bounded) and logged without any content.

    Args:
        result: A ``UnifiedToolOutput``-shaped object (``message`` plus
            optional ``structured_data`` / ``registry_updates``).
        tool_name: The bound tool's name, for the metric and the log.
        budget_tokens: Tokens the block may occupy; the settings ceiling when
            omitted.

    Returns:
        The ToolMessage body.
    """
    from src.domains.agents.utils.react_budget import tool_result_budget_note
    from src.infrastructure.observability.metrics_react import (
        react_tool_result_truncated_total,
    )

    budget = budget_tokens if budget_tokens is not None else _default_budget()
    block = extract_data_block(result, budget)
    if block is None:
        return str(result.message)
    text = f"{result.message}\n\nData:\n{mark_untrusted_data(result, block.text)}"
    if not block.truncated:
        return text
    react_tool_result_truncated_total.labels(tool_name=tool_name).inc()
    logger.info(
        "react_tool_result_truncated",
        tool_name=tool_name,
        shown=block.shown,
        total=block.total,
        used_tokens=block.used_tokens,
        budget_tokens=block.budget_tokens,
    )
    note = tool_result_budget_note(
        shown=block.shown, total=block.total, key=block.key, budget_tokens=block.budget_tokens
    )
    return f"{text}\n{note}"


class ReactToolWrapper(BaseTool):
    """Wraps a BaseTool for ReAct execution: collects registry items.

    The ReAct agent needs string results to reason about tool outputs. This wrapper
    intercepts structured outputs and converts them to strings while capturing
    side-channel data (registry items) for later propagation to the parent graph
    state.

    Attributes:
        _original_tool: The wrapped BaseTool instance.
        _accumulated_registry: Registry items collected from tool outputs.
        _hitl_required: Whether this tool requires HITL approval before execution.
    """

    _original_tool: BaseTool = PrivateAttr()
    _accumulated_registry: dict[str, Any] = PrivateAttr(default_factory=dict)
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
        except asyncio.CancelledError:
            # A user stop must cancel the whole ReAct loop, never become a
            # tool-error string the agent reasons about.
            raise
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

    def _process_result(self, result: Any, budget_tokens: int | None = None) -> str:
        """Extract registry items and return a string representation for the LLM.

        Args:
            result: Raw tool output (UnifiedToolOutput, dict, or string).
            budget_tokens: Tokens the Data block may occupy (ADR-286); the
                settings ceiling when omitted.

        Returns:
            String representation for the ReAct LLM.
        """
        # UnifiedToolOutput (Pydantic model with .message, .registry_updates, .tool_metadata)
        if hasattr(result, "registry_updates") and hasattr(result, "message"):
            if result.registry_updates:
                self._accumulated_registry.update(result.registry_updates)
            # Include data so the ReAct LLM can reason on actual values (dates, names, etc.)
            return compose_tool_message(result, tool_name=self.name, budget_tokens=budget_tokens)

        # Dict result (ToolResponse.model_dump() format)
        if isinstance(result, dict):
            if result.get("registry_updates"):
                self._accumulated_registry.update(result["registry_updates"])
            return result.get("message", str(result))

        # String passthrough
        return str(result)

    def _run(self, **kwargs: Any) -> str:
        """Synchronous execution not supported."""
        raise NotImplementedError("ReactToolWrapper is async only.")
