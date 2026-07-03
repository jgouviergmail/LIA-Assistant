"""Tool-call pairing invariants for MessageHistoryMiddleware (audit N-179b).

OpenAI and Anthropic both reject histories where a tool result has no
preceding assistant tool_call (400 "must be a response to a preceding
message with 'tool_calls'") or where an assistant tool_call has no result.
The middleware's "last 5 ToolMessages" priority and its token trim both
selected messages INDIVIDUALLY, detaching ToolMessages from the AIMessage
that carries their tool_calls.

Every filtered output must satisfy the provider sequence contract, whatever
the keep_last_n / max_tokens pressure.
"""

from __future__ import annotations

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.domains.agents.middleware.message_history import MessageHistoryMiddleware


def _assert_provider_valid_sequence(messages: list[BaseMessage]) -> None:
    """Assert the OpenAI/Anthropic tool-pairing contract on a message list."""
    carrier_position: dict[str, int] = {}
    for i, msg in enumerate(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tool_call in msg.tool_calls:
                carrier_position[tool_call["id"]] = i

    answered: set[str] = set()
    for i, msg in enumerate(messages):
        if isinstance(msg, ToolMessage):
            assert msg.tool_call_id in carrier_position, (
                f"orphan ToolMessage (tool_call_id={msg.tool_call_id}) — "
                "no AIMessage carries this tool_call"
            )
            assert (
                carrier_position[msg.tool_call_id] < i
            ), f"ToolMessage {msg.tool_call_id} precedes its carrier AIMessage"
            answered.add(msg.tool_call_id)

    for call_id in carrier_position:
        assert (
            call_id in answered
        ), f"AIMessage tool_call {call_id} kept without its ToolMessage result"


def _tool_call(call_id: str) -> dict:
    return {"id": call_id, "name": "get_contacts_tool", "args": {"q": call_id}, "type": "tool_call"}


def _history_with_three_tool_rounds() -> list[BaseMessage]:
    """Realistic multi-round agent history (3 tool rounds, 6 ToolMessages)."""
    return [
        SystemMessage(content="You are the contacts agent."),
        HumanMessage(content="find John"),
        AIMessage(content="", tool_calls=[_tool_call("a1"), _tool_call("a2")]),
        ToolMessage(content="result a1", tool_call_id="a1"),
        ToolMessage(content="result a2", tool_call_id="a2"),
        AIMessage(content="Found John."),
        HumanMessage(content="and his email?"),
        AIMessage(content="", tool_calls=[_tool_call("b1")]),
        ToolMessage(content="result b1", tool_call_id="b1"),
        AIMessage(content="john@example.com"),
        HumanMessage(content="now check Mary, Bob and Eve"),
        AIMessage(
            content="",
            tool_calls=[_tool_call("c1"), _tool_call("c2"), _tool_call("c3")],
        ),
        ToolMessage(content="result c1", tool_call_id="c1"),
        ToolMessage(content="result c2", tool_call_id="c2"),
        ToolMessage(content="result c3", tool_call_id="c3"),
        AIMessage(content="Here are the three contacts."),
        HumanMessage(content="great, summarize"),
    ]


def test_keep_last_n_filtering_never_orphans_tool_messages() -> None:
    """The recency filter must keep AIMessage↔ToolMessages pairs atomic."""
    middleware = MessageHistoryMiddleware(keep_last_n=6, max_tokens=100_000)

    result = middleware.before_model({"messages": _history_with_three_tool_rounds()}, None)

    assert result is not None
    filtered = result["llm_input_messages"]
    _assert_provider_valid_sequence(filtered)
    # The most recent tool round must remain usable context
    assert any(isinstance(m, ToolMessage) for m in filtered)


def test_token_trim_never_orphans_tool_messages() -> None:
    """The token trim must drop pairs atomically, not carriers first."""
    # Tiny budget forces aggressive trimming on a tool-heavy history
    middleware = MessageHistoryMiddleware(keep_last_n=12, max_tokens=60)

    result = middleware.before_model({"messages": _history_with_three_tool_rounds()}, None)

    assert result is not None
    _assert_provider_valid_sequence(result["llm_input_messages"])


def test_every_pressure_combination_yields_valid_sequences() -> None:
    """Sweep filter pressures: no combination may emit an invalid sequence."""
    history = _history_with_three_tool_rounds()
    for keep_last_n in (1, 2, 3, 4, 5, 6, 8, 10, 20):
        for max_tokens in (10, 30, 60, 120, 100_000):
            middleware = MessageHistoryMiddleware(keep_last_n=keep_last_n, max_tokens=max_tokens)
            result = middleware.before_model({"messages": list(history)}, None)
            assert result is not None
            filtered = result["llm_input_messages"]
            _assert_provider_valid_sequence(filtered)
            # SystemMessage always survives
            assert any(isinstance(m, SystemMessage) for m in filtered)


def test_short_history_passes_through_valid() -> None:
    """Sanity: a short, already-valid history stays valid and complete."""
    history = [
        SystemMessage(content="sys"),
        HumanMessage(content="hi"),
        AIMessage(content="", tool_calls=[_tool_call("x1")]),
        ToolMessage(content="result", tool_call_id="x1"),
        AIMessage(content="done"),
    ]
    middleware = MessageHistoryMiddleware(keep_last_n=10, max_tokens=100_000)

    result = middleware.before_model({"messages": history}, None)

    assert result is not None
    filtered = result["llm_input_messages"]
    _assert_provider_valid_sequence(filtered)
    assert len(filtered) == len(history)
