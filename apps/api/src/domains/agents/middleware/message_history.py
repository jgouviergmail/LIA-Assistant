"""
Message History Middleware for LangGraph Agents (LangChain v1.0).

Replaces the legacy pre_model_hook pattern with v1.0-compliant middleware.
Filters message history for LLM input while preserving full state for tools.

Pattern: Official LangGraph best practice for multi-turn conversations.
Ref: https://langchain-ai.github.io/langgraph/how-tos/create-react-agent-manage-message-history/

Migration Note:
    LangChain v1.0 removed pre_model_hook in favor of middleware architecture.
    This middleware provides equivalent functionality via before_model() hook.

Usage:
    >>> middleware = MessageHistoryMiddleware(
    ...     keep_last_n=10,
    ...     max_tokens=4000,
    ... )
    >>> agent = create_agent(
    ...     model=llm,
    ...     tools=tools,
    ...     middleware=[hitl_middleware, middleware],
    ... )

Benefits:
    - Tools can access full state["messages"] via runtime
    - Agent sees enough context to make intelligent decisions
    - Prevents context window overflow (token limit)
    - Generic: works for contacts, gmail, calendar, etc.
"""

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from src.core.config import settings
from src.core.field_names import FIELD_RUN_ID
from src.domains.agents.utils.message_filters import enforce_tool_message_pairing
from src.domains.agents.utils.token_utils import count_messages_tokens
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class MessageHistoryMiddleware(AgentMiddleware):
    """
    Middleware for filtering message history before model calls.

    This middleware intelligently filters the message history to:
    1. Always include SystemMessage (agent instructions)
    2. Prioritize ToolMessages (critical for context resolution)
    3. Keep recent HumanMessage/AIMessage
    4. Trim by tokens if exceeds max_tokens

    The full message history remains available in state["messages"] for tool access.
    Only the LLM input is filtered via llm_input_messages.

    Attributes:
        keep_last_n: Number of recent messages to keep (excluding SystemMessage)
        max_tokens: Maximum tokens to keep in filtered history
        encoding_name: Tiktoken encoding for token counting
    """

    def __init__(
        self,
        keep_last_n: int | None = None,
        max_tokens: int | None = None,
        encoding_name: str = "o200k_base",
    ) -> None:
        """
        Initialize MessageHistoryMiddleware.

        Args:
            keep_last_n: Number of recent messages to keep (default: from settings)
            max_tokens: Max tokens to keep (default: from settings)
            encoding_name: Tiktoken encoding for token counting
        """
        super().__init__()
        self.keep_last_n = keep_last_n or settings.agent_history_keep_last
        self.max_tokens = max_tokens or settings.max_tokens_history
        self.encoding_name = encoding_name

        logger.info(
            "message_history_middleware_initialized",
            keep_last_n=self.keep_last_n,
            max_tokens=self.max_tokens,
            encoding=self.encoding_name,
        )

    @staticmethod
    def _build_atomic_units(messages: list[Any]) -> list[list[Any]]:
        """Group messages into units that must survive or drop TOGETHER.

        An AIMessage carrying ``tool_calls`` and the ToolMessages answering
        them form one atomic unit: selecting or trimming them individually
        detaches tool results from their carrier, which OpenAI/Anthropic
        reject with a 400 (audit N-179b). Every other message is a
        single-element unit. SystemMessages are handled by the caller.

        Args:
            messages: Non-system messages, in original order.

        Returns:
            Ordered list of units (each a list of messages).
        """
        units: list[list[Any]] = []
        unit_by_call_id: dict[str, list[Any]] = {}

        for msg in messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                unit: list[Any] = [msg]
                units.append(unit)
                for tool_call in msg.tool_calls:
                    call_id = tool_call.get("id") if isinstance(tool_call, dict) else None
                    if call_id:
                        unit_by_call_id[call_id] = unit
            elif isinstance(msg, ToolMessage) and msg.tool_call_id in unit_by_call_id:
                unit_by_call_id[msg.tool_call_id].append(msg)
            else:
                # Plain message — or an orphan ToolMessage from an already
                # corrupted history; the final pairing net drops the latter.
                units.append([msg])

        return units

    def before_model(self, state: dict, runtime: Any) -> dict[str, Any] | None:
        """
        Filter messages for LLM input before model call.

        Filtering strategy (pair-safe, audit N-179b):
        1. Always include SystemMessage
        2. Group non-system messages into ATOMIC units — an AIMessage with
           tool_calls plus its ToolMessages travel together
        3. Keep the most recent units within the keep_last_n message budget
        4. Trim whole OLDEST units while over max_tokens
        5. Safety net: enforce the tool-pairing contract on the result

        Args:
            state: Current agent state containing messages
            runtime: Agent runtime context (not used here but required by signature)

        Returns:
            dict with "llm_input_messages" key containing filtered messages,
            or None if no filtering needed.
        """
        messages = state.get("messages", [])

        if not messages:
            return None  # No messages to filter

        # 1. Extract SystemMessage (always include)
        system_messages = [msg for msg in messages if isinstance(msg, SystemMessage)]
        non_system = [msg for msg in messages if not isinstance(msg, SystemMessage)]

        # 2. Group into atomic tool-call units
        units = self._build_atomic_units(non_system)

        # 3. Keep the most recent units within the message budget.
        # The newest unit is always kept, even when larger than the budget:
        # dropping the current tool round entirely would blind the agent.
        selected: list[list[Any]] = []
        selected_count = 0
        for unit in reversed(units):
            if selected and selected_count + len(unit) > self.keep_last_n:
                break
            selected.append(unit)
            selected_count += len(unit)
        selected.reverse()

        # 4. Trim by tokens: drop whole OLDEST units first, never split one.
        def _flatten(units_list: list[list[Any]]) -> list[Any]:
            return system_messages + [msg for unit in units_list for msg in unit]

        filtered = _flatten(selected)
        total_tokens = count_messages_tokens(filtered, self.encoding_name)
        while total_tokens > self.max_tokens and len(selected) > 1:
            selected.pop(0)
            filtered = _flatten(selected)
            total_tokens = count_messages_tokens(filtered, self.encoding_name)

        # 5. Safety net — guarantees the provider contract even for histories
        # that were already inconsistent before filtering.
        filtered = system_messages + enforce_tool_message_pairing(
            [msg for msg in filtered if not isinstance(msg, SystemMessage)]
        )

        # Log filtering statistics
        tool_count = sum(1 for m in filtered if isinstance(m, ToolMessage))
        logger.info(
            "message_history_filtered",
            run_id=state.get(FIELD_RUN_ID),
            total_messages=len(messages),
            filtered_messages=len(filtered),
            tool_messages_kept=tool_count,
            total_tokens=total_tokens,
            max_tokens=self.max_tokens,
        )

        # Return via llm_input_messages to preserve full state["messages"]
        return {"llm_input_messages": filtered}
