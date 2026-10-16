"""The closing pass of a ReAct sub-loop: its last call writes, it does not search (ADR-083).

When a sub-loop ran out of budget, the prebuilt agent substituted its own sentence
for the model's answer and every result the loop had gathered was lost — production,
2026-10-13: nine rounds of searches, then a delegation that reported « Sorry, need
more steps to process this request. » as a SUCCESS. On an odd limit the same loop
raised ``GraphRecursionError`` instead (see ``react_runner_budget``).

The native agent's model middleware gives the last call NO tool and flattens the
history into one message. A reply that still proposes a call is refused before
the graph can dispatch it: a promise to do more work is not the loop's answer.

What the loop read stays third-party data: each result is wrapped as external
content, because a tool output moved into a USER message would otherwise read
with the authority of the one who asked.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain.agents.middleware.types import PrivateStateAttr
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.managed.is_last_step import RemainingStepsManager

from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.tools.react_runner_budget import CLOSING_BELOW_REMAINING_STEPS
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.llm.tool_call_blocks import has_tool_call_block

#: How a tool result is labelled inside its external-content envelope.
_RESULT_SOURCE_TYPE = "sub_agent_tool_result"

#: What the loop's model input is: the system prompt, then the messages.
ModelInput = Sequence[BaseMessage]


class ClosingState(AgentState[Any]):
    """The native agent state plus LangGraph's managed graph-step allowance."""

    # Native agent IO excludes managed fields; LangGraph recognizes the LAST metadata item.
    remaining_steps: Annotated[int, PrivateStateAttr, RemainingStepsManager]


@dataclass
class ClosingTrace:
    """What one run's selector saw: one instance per run, never shared."""

    closed: bool = False


def _lines() -> dict[str, str]:
    """The one-line scaffolds of the research log, read from the store (cached)."""
    return dict(parse_prompt_sections(read_prompt_file("react_runner_closing_lines"), 2))


def _call_entries(
    message: AIMessage, calls: dict[str, tuple[int, str]], lines: Mapping[str, str]
) -> list[str]:
    """What a model turn adds to the log: its own words, then each call it made."""
    entries: list[str] = []
    text = coerce_content_to_text(message.content).strip()
    if text:
        entries.append(lines["note"].format(content=text))
    for call in message.tool_calls:
        index = len(calls) + 1
        calls[call.get("id") or f"call-{index}"] = (index, call["name"])
        arguments = json.dumps(call.get("args") or {}, ensure_ascii=False, sort_keys=True)
        entries.append(lines["call"].format(index=index, tool=call["name"], arguments=arguments))
    return entries


def _result_entries(
    message: ToolMessage, calls: Mapping[str, tuple[int, str]], lines: Mapping[str, str]
) -> list[str]:
    """What a tool result adds to the log: its label, then its content as external data."""
    index, called = calls.get(message.tool_call_id, (0, ""))
    tool = message.name or called or "tool"
    text = coerce_content_to_text(message.content).strip()
    body = wrap_external_content(text, tool, _RESULT_SOURCE_TYPE) if text else lines["empty"]
    return [lines["result"].format(index=index, tool=tool), body]


def research_log(history: Sequence[BaseMessage]) -> str:
    """The loop's calls and results as text, in order and whole.

    Nothing is cut: the closing call reads what the previous call already read, and a
    shorter log would trade what the model knows for tokens.

    Args:
        history: The loop's messages after the task.

    Returns:
        The log, or the line saying no tool was called.
    """
    lines = _lines()
    calls: dict[str, tuple[int, str]] = {}
    entries: list[str] = []
    for message in history:
        if isinstance(message, AIMessage):
            entries.extend(_call_entries(message, calls, lines))
        elif isinstance(message, ToolMessage):
            entries.extend(_result_entries(message, calls, lines))
        else:
            # Never expected after the task; kept rather than dropped in silence.
            text = coerce_content_to_text(message.content).strip()
            if text:
                entries.append(lines["note"].format(content=text))
    return "\n".join(entries) if entries else lines["nothing"]


def closing_messages(messages: ModelInput) -> list[BaseMessage]:
    """The closing call's input: the same system prompt, then one message.

    The system prompt is kept as it is — a provider caches its prefix. Everything else
    becomes one user message: the task, the research log and the closing directive.

    Args:
        messages: The loop's model input (system prompt first, then the history).

    Returns:
        ``[*system messages, HumanMessage]``.
    """
    system = [message for message in messages if isinstance(message, SystemMessage)]
    return [*system, closing_message(messages)]


def closing_message(messages: ModelInput) -> HumanMessage:
    """The task and whole external research log, without copying the system prefix."""
    conversation = [message for message in messages if not isinstance(message, SystemMessage)]
    task_at = next(
        (at for at, message in enumerate(conversation) if isinstance(message, HumanMessage)),
        None,
    )
    task = "" if task_at is None else coerce_content_to_text(conversation[task_at].content)
    history = [message for at, message in enumerate(conversation) if at != task_at]
    directive = load_prompt("react_runner_closing_prompt").format(
        task=task, research_log=research_log(history)
    )
    return HumanMessage(content=directive)


def _without_unbound_calls(response: ModelResponse[Any]) -> ModelResponse[Any]:
    """Reject a closing narration without dispatching its proposed calls; keep billed usage."""
    messages: list[BaseMessage] = []
    for message in response.result:
        if isinstance(message, AIMessage) and (
            message.tool_calls or message.invalid_tool_calls or has_tool_call_block(message.content)
        ):
            message = AIMessage(
                content="",
                id=message.id,
                usage_metadata=message.usage_metadata,
                response_metadata=message.response_metadata,
            )
        messages.append(message)
    return ModelResponse(result=messages, structured_response=response.structured_response)


class ClosingMiddleware(AgentMiddleware[ClosingState, LiaRuntimeContext]):
    """Wrap the model node, adding no graph step and retaining the published arithmetic."""

    state_schema = ClosingState

    def __init__(self, trace: ClosingTrace) -> None:
        self.trace = trace

    async def awrap_model_call(
        self,
        request: ModelRequest[LiaRuntimeContext],
        handler: Callable[[ModelRequest[LiaRuntimeContext]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        if not request.tools:
            return _without_unbound_calls(await handler(request))
        remaining = request.state.get("remaining_steps")
        if not isinstance(remaining, int) or remaining >= CLOSING_BELOW_REMAINING_STEPS:
            return await handler(request)
        self.trace.closed = True
        closing = request.override(
            messages=[closing_message(request.messages)], tools=[], tool_choice=None
        )
        return _without_unbound_calls(await handler(closing))
