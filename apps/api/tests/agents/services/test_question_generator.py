"""Tests for HITL Question Generator - Multi-Provider Factory Version.

Tests the question generator using the get_llm() factory pattern.
The actual LLM is mocked to test generation logic without API calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.services.hitl.question_generator import HitlQuestionGenerator


@pytest.fixture
def mock_llm():
    """Create a mock LLM instance for testing."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock()
    llm.astream = AsyncMock()
    return llm


@pytest.fixture
def question_generator(mock_llm):
    """Create question generator instance with mocked LLMs."""
    with patch(
        "src.domains.agents.services.hitl.question_generator.get_llm",
        return_value=mock_llm,
    ):
        generator = HitlQuestionGenerator()
        # Both LLMs use the same mock for simplicity
        generator.tool_question_llm = mock_llm
        generator.plan_approval_llm = mock_llm
        return generator


# =============================================================================
# Test: Question Generation
# =============================================================================


@pytest.mark.asyncio
async def test_generate_question_search_contacts(question_generator, mock_llm):
    """Test question generation for search_contacts_tool."""
    # Arrange
    tool_name = "search_contacts_tool"
    tool_args = {"query": "jean", "max_results": 10}
    user_language = "fr"

    # Mock LLM response
    mock_response = MagicMock()
    mock_response.content = (
        "Je vais rechercher les contacts correspondant à 'jean'. Dois-je continuer ?"
    )
    mock_llm.ainvoke.return_value = mock_response

    # Act
    question = await question_generator.generate_confirmation_question(
        tool_name=tool_name,
        tool_args=tool_args,
        user_language=user_language,
    )

    # Assert
    assert question == "Je vais rechercher les contacts correspondant à 'jean'. Dois-je continuer ?"
    mock_llm.ainvoke.assert_called_once()

    # Verify prompt structure
    call_args = mock_llm.ainvoke.call_args[0][0]
    assert isinstance(call_args, list)
    assert len(call_args) == 2
    assert call_args[0]["role"] == "system"
    assert call_args[1]["role"] == "user"
    assert "search_contacts_tool" in call_args[1]["content"]
    assert "jean" in call_args[1]["content"]


@pytest.mark.asyncio
async def test_generate_question_delete_tool(question_generator, mock_llm):
    """Test question generation includes warning for delete operations."""
    # Arrange
    tool_name = "delete_contact_tool"
    tool_args = {"contact_id": "12345"}
    user_language = "fr"

    # Mock LLM response with warning emoji
    mock_response = MagicMock()
    mock_response.content = (
        "🔴 Je m'apprête à supprimer le contact. Cette action est irréversible. Confirmes-tu ?"
    )
    mock_llm.ainvoke.return_value = mock_response

    # Act
    question = await question_generator.generate_confirmation_question(
        tool_name=tool_name,
        tool_args=tool_args,
        user_language=user_language,
    )

    # Assert
    assert "🔴" in question or "⚠️" in question  # Should have warning emoji
    assert "supprimer" in question.lower() or "delete" in question.lower()


@pytest.mark.asyncio
async def test_generate_question_english(question_generator, mock_llm):
    """Test question generation in English."""
    # Arrange
    tool_name = "search_contacts_tool"
    tool_args = {"query": "John"}
    user_language = "en"

    # Mock LLM response in English
    mock_response = MagicMock()
    mock_response.content = "I'm about to search for contacts matching 'John'. Should I proceed?"
    mock_llm.ainvoke.return_value = mock_response

    # Act
    question = await question_generator.generate_confirmation_question(
        tool_name=tool_name,
        tool_args=tool_args,
        user_language=user_language,
    )

    # Assert
    assert question == "I'm about to search for contacts matching 'John'. Should I proceed?"

    # Verify LLM was called (don't check internal prompt format)
    mock_llm.ainvoke.assert_called_once()
