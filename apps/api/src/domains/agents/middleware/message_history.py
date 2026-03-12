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
from langchain_core.messages import SystemMessage, ToolMessage

from src.core.config import settings
from src.core.field_names import FIELD_RUN_ID
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

    def before_model(self, state: dict, runtime: Any) -> dict[str, Any] | None:
        """
        Filter messages for LLM input before model call.

        Intelligent filtering strategy:
        1. Always include SystemMessage
        2. PRIORITIZE ToolMessages (critical for context resolution)
        3. Include recent HumanMessage/AIMessage
        4. Trim by tokens if needed

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

        # 2. INTELLIGENT FILTERING: Prioritize ToolMessages
        # Separate messages by type
        tool_messages = []
        other_messages = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                continue  # Already handled
            elif isinstance(msg, ToolMessage):
                tool_messages.append(msg)
            else:
                other_messages.append(msg)

        # 3. Build filtered list intelligently
        # Strategy: Keep ALL recent ToolMessages + fill remaining slots with other messages
        # This ensures context (search results, etc.) is ALWAYS visible to agent

        # Get indices of messages in original list to preserve order
        message_indices = {id(msg): idx for idx, msg in enumerate(messages)}

        # Take recent ToolMessages (last 5 ToolMessages = ~2-3 tool calls)
        recent_tool_messages = tool_messages[-5:] if len(tool_messages) > 5 else tool_messages

        # Calculate remaining slots
        remaining_slots = self.keep_last_n - len(recent_tool_messages)

        # Fill remaining with most recent other messages
        if remaining_slots > 0:
            recent_other = other_messages[-remaining_slots:]
        else:
            recent_other = []

        # Combine and sort by original order
        combined = recent_tool_messages + recent_other
        combined.sort(key=lambda msg: message_indices.get(id(msg), 0))

        # Final filtered list: SystemMessage + sorted messages
        filtered = system_messages + combined

        # 4. Optional: Trim by tokens if exceeds max_tokens
        total_tokens = count_messages_tokens(filtered, self.encoding_name)
        if total_tokens > self.max_tokens:
            # Trim strategy: Remove oldest non-critical messages first
            # Priority: SystemMessage > ToolMessages > Recent HumanMessage > Old AIMessages
            while total_tokens > self.max_tokens and len(filtered) > len(system_messages) + 1:
                # Find oldest non-system, non-tool message to remove
                removed = False
                for i, msg in enumerate(filtered):
                    if not isinstance(msg, SystemMessage) and not isinstance(msg, ToolMessage):
                        filtered.pop(i)
                        removed = True
                        break

                # If only ToolMessages + SystemMessage left, remove oldest ToolMessage
                if not removed and len(filtered) > len(system_messages) + 1:
                    for i, msg in enumerate(filtered):
                        if isinstance(msg, ToolMessage):
                            filtered.pop(i)
                            break

                total_tokens = count_messages_tokens(filtered, self.encoding_name)

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
