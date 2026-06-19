"""
Tests for Response Node.
Validates agent results injection and prompt template behavior.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.models import MessagesState
from src.domains.agents.nodes.response_node import format_agent_results_for_prompt, response_node
from src.domains.agents.orchestration.schemas import ContactsResultData
from src.domains.agents.prompts import get_response_prompt


def test_get_response_prompt_returns_formatted_string():
    """Test that get_response_prompt returns a formatted system prompt string.

    Since the refactor, get_response_prompt returns a string (not ChatPromptTemplate).
    The ChatPromptTemplate is now built dynamically in response_node to avoid
    empty system blocks that some providers (e.g., Anthropic) reject.
    """
    result = get_response_prompt()

    # Should return a non-empty string
    assert isinstance(result, str)
    assert len(result) > 0

    # Verify current_datetime was injected (should not contain placeholder)
    assert "{current_datetime}" not in result


def test_get_response_prompt_with_timezone():
    """Test that datetime context is properly injected based on timezone."""
    result = get_response_prompt(user_timezone="Europe/Paris", user_language="fr")

    # Should return a formatted string with datetime context
    assert isinstance(result, str)
    assert len(result) > 0

    # Verify placeholder was replaced (should not contain the placeholder anymore)
    assert "{current_datetime}" not in result

    # Verify the prompt contains datetime information
    # Prompts are now in English ("Current date and time") but datetime value is localized
    assert "date" in result.lower()


def test_format_agent_results_empty():
    """Test formatting when no agents were called.

    NOTE: Data details are now injected via {data_for_filtering}.
    format_agent_results_for_prompt only returns status messages (errors, etc.)
    When no agents or no errors, it returns empty string.
    """
    result = format_agent_results_for_prompt({})
    assert result == ""


def test_format_agent_results_success():
    """Test formatting successful agent results.

    NOTE: Data details are now injected via {data_for_filtering} using the
    generic payload serializer. format_agent_results_for_prompt only returns
    status messages (errors, connector_disabled). Success results return empty.
    """
    agent_results = {
        "contacts_agent": {
            "status": "success",
            "data": ContactsResultData(
                contacts=[
                    {"names": "Contact 1"},
                    {"names": "Contact 2"},
                    {"names": "Contact 3"},
                    {"names": "Contact 4"},
                    {"names": "Contact 5"},
                ],
                total_count=5,
                has_more=False,
            ),
            "error": None,
        }
    }

    # Success results return empty - data is now in {data_for_filtering}
    result = format_agent_results_for_prompt(agent_results)
    assert result == ""  # No status message for success


def test_format_agent_results_connector_disabled():
    """Test formatting when connector is disabled."""
    agent_results = {
        "contacts_agent": {
            "status": "connector_disabled",
            "data": None,
            "error": "Le service Google Contacts n'est pas activé.",
        }
    }

    result = format_agent_results_for_prompt(agent_results)
    assert "⚠️ contacts_agent" in result
    assert "Google Contacts n'est pas activé" in result


def test_format_agent_results_error():
    """Test formatting technical errors."""
    agent_results = {
        "contacts_agent": {
            "status": "error",
            "data": None,
            "error": "Erreur technique lors de l'accès aux contacts",
        }
    }

    result = format_agent_results_for_prompt(agent_results)
    assert "❌ contacts_agent" in result
    assert "Erreur technique" in result


@pytest.mark.asyncio
async def test_response_node_injects_agent_results():
    """Test that response_node properly formats and passes agent_results."""
    # Create state with agent results - use proper contact format
    state = MessagesState(
        messages=[HumanMessage(content="Test message")],
        agent_results={
            "contacts_agent": {
                "status": "success",
                "data": ContactsResultData(
                    contacts=[
                        {"names": "Contact 1"},
                        {"names": "Contact 2"},
                        {"names": "Contact 3"},
                    ],
                    total_count=3,
                    has_more=False,
                ),
                "error": None,
                "tokens_in": 100,
                "tokens_out": 50,
                "duration_ms": 1000,
            }
        },
        metadata={"user_id": "test-user"},
    )

    config = {"metadata": {"run_id": "test-run"}}

    # Test the formatting function directly (unit test)
    # NOTE: Data details are now injected via {data_for_filtering}.
    # format_agent_results_for_prompt only returns status messages.
    from src.domains.agents.nodes.response_node import format_agent_results_for_prompt

    formatted = format_agent_results_for_prompt(state.get("agent_results", {}))
    # Success results return empty - data is now in {data_for_filtering}
    assert formatted == ""

    # Mock the prompt (now returns string) and LLM to create a functional chain
    with patch("src.domains.agents.nodes.response_node.get_response_prompt") as mock_get_prompt:
        with patch("src.domains.agents.nodes.response_node.get_llm") as mock_get_llm:
            with patch("src.domains.agents.nodes.response_node.ChatPromptTemplate") as mock_cpt:
                mock_chain = AsyncMock()
                mock_chain.ainvoke = AsyncMock(return_value=AIMessage(content="Test response"))

                mock_prompt_obj = Mock()
                mock_prompt_obj.__or__ = Mock(return_value=mock_chain)
                mock_cpt.from_messages.return_value = mock_prompt_obj
                mock_get_prompt.return_value = "mock system prompt"
                mock_get_llm.return_value = Mock()

                result = await response_node(state, config)

                assert result["messages"] is not None
                assert len(result["messages"]) == 1
                assert isinstance(result["messages"][0], AIMessage)
                assert result["messages"][0].content == "Test response"


@pytest.mark.asyncio
async def test_response_node_empty_agent_results():
    """Test response_node with no agent results."""
    state = MessagesState(
        messages=[HumanMessage(content="Hello")],
        agent_results={},
        metadata={"user_id": "test-user"},
    )

    config = {"metadata": {"run_id": "test-run"}}

    # Test the formatting function directly
    # NOTE: Empty agent_results returns empty string (data is in {data_for_filtering})
    from src.domains.agents.nodes.response_node import format_agent_results_for_prompt

    formatted = format_agent_results_for_prompt(state.get("agent_results", {}))
    assert formatted == ""  # No status messages for empty results

    # Mock the prompt (now returns string) and LLM to create a functional chain
    with patch("src.domains.agents.nodes.response_node.get_response_prompt") as mock_get_prompt:
        with patch("src.domains.agents.nodes.response_node.get_llm") as mock_get_llm:
            with patch("src.domains.agents.nodes.response_node.ChatPromptTemplate") as mock_cpt:
                mock_chain = AsyncMock()
                mock_chain.ainvoke = AsyncMock(return_value=AIMessage(content="Hi there!"))

                mock_prompt_obj = Mock()
                mock_prompt_obj.__or__ = Mock(return_value=mock_chain)
                mock_cpt.from_messages.return_value = mock_prompt_obj
                mock_get_prompt.return_value = "mock system prompt"
                mock_get_llm.return_value = Mock()

                result = await response_node(state, config)

                assert result["messages"] is not None
                assert len(result["messages"]) == 1
                assert isinstance(result["messages"][0], AIMessage)
                assert result["messages"][0].content == "Hi there!"


@pytest.mark.asyncio
async def test_response_node_multiple_agents():
    """Test response_node with multiple agent results."""
    state = MessagesState(
        messages=[HumanMessage(content="Complex query")],
        agent_results={
            "contacts_agent": {
                "status": "success",
                "data": ContactsResultData(
                    contacts=[{"names": "Contact 1"}, {"names": "Contact 2"}],
                    total_count=2,
                    has_more=False,
                ),
                "error": None,
                "tokens_in": 50,
                "tokens_out": 25,
                "duration_ms": 500,
            },
            "emails_agent": {  # Future agent
                "status": "connector_disabled",
                "data": None,
                "error": "Gmail connector not activated",
                "tokens_in": 0,
                "tokens_out": 0,
                "duration_ms": 10,
            },
        },
        metadata={"user_id": "test-user"},
    )

    config = {"metadata": {"run_id": "test-run"}}

    # Test the formatting function directly
    # NOTE: Data details are now injected via {data_for_filtering}.
    # format_agent_results_for_prompt only returns status messages.
    from src.domains.agents.nodes.response_node import format_agent_results_for_prompt

    formatted = format_agent_results_for_prompt(state.get("agent_results", {}))
    # Success results don't produce status - only connector_disabled does
    assert "⚠️" in formatted
    assert "Gmail connector not activated" in formatted
    # No success emoji or contact count (data is in {data_for_filtering})
    assert "✅" not in formatted

    # Mock the prompt (now returns string) and LLM to create a functional chain
    with patch("src.domains.agents.nodes.response_node.get_response_prompt") as mock_get_prompt:
        with patch("src.domains.agents.nodes.response_node.get_llm") as mock_get_llm:
            with patch("src.domains.agents.nodes.response_node.ChatPromptTemplate") as mock_cpt:
                mock_chain = AsyncMock()
                mock_chain.ainvoke = AsyncMock(return_value=AIMessage(content="Response"))

                mock_prompt_obj = Mock()
                mock_prompt_obj.__or__ = Mock(return_value=mock_chain)
                mock_cpt.from_messages.return_value = mock_prompt_obj
                mock_get_prompt.return_value = "mock system prompt"
                mock_get_llm.return_value = Mock()

                result = await response_node(state, config)

                assert result["messages"] is not None
                assert len(result["messages"]) == 1
                assert isinstance(result["messages"][0], AIMessage)
                assert result["messages"][0].content == "Response"


@pytest.mark.asyncio
async def test_response_node_error_handling():
    """Test response_node handles LLM errors gracefully."""
    state = MessagesState(
        messages=[HumanMessage(content="Test")],
        agent_results={},
        metadata={"user_id": "test-user"},
    )

    config = {"metadata": {"run_id": "test-run"}}

    # Mock the prompt (now returns string) and LLM to create a chain that raises an error
    with patch("src.domains.agents.nodes.response_node.get_response_prompt") as mock_get_prompt:
        with patch("src.domains.agents.nodes.response_node.get_llm") as mock_get_llm:
            with patch("src.domains.agents.nodes.response_node.ChatPromptTemplate") as mock_cpt:
                mock_chain = AsyncMock()
                mock_chain.ainvoke.side_effect = ValueError("LLM error")

                mock_prompt_obj = Mock()
                mock_prompt_obj.__or__ = Mock(return_value=mock_chain)
                mock_cpt.from_messages.return_value = mock_prompt_obj
                mock_get_prompt.return_value = "mock system prompt"
                mock_get_llm.return_value = Mock()

                result = await response_node(state, config)

                assert result["messages"] is not None
                assert len(result["messages"]) == 1
                # Error fallback is an AIMessage (the assistant's reply), not a
                # HumanMessage — see the "BUG FIX" note in response_node's except handler.
                assert isinstance(result["messages"][0], AIMessage)
                assert "Désolé, une erreur s'est produite" in result["messages"][0].content
                assert "ValueError" in result["messages"][0].content


# ============================================================================
# AUTOMATED-SOURCE EXTRACTION GUARD (is_automated_source redesign)
# ============================================================================
# response_node computes a single `_is_automated_source` flag from
# config["configurable"][FIELD_IS_AUTOMATED_SOURCE] and reuses it to gate ALL
# four post-response extractions (memory, interest, journal, psyche). These
# tests assert the user-facing contract on the two the user explicitly named —
# long-term memory and interests — for both an automated run and a direct one.
# (Journal/psyche share the exact same single computation, so they are gated
# identically by construction.)


def _setup_response_node_patches(stack):
    """Patch response_node's heavy collaborators so the node runs end-to-end to
    its post-response extraction blocks without any LLM / DB / embedding calls.

    Returns the memory + interest extraction-entry-point mocks so tests can
    assert whether each was scheduled.
    """
    # LLM synthesis chain -> deterministic AIMessage (mirrors the tests above).
    mock_get_prompt = stack.enter_context(
        patch("src.domains.agents.nodes.response_node.get_response_prompt")
    )
    mock_get_llm = stack.enter_context(patch("src.domains.agents.nodes.response_node.get_llm"))
    mock_cpt = stack.enter_context(
        patch("src.domains.agents.nodes.response_node.ChatPromptTemplate")
    )
    mock_chain = AsyncMock()
    mock_chain.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))
    mock_prompt_obj = Mock()
    mock_prompt_obj.__or__ = Mock(return_value=mock_chain)
    mock_cpt.from_messages.return_value = mock_prompt_obj
    mock_get_prompt.return_value = "system"
    mock_get_llm.return_value = Mock()

    # Background scheduling -> no-op (prevents real asyncio task creation).
    stack.enter_context(patch("src.domains.agents.nodes.response_node.safe_fire_and_forget"))
    # Memory injection -> avoid semantic-memory store / DB access.
    stack.enter_context(
        patch(
            "src.domains.agents.nodes.response_node.build_psychological_profile",
            AsyncMock(return_value=("", Mock(value="neutral"), [])),
        )
    )
    # Embedding + triviality -> deterministic, no embedding model call.
    stack.enter_context(
        patch(
            "src.infrastructure.llm.user_message_embedding.get_or_compute_embedding",
            AsyncMock(return_value=None),
        )
    )
    stack.enter_context(
        patch(
            "src.infrastructure.llm.user_message_embedding.is_trivial_message",
            Mock(return_value=False),
        )
    )

    # new_callable=Mock forces SYNC mocks: the extractors are `async def`, so the
    # default AsyncMock would create a coroutine on each call that the (mocked,
    # no-op) safe_fire_and_forget never awaits — a spurious "never awaited"
    # warning. We only need to know whether each was *called*, not awaited.
    return {
        "memory": stack.enter_context(
            patch(
                "src.domains.agents.nodes.response_node.extract_memories_background",
                new_callable=Mock,
            )
        ),
        "interest": stack.enter_context(
            patch(
                "src.domains.agents.nodes.response_node.extract_interests_background",
                new_callable=Mock,
            )
        ),
        # journal + psyche are lazily imported inside response_node — patch at source.
        "journal": stack.enter_context(
            patch(
                "src.domains.journals.extraction_service.extract_journal_entry_background",
                new_callable=Mock,
            )
        ),
        "psyche": stack.enter_context(
            patch(
                "src.domains.psyche.service.psyche_post_response_background",
                new_callable=Mock,
            )
        ),
    }


@pytest.mark.asyncio
async def test_response_node_skips_extraction_for_automated_source():
    """Automated runs (is_automated_source=True) must NOT feed long-term memory or
    interests — even when the user has memory enabled (the scheduled-action case)."""
    import uuid
    from contextlib import ExitStack

    from src.core.field_names import FIELD_IS_AUTOMATED_SOURCE

    state = MessagesState(
        messages=[HumanMessage(content="Je m'appelle Jean et j'adore le jazz et la cuisine.")],
        agent_results={},
        metadata={"user_id": "test-user"},
    )
    config = {
        "metadata": {"run_id": "test-run"},
        "configurable": {
            "langgraph_user_id": str(uuid.uuid4()),
            "user_memory_enabled": True,
            FIELD_IS_AUTOMATED_SOURCE: True,
        },
    }

    with ExitStack() as stack:
        mocks = _setup_response_node_patches(stack)
        await response_node(state, config)

    # All FOUR post-response extractions are gated by the single _is_automated_source
    # flag (checked first in each block, before the per-subsystem enable check).
    mocks["memory"].assert_not_called()
    mocks["interest"].assert_not_called()
    mocks["journal"].assert_not_called()
    mocks["psyche"].assert_not_called()


@pytest.mark.asyncio
async def test_response_node_schedules_extraction_for_direct_user():
    """Direct user inputs (flag absent -> default False) DO feed memory and interests."""
    import uuid
    from contextlib import ExitStack

    state = MessagesState(
        messages=[HumanMessage(content="Je m'appelle Jean et j'adore le jazz et la cuisine.")],
        agent_results={},
        metadata={"user_id": "test-user"},
    )
    config = {
        "metadata": {"run_id": "test-run"},
        "configurable": {
            "langgraph_user_id": str(uuid.uuid4()),
            "user_memory_enabled": True,
            # FIELD_IS_AUTOMATED_SOURCE intentionally absent -> default False (direct user).
        },
    }

    with ExitStack() as stack:
        mocks = _setup_response_node_patches(stack)
        await response_node(state, config)

    mocks["memory"].assert_called_once()
    mocks["interest"].assert_called_once()
