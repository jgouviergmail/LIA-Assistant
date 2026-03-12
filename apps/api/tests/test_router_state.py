"""
Unit tests for router node state management.
Ensures router JSON output does NOT pollute the messages state.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.graph import build_graph
from src.domains.agents.models import create_initial_state


@pytest.fixture
async def mock_store():
    """Mock tool context store for tests."""
    store = AsyncMock()
    store.aget = AsyncMock(return_value=None)
    store.aput = AsyncMock()
    return store


class TestRouterStateManagement:
    """Test that router node doesn't add JSON output to messages state."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"), reason="Requires OPENAI_API_KEY for integration test"
    )
    async def test_router_does_not_add_json_to_messages(self, mock_store, agent_registry):
        """
        Test that router node does NOT add its JSON decision to messages.

        The router node should only update routing_history, not messages.
        This prevents the JSON routing decision from appearing in the user's chat.
        """
        # Build graph with mocked store (agent_registry fixture initializes agents)
        with patch("src.domains.agents.graph.get_tool_context_store", return_value=mock_store):
            graph, _ = await build_graph()

        # Create initial state with a user message
        state = create_initial_state(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            session_id="test_session",
            run_id="test_run",
        )

        # Add user message
        user_message = HumanMessage(content="je ne sais pas")
        state["messages"].append(user_message)

        # Execute graph
        result = await graph.ainvoke(state, config={"metadata": {"run_id": "test_run"}})

        # Verify messages state
        messages = result["messages"]

        # Assert: Should contain HumanMessage + final AIMessage (response)
        # Should NOT contain any JSON routing decision
        assert len(messages) >= 2, "Should have at least user message + AI response"

        # Check first message is user's
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "je ne sais pas"

        # Check last message is AI's final response
        assert isinstance(messages[-1], AIMessage)
        last_message_content = messages[-1].content

        # Assert: Last message should NOT be JSON
        # (Router JSON should not appear in messages)
        assert not last_message_content.strip().startswith(
            "{"
        ), f"Router JSON output should NOT appear in messages. Found: {last_message_content[:100]}"

        # Assert: Last message should NOT contain router JSON keys
        router_keys = ["intention", "confidence", "context_label", "next_node", "reasoning"]
        for key in router_keys:
            assert f'"{key}"' not in last_message_content, (
                f"Router JSON key '{key}' found in final message. "
                f"Router output should not pollute messages state."
            )

        # Verify routing_history was updated correctly
        routing_history = result.get("routing_history", [])
        assert len(routing_history) > 0, "Routing history should be populated"

        # Verify router decision is in routing_history (NOT in messages)
        last_routing = routing_history[-1]
        assert hasattr(last_routing, "intention")
        assert hasattr(last_routing, "confidence")
        assert hasattr(last_routing, "next_node")

    @pytest.mark.asyncio
    async def test_router_output_only_in_routing_history(self, mock_store, agent_registry):
        """
        Test that router decision exists ONLY in routing_history.

        Ensures proper separation of concerns:
        - Messages state: conversational messages only
        - Routing history: routing decisions only
        """
        # Build graph with mocked store (agent_registry fixture initializes agents)
        with patch("src.domains.agents.graph.get_tool_context_store", return_value=mock_store):
            graph, _ = await build_graph()

        # Create state with user message
        state = create_initial_state(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            session_id="test_session",
            run_id="test_run",
        )
        state["messages"].append(HumanMessage(content="Hello"))

        # Execute graph
        result = await graph.ainvoke(state, config={"metadata": {"run_id": "test_run"}})

        # Extract routing decision from routing_history
        routing_history = result.get("routing_history", [])
        assert len(routing_history) == 1, "Should have exactly one routing decision"

        router_decision = routing_history[0]

        # Verify routing decision has expected structure
        assert hasattr(router_decision, "intention")
        assert hasattr(router_decision, "confidence")
        assert hasattr(router_decision, "context_label")
        assert hasattr(router_decision, "next_node")
        assert hasattr(router_decision, "reasoning")

        # Verify this decision is NOT in messages
        messages = result["messages"]
        for message in messages:
            if isinstance(message, AIMessage):
                # AI messages should be conversational responses, not JSON
                content = message.content.strip()

                # Should not be JSON structure
                assert not (
                    content.startswith("{") and content.endswith("}")
                ), f"AIMessage contains JSON instead of conversational response: {content[:100]}"

                # Should not contain routing decision data
                assert (
                    router_decision.intention not in content or len(content) > 200
                ), "AIMessage appears to be router decision instead of conversation"

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"), reason="Requires OPENAI_API_KEY for integration test"
    )
    async def test_multiple_messages_conversation(self, mock_store, agent_registry):
        """
        Test multi-turn conversation doesn't accumulate router JSON in messages.

        Ensures router decisions stay in routing_history across multiple turns.
        """
        # Build graph with mocked store (agent_registry fixture initializes agents)
        with patch("src.domains.agents.graph.get_tool_context_store", return_value=mock_store):
            graph, _ = await build_graph()

        # Initial state
        state = create_initial_state(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            session_id="test_session",
            run_id="test_run_1",
        )

        # Turn 1
        state["messages"].append(HumanMessage(content="Hello"))
        result1 = await graph.ainvoke(state, config={"metadata": {"run_id": "test_run_1"}})

        # Turn 2 - use previous state
        result1["messages"].append(HumanMessage(content="How are you?"))
        result2 = await graph.ainvoke(result1, config={"metadata": {"run_id": "test_run_2"}})

        # Verify no JSON pollution in messages
        messages = result2["messages"]

        # Count message types
        human_messages = [m for m in messages if isinstance(m, HumanMessage)]
        ai_messages = [m for m in messages if isinstance(m, AIMessage)]

        assert len(human_messages) == 2, "Should have 2 user messages"
        assert len(ai_messages) >= 1, "Should have at least 1 AI response"

        # Verify NO AI message is JSON
        for ai_msg in ai_messages:
            content = ai_msg.content.strip()
            assert not content.startswith("{"), f"Found JSON in AI message: {content[:100]}"

        # Verify routing_history has correct number of decisions
        routing_history = result2.get("routing_history", [])
        assert len(routing_history) >= 2, "Should have routing decisions for both turns"


class TestRouterWithStructuredOutput:
    """Test with_structured_output() integration."""

    @pytest.mark.asyncio
    async def test_router_returns_pydantic_object(self, mock_store, agent_registry):
        """Test that router node correctly returns RouterOutput Pydantic object."""

        # Build graph with mocked store (agent_registry fixture initializes agents)
        with patch("src.domains.agents.graph.get_tool_context_store", return_value=mock_store):
            graph, _ = await build_graph()

        # Create state
        state = create_initial_state(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            session_id="test_session",
            run_id="test_run",
        )
        state["messages"].append(HumanMessage(content="Test message"))

        # Execute graph
        result = await graph.ainvoke(state, config={"metadata": {"run_id": "test_run"}})

        # Verify routing_history contains RouterOutput objects
        routing_history = result.get("routing_history", [])
        assert len(routing_history) > 0

        router_output = routing_history[-1]

        # Check it's a RouterOutput instance (or has RouterOutput attributes)
        assert hasattr(router_output, "intention")
        assert hasattr(router_output, "confidence")
        assert hasattr(router_output, "context_label")
        assert hasattr(router_output, "next_node")
        assert hasattr(router_output, "reasoning")

        # Verify types
        assert isinstance(router_output.intention, str)
        assert isinstance(router_output.confidence, float)
        assert isinstance(router_output.context_label, str)
        assert isinstance(router_output.next_node, str)
        assert isinstance(router_output.reasoning, str)

        # Verify confidence is in valid range
        assert 0.0 <= router_output.confidence <= 1.0


class TestRouterJSONNotStreamedToUser:
    """Test that router JSON is NOT streamed to user via SSE."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"), reason="Requires OPENAI_API_KEY for integration test"
    )
    async def test_router_json_not_in_sse_stream(self, mock_store, agent_registry):
        """
        Test that router JSON tokens are NOT streamed to user.

        Router node generates JSON with with_structured_output(), but this JSON
        should only appear in routing_history, NOT in the SSE token stream.
        """
        import uuid

        from src.domains.agents.api.service import AgentService

        # Mock the store to avoid database connection (agent_registry fixture initializes agents)
        with patch("src.domains.agents.graph.get_tool_context_store", return_value=mock_store):
            service = AgentService()

            # Collect all streamed tokens
            tokens = []
            router_decision_received = False

            async for chunk in service.stream_chat_response(
                "je ne sais pas",  # Test case that was failing
                user_id=uuid.uuid4(),
                session_id="test_session_streaming",
            ):
                if chunk.type == "token":
                    tokens.append(chunk.content)
                elif chunk.type == "router_decision":
                    router_decision_received = True

        # Reconstruct full response from tokens
        full_response = "".join(tokens)

        # Assert: Router decision was sent via separate chunk (not tokens)
        assert router_decision_received, "Router decision should be sent as separate chunk"

        # Assert: Response should NOT contain router JSON keys
        router_json_indicators = [
            '"intention"',
            '"confidence"',
            '"context_label"',
            '"next_node"',
            '"reasoning"',
            '{"intention"',  # Start of JSON object
        ]

        for indicator in router_json_indicators:
            assert indicator not in full_response, (
                f"Router JSON indicator '{indicator}' found in streamed response. "
                f"Router JSON should not be streamed to user.\n"
                f"Response preview: {full_response[:200]}"
            )

        # Assert: Response should be conversational text, not JSON
        assert not full_response.strip().startswith("{"), (
            f"Response starts with '{{' - appears to be JSON instead of conversation.\n"
            f"Response: {full_response[:200]}"
        )

        # Assert: Response is not empty
        assert len(full_response) > 0, "Response should contain content"

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"), reason="Requires OPENAI_API_KEY for integration test"
    )
    async def test_only_response_node_tokens_streamed(self, mock_store, agent_registry):
        """
        Test that ONLY response node tokens are streamed, not router tokens.

        Verifies the node filtering logic in AgentService.stream_chat_response().
        """
        import uuid

        from src.domains.agents.api.service import AgentService

        # Mock the store to avoid database connection (agent_registry fixture initializes agents)
        with patch("src.domains.agents.graph.get_tool_context_store", return_value=mock_store):
            service = AgentService()

            # Collect tokens and track if we get JSON-like content
            tokens = []
            has_json_structure = False

            async for chunk in service.stream_chat_response(
                "Hello",
                user_id=uuid.uuid4(),
                session_id="test_filtering",
            ):
                if chunk.type == "token":
                    token = chunk.content
                    tokens.append(token)

                    # Check if token looks like JSON (router output)
                    if token.strip() in ["{", "}", "[", "]"] or '":"' in token:
                        has_json_structure = True

        full_response = "".join(tokens)

        # Assert: No JSON structure in tokens
        assert not has_json_structure, (
            f"JSON structure found in streamed tokens. "
            f"This suggests router tokens were not filtered.\n"
            f"Response: {full_response}"
        )

        # Assert: Response is conversational
        # (should contain words, not just punctuation/JSON)
        import re

        word_count = len(re.findall(r"\w+", full_response))
        assert word_count > 5, (
            f"Response has only {word_count} words - seems too short or malformed.\n"
            f"Response: {full_response}"
        )
