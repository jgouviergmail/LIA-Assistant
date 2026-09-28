"""Display preferences compose the existing response pipeline without extra model calls."""

from importlib import import_module
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from src.domains.agents.context import runtime_context
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.models import MessagesState
from src.domains.agents.services import response_context
from src.domains.agents.services.response_context import ResponseContextBundle
from src.domains.agents.services.streaming.service import StreamingService

pytestmark = pytest.mark.unit
node = import_module("src.domains.agents.nodes.response_node")


@pytest.fixture(autouse=True)
def isolate_response_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep prompt/selection/rendering real while replacing unrelated external I/O."""
    monkeypatch.setattr(node.settings, "skills_enabled", False)
    monkeypatch.setattr(
        response_context, "pop_response_context", AsyncMock(return_value=ResponseContextBundle())
    )
    monkeypatch.setattr(node, "build_performed_actions_block", AsyncMock(return_value=""))
    monkeypatch.setattr(node, "_instrument_business_metrics", AsyncMock())
    monkeypatch.setattr(node, "_schedule_post_response_extractions", Mock())


@pytest.mark.parametrize("display_mode", ["cards", "html", "html_cards", "markdown"])
@pytest.mark.parametrize("selection", [None, "", "email_selected"])
@pytest.mark.parametrize("route_to,voice_enabled", [("planner", False), ("response", True)])
async def test_mode_reaches_prompt_history_selection_rendering_and_sse(
    monkeypatch: pytest.MonkeyPatch,
    display_mode: str,
    selection: str | None,
    route_to: str,
    voice_enabled: bool,
) -> None:
    """Exercise the node itself: substituting I/O must not bypass its mode decisions."""
    context = LiaRuntimeContext.for_conversation(
        user_id=uuid4(),
        conversation_id=uuid4(),
        display_mode=display_mode,
        voice_enabled=voice_enabled,
    )
    monkeypatch.setattr(runtime_context, "runtime_context_if_running", lambda: context)

    rich_html = display_mode in ("html", "html_cards")
    html_directive = rich_html and (route_to == "planner" or not voice_enabled)
    data_cards = display_mode in ("cards", "html_cards")
    prose = '<div class="lia-response"><p>Result.</p></div>' if html_directive else "Result."
    model_output = (
        f"<relevant_ids>{selection}</relevant_ids>" if selection is not None else ""
    ) + prose
    prompts: list[Any] = []

    def respond(prompt: Any) -> AIMessage:
        prompts.append(prompt)
        return AIMessage(content=model_output)

    monkeypatch.setattr(node, "get_llm", lambda *_args: RunnableLambda(respond))
    registry = {
        "email_selected": {"type": "EMAIL", "payload": {"subject": "Selected email"}},
        "email_discarded": {"type": "EMAIL", "payload": {"subject": "Discarded email"}},
    }
    history = AIMessage(content="**Earlier answer**")
    state = MessagesState(
        messages=[
            HumanMessage(content="Earlier query"),
            history,
            HumanMessage(content="Find my email"),
        ],
        current_turn_id=1,
        registry=registry,
        agent_results={"1:email_agent": {"status": "success", "registry_updates": registry}},
        query_intelligence={"route_to": route_to},
    )

    result = await node.response_node(state, {"metadata": {"run_id": "display-mode-test"}})

    assert len(prompts) == 1
    messages = prompts[0].to_messages()
    assert ("Semantic HTML Interface Synthesizer" in str(messages[0].content)) is html_directive
    assert ("<html_cards_composition>" in str(messages[0].content)) is (
        html_directive and display_mode == "html_cards"
    )
    if html_directive and display_mode == "html_cards":
        assert "Do not repeat the cards' full fields" in str(messages[0].content)
    previous_answer = next(message for message in messages if isinstance(message, AIMessage))
    assert ("**Earlier answer**" in str(previous_answer.content)) is not rich_html
    assert "Earlier answer" in str(previous_answer.content)
    assert history.content == "**Earlier answer**"  # Graph history is never rewritten.
    selected_ids = (
        {"email_selected"}
        if selection
        else set() if selection == "" or data_cards else set(registry)
    )
    assert set(result["current_turn_registry"]) == selected_ids
    content = result["messages"][0].content
    assert prose in content
    assert "<relevant_ids>" not in content
    assert ("Selected email" in content) is (data_cards and bool(selection))
    assert "Discarded email" not in content

    service = StreamingService.__new__(StreamingService)
    service.persistable_widgets = {}
    service.voice_context_registry = None
    chunks = [
        chunk
        async for chunk in service._emit_post_stream_registry(
            {**state, **result}, set(), "display-mode-test"
        )
    ]
    if not selected_ids:
        assert chunks == []  # Explicit rejection cannot revive the full registry.
        assert not service.voice_context_registry
    else:
        assert len(chunks) == 1
        assert set(chunks[0][0].metadata["items"]) == selected_ids
        assert set(service.voice_context_registry) == selected_ids


@pytest.mark.parametrize("display_mode", ["html", "html_cards"])
@pytest.mark.parametrize("route_to", ["planner", "response", None])
@pytest.mark.parametrize("voice_enabled", [False, True])
def test_both_rich_modes_keep_the_existing_voice_guard(
    display_mode: str, route_to: str | None, voice_enabled: bool
) -> None:
    assert node._should_inject_html_directive(display_mode, route_to, voice_enabled) is (
        route_to == "planner" or not voice_enabled
    )


@pytest.mark.parametrize("display_mode", ["cards", "html_cards"])
@pytest.mark.parametrize("selection", ["resolved_email", "", None])
@pytest.mark.parametrize("registry_state", ["empty", "stale", "fresh"])
async def test_reference_only_items_are_candidates_before_selection(
    monkeypatch: pytest.MonkeyPatch,
    display_mode: str,
    selection: str | None,
    registry_state: str,
) -> None:
    """A retained reference can render; rejection must not revive its fallback card."""
    context = LiaRuntimeContext.for_conversation(
        user_id=uuid4(), conversation_id=uuid4(), display_mode=display_mode
    )
    monkeypatch.setattr(runtime_context, "runtime_context_if_running", lambda: context)
    prose = "Here is the reference." if selection else "No relevant record."
    model_output = (
        f"<relevant_ids>{selection}</relevant_ids>" if selection is not None else ""
    ) + prose
    prompts: list[Any] = []

    def respond(prompt: Any) -> AIMessage:
        prompts.append(prompt)
        return AIMessage(content=model_output)

    monkeypatch.setattr(node, "get_llm", lambda *_args: RunnableLambda(respond))
    registry = (
        {"stale_email": {"type": "EMAIL", "payload": {"id": "stale", "subject": "Stale email"}}}
        if registry_state == "stale"
        else {}
    )
    has_fresh_result = registry_state == "fresh"
    if has_fresh_result:
        registry = {
            "fresh_email": {
                "type": "EMAIL",
                "payload": {"id": "resolved_email", "subject": "Fresh reference"},
            }
        }
    expected_subject = "Fresh reference" if has_fresh_result else "Selected reference"
    resolved_items = [
        {"id": "resolved_email", "subject": "Selected reference"},
        {"id": "discarded_email", "subject": "Discarded reference"},
    ]
    state = MessagesState(
        messages=[HumanMessage(content="Show me the selected reference")],
        current_turn_id=2,
        turn_type="REFERENCE_PURE",
        registry=registry,
        agent_results=(
            {"2:email_agent": {"status": "success", "registry_updates": registry}}
            if has_fresh_result
            else {}
        ),
        resolved_context={"items": resolved_items, "source_domain": "emails", "source_turn_id": 1},
        query_intelligence={"route_to": "response"},
    )

    result = await node.response_node(state, {"metadata": {"run_id": "reference-mode-test"}})

    assert len(prompts) == 1
    system_prompt = str(prompts[0].to_messages()[0].content)
    assert "<DataForFiltering>" in system_prompt
    candidates = system_prompt.split("<DataForFiltering>", 1)[1].split("</DataForFiltering>", 1)[0]
    assert expected_subject in candidates
    assert ("Discarded reference" in candidates) is not has_fresh_result
    assert "Stale email" not in candidates
    content = result["messages"][0].content
    assert prose in content
    assert (expected_subject in content) is bool(selection)
    if has_fresh_result:
        assert "Selected reference" not in content
    assert "Discarded reference" not in content
    assert "Stale email" not in content
    assert "<relevant_ids>" not in content
    selected = result["current_turn_registry"]
    assert len(selected) == (1 if selection else 0)
    if selection:
        assert next(iter(selected.values()))["payload"]["id"] == "resolved_email"
        assert result["content_final_replacement"] == content
    assert state["registry"] == registry
    assert state["resolved_context"]["items"] == resolved_items

    service = StreamingService.__new__(StreamingService)
    service.persistable_widgets = {}
    service.voice_context_registry = None
    chunks = [
        chunk
        async for chunk in service._emit_post_stream_registry(
            {**state, **result}, set(), "reference-mode-test"
        )
    ]
    if selection:
        assert len(chunks) == 1
        assert set(chunks[0][0].metadata["items"]) == set(selected)
    else:
        assert chunks == []
