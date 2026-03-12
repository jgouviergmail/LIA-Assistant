"""
Unit tests for Generic Structured Output Helper (Multi-Provider Support).

Tests the get_structured_output() helper function that provides unified
interface for obtaining Pydantic-typed outputs from any LLM provider,
automatically handling provider-specific capabilities.

Coverage:
    - Native structured output path (OpenAI, Anthropic, DeepSeek)
    - JSON mode fallback path (Ollama, Perplexity)
    - Error handling and validation
    - Provider capability detection
    - Retry mechanisms
    - Edge cases (invalid JSON, schema mismatches, etc.)

Test Architecture:
    - Uses pytest fixtures for mock LLMs
    - Mocks LangChain BaseChatModel for isolated testing
    - Validates Pydantic schema parsing
    - Tests both sync and async paths
"""

import json
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.infrastructure.llm.structured_output import (
    StructuredOutputError,
    get_structured_output,
    get_structured_output_with_retry,
)

# ============================================================================
# Test Pydantic Schemas
# ============================================================================


class SimpleDecision(BaseModel):
    """Simple test schema for basic validation."""

    reasoning: str = Field(description="Explanation of the decision")
    action: str = Field(description="Action to take")
    confidence: float = Field(description="Confidence score 0-1", ge=0, le=1)


class ComplexPlan(BaseModel):
    """Complex nested schema for advanced validation."""

    title: str
    steps: list[dict[str, Any]]
    metadata: dict[str, Any]
    is_complete: bool = False


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def simple_decision_json() -> str:
    """Valid JSON matching SimpleDecision schema."""
    return json.dumps(
        {"reasoning": "User requested search", "action": "search_contacts", "confidence": 0.9}
    )


@pytest.fixture
def complex_plan_json() -> str:
    """Valid JSON matching ComplexPlan schema."""
    return json.dumps(
        {
            "title": "Multi-step plan",
            "steps": [{"step_id": "1", "tool": "search"}, {"step_id": "2", "tool": "filter"}],
            "metadata": {"user_id": "123", "session_id": "abc"},
            "is_complete": False,
        }
    )


@pytest.fixture
def invalid_json() -> str:
    """Invalid JSON that cannot be parsed."""
    return '{"reasoning": "incomplete", "action": '


@pytest.fixture
def mismatched_schema_json() -> str:
    """Valid JSON but doesn't match SimpleDecision schema (missing required fields)."""
    return json.dumps({"reasoning": "test", "wrong_field": "value"})


@pytest.fixture
def mock_native_llm(simple_decision_json: str) -> Mock:
    """Mock LLM that supports native structured output (.with_structured_output())."""
    llm = Mock()

    # Mock .with_structured_output() to return a structured LLM wrapper
    structured_llm = AsyncMock()

    # When invoked, return a Pydantic instance directly (native behavior)
    structured_llm.ainvoke.return_value = SimpleDecision(
        reasoning="User requested search", action="search_contacts", confidence=0.9
    )

    llm.with_structured_output.return_value = structured_llm

    return llm


@pytest.fixture
def mock_json_mode_llm(simple_decision_json: str) -> AsyncMock:
    """Mock LLM for JSON mode fallback (Ollama, Perplexity)."""
    # For JSON mode fallback, we call llm.ainvoke() directly (no .bind())
    llm = AsyncMock()

    # When invoked, return AIMessage with JSON content
    llm.ainvoke.return_value = AIMessage(content=simple_decision_json)

    return llm


# ============================================================================
# Test Native Structured Output (OpenAI, Anthropic, DeepSeek)
# ============================================================================


@pytest.mark.asyncio
async def test_native_structured_output_openai(mock_native_llm: Mock):
    """Test native structured output with OpenAI provider."""
    messages = [HumanMessage(content="What should I do?")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"openai": True}

        result = await get_structured_output(
            llm=mock_native_llm,
            messages=messages,
            schema=SimpleDecision,
            provider="openai",
        )

    # Verify result is a Pydantic instance
    assert isinstance(result, SimpleDecision)
    assert result.reasoning == "User requested search"
    assert result.action == "search_contacts"
    assert result.confidence == 0.9

    # Verify .with_structured_output() was called with schema
    # Note: Implementation may pass additional kwargs like method='function_calling'
    mock_native_llm.with_structured_output.assert_called_once()
    call_args = mock_native_llm.with_structured_output.call_args
    assert call_args[0][0] == SimpleDecision  # First positional arg is schema


@pytest.mark.asyncio
async def test_native_structured_output_anthropic(mock_native_llm: Mock):
    """Test native structured output with Anthropic provider."""
    messages = [HumanMessage(content="Analyze this request")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"anthropic": True}

        result = await get_structured_output(
            llm=mock_native_llm,
            messages=messages,
            schema=SimpleDecision,
            provider="anthropic",
        )

    assert isinstance(result, SimpleDecision)
    mock_native_llm.with_structured_output.assert_called_once()


@pytest.mark.asyncio
async def test_native_structured_output_deepseek(mock_native_llm: Mock):
    """Test native structured output with DeepSeek provider."""
    messages = [SystemMessage(content="You are a router"), HumanMessage(content="Route this")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"deepseek": True}

        result = await get_structured_output(
            llm=mock_native_llm,
            messages=messages,
            schema=SimpleDecision,
            provider="deepseek",
        )

    assert isinstance(result, SimpleDecision)


# ============================================================================
# Test JSON Mode Fallback (Ollama, Perplexity)
# ============================================================================


@pytest.mark.asyncio
async def test_json_mode_fallback_ollama(mock_json_mode_llm: AsyncMock, simple_decision_json: str):
    """Test JSON mode fallback with Ollama provider."""
    messages = [HumanMessage(content="What should I do?")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"ollama": False}

        result = await get_structured_output(
            llm=mock_json_mode_llm,
            messages=messages,
            schema=SimpleDecision,
            provider="ollama",
        )

    # Verify result is a valid Pydantic instance
    assert isinstance(result, SimpleDecision)
    assert result.reasoning == "User requested search"
    assert result.action == "search_contacts"
    assert result.confidence == 0.9

    # Verify .ainvoke() was called directly (no .bind())
    mock_json_mode_llm.ainvoke.assert_called_once()
    # Verify we passed augmented messages (SystemMessage + original message)
    call_args = mock_json_mode_llm.ainvoke.call_args[0][0]
    assert len(call_args) == 2  # SystemMessage with JSON instructions + original HumanMessage
    assert isinstance(call_args[0], SystemMessage)
    assert "JSON" in call_args[0].content


@pytest.mark.asyncio
async def test_json_mode_fallback_perplexity(
    mock_json_mode_llm: AsyncMock, simple_decision_json: str
):
    """Test JSON mode fallback with Perplexity provider."""
    messages = [HumanMessage(content="Search for information")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"perplexity": False}

        result = await get_structured_output(
            llm=mock_json_mode_llm,
            messages=messages,
            schema=SimpleDecision,
            provider="perplexity",
        )

    assert isinstance(result, SimpleDecision)
    mock_json_mode_llm.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_json_mode_augments_prompt(mock_json_mode_llm: AsyncMock, simple_decision_json: str):
    """Verify that JSON mode adds schema instructions to the prompt."""
    messages = [HumanMessage(content="Test query")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"ollama": False}

        await get_structured_output(
            llm=mock_json_mode_llm,
            messages=messages,
            schema=SimpleDecision,
            provider="ollama",
        )

    # Get the messages passed to ainvoke (called directly, no .bind())
    call_args = mock_json_mode_llm.ainvoke.call_args
    augmented_messages = call_args[0][0]

    # Verify that a SystemMessage with JSON instructions was prepended
    assert len(augmented_messages) == 2  # SystemMessage + original HumanMessage
    assert isinstance(augmented_messages[0], SystemMessage)
    assert "JSON" in augmented_messages[0].content
    assert "SimpleDecision" in augmented_messages[0].content
    assert isinstance(augmented_messages[1], HumanMessage)
    assert augmented_messages[1].content == "Test query"


# ============================================================================
# Test Complex Schemas
# ============================================================================


@pytest.mark.asyncio
async def test_complex_nested_schema(complex_plan_json: str):
    """Test structured output with complex nested Pydantic schema."""
    # Mock LLM for JSON mode fallback (no .bind())
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content=complex_plan_json)

    messages = [HumanMessage(content="Create a plan")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"ollama": False}

        result = await get_structured_output(
            llm=mock_llm, messages=messages, schema=ComplexPlan, provider="ollama"
        )

    assert isinstance(result, ComplexPlan)
    assert result.title == "Multi-step plan"
    assert len(result.steps) == 2
    assert result.steps[0]["step_id"] == "1"
    assert result.metadata["user_id"] == "123"
    assert result.is_complete is False


# ============================================================================
# Test Error Handling
# ============================================================================


@pytest.mark.asyncio
async def test_invalid_json_raises_error(invalid_json: str):
    """Test that invalid JSON raises StructuredOutputError."""
    # Mock LLM for JSON mode fallback
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content=invalid_json)

    messages = [HumanMessage(content="Test")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"ollama": False}

        with pytest.raises(StructuredOutputError) as exc_info:
            await get_structured_output(
                llm=mock_llm, messages=messages, schema=SimpleDecision, provider="ollama"
            )

        # Verify error details
        assert "Failed to parse JSON" in str(exc_info.value)
        assert exc_info.value.provider == "ollama"
        assert exc_info.value.schema_name == "SimpleDecision"
        assert exc_info.value.raw_output == invalid_json


@pytest.mark.asyncio
async def test_schema_mismatch_raises_error(mismatched_schema_json: str):
    """Test that JSON not matching schema raises StructuredOutputError."""
    # Mock LLM for JSON mode fallback
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content=mismatched_schema_json)

    messages = [HumanMessage(content="Test")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"ollama": False}

        with pytest.raises(StructuredOutputError) as exc_info:
            await get_structured_output(
                llm=mock_llm, messages=messages, schema=SimpleDecision, provider="ollama"
            )

        # Verify error mentions Pydantic validation
        assert "Pydantic validation failed" in str(exc_info.value)
        assert exc_info.value.provider == "ollama"


@pytest.mark.asyncio
async def test_native_structured_output_error_handling():
    """Test error handling for native structured output failures."""
    mock_llm = Mock()
    structured_llm = AsyncMock()

    # Simulate LLM returning wrong type (unexpected behavior)
    structured_llm.ainvoke.return_value = {"reasoning": "test", "action": "test", "confidence": 0.5}

    mock_llm.with_structured_output.return_value = structured_llm

    messages = [HumanMessage(content="Test")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"openai": True}

        with pytest.raises(StructuredOutputError) as exc_info:
            await get_structured_output(
                llm=mock_llm, messages=messages, schema=SimpleDecision, provider="openai"
            )

        assert "unexpected type" in str(exc_info.value)


@pytest.mark.asyncio
async def test_native_structured_output_validation_error():
    """Test ValidationError handling in native structured output path.

    This test covers lines 295-302: the ValidationError exception handler
    in _get_native_structured_output(). It simulates a scenario where the
    LLM provider returns data that fails Pydantic validation.
    """
    from pydantic import ValidationError as PydanticValidationError

    mock_llm = Mock()
    structured_llm = AsyncMock()

    # Create a proper ValidationError using Pydantic v2 API
    # Simulate field validation failure (e.g., confidence out of range)
    try:
        SimpleDecision(reasoning="test", action="test", confidence=1.5)  # Invalid: > 1.0
    except PydanticValidationError as validation_error:
        # Use this real validation error for the test
        structured_llm.ainvoke.side_effect = validation_error

    mock_llm.with_structured_output.return_value = structured_llm

    messages = [HumanMessage(content="Test")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"openai": True}

        with pytest.raises(StructuredOutputError) as exc_info:
            await get_structured_output(
                llm=mock_llm,
                messages=messages,
                schema=SimpleDecision,
                provider="openai",
            )

        # Verify error wrapping
        assert "Pydantic validation failed" in str(exc_info.value)
        assert exc_info.value.provider == "openai"
        assert exc_info.value.schema_name == "SimpleDecision"
        assert isinstance(exc_info.value.original_error, PydanticValidationError)


@pytest.mark.asyncio
async def test_native_structured_output_llm_api_error():
    """Test generic exception handling in native structured output path.

    This test covers lines 304-311: the generic Exception handler
    in _get_native_structured_output(). It simulates LLM API failures
    like network errors, rate limits, or service outages.
    """
    mock_llm = Mock()
    structured_llm = AsyncMock()

    # Simulate LLM API error (could be network, rate limit, service outage, etc.)
    api_error = Exception("API rate limit exceeded")
    structured_llm.ainvoke.side_effect = api_error

    mock_llm.with_structured_output.return_value = structured_llm

    messages = [HumanMessage(content="Test")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"anthropic": True}

        with pytest.raises(StructuredOutputError) as exc_info:
            await get_structured_output(
                llm=mock_llm,
                messages=messages,
                schema=SimpleDecision,
                provider="anthropic",
            )

        # Verify error wrapping
        assert "Native structured output failed" in str(exc_info.value)
        assert exc_info.value.provider == "anthropic"
        assert exc_info.value.schema_name == "SimpleDecision"
        assert exc_info.value.original_error is api_error


@pytest.mark.asyncio
async def test_json_mode_reraises_structured_output_error(invalid_json: str):
    """Test that StructuredOutputError is re-raised correctly in JSON mode.

    This test covers lines 424-426: the StructuredOutputError re-raise path
    in _get_json_mode_fallback(). While this is already implicitly tested by
    other error tests, this explicit test ensures the re-raise behavior is
    clearly documented and maintained.
    """
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content=invalid_json)

    messages = [HumanMessage(content="Test")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"ollama": False}

        with pytest.raises(StructuredOutputError) as exc_info:
            await get_structured_output(
                llm=mock_llm,
                messages=messages,
                schema=SimpleDecision,
                provider="ollama",
            )

        # Verify that the original StructuredOutputError was re-raised
        # (not wrapped in another exception)
        assert "Failed to parse JSON" in str(exc_info.value)
        assert exc_info.value.provider == "ollama"
        assert exc_info.value.schema_name == "SimpleDecision"
        assert exc_info.value.raw_output == invalid_json
        # Verify it's a StructuredOutputError with original JSONDecodeError
        assert isinstance(exc_info.value.original_error, json.JSONDecodeError)


# ============================================================================
# Test Retry Mechanism
# ============================================================================


@pytest.mark.asyncio
async def test_retry_success_after_transient_failure(simple_decision_json: str):
    """Test that retry mechanism succeeds after transient failures."""
    # Mock LLM for JSON mode fallback (no .bind())
    mock_llm = AsyncMock()

    # First call fails, second call succeeds
    mock_llm.ainvoke.side_effect = [
        Exception("Transient network error"),
        AIMessage(content=simple_decision_json),
    ]

    messages = [HumanMessage(content="Test")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"ollama": False}

        result = await get_structured_output_with_retry(
            llm=mock_llm, messages=messages, schema=SimpleDecision, provider="ollama", max_retries=3
        )

    # Should succeed on second attempt
    assert isinstance(result, SimpleDecision)
    assert mock_llm.ainvoke.call_count == 2


@pytest.mark.asyncio
async def test_retry_exhausted_raises_final_error():
    """Test that all retries exhausted raises the final error."""
    # Mock LLM for JSON mode fallback (no .bind())
    mock_llm = AsyncMock()

    # All calls fail
    mock_llm.ainvoke.side_effect = Exception("Persistent error")

    messages = [HumanMessage(content="Test")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"ollama": False}

        with pytest.raises(StructuredOutputError):
            await get_structured_output_with_retry(
                llm=mock_llm,
                messages=messages,
                schema=SimpleDecision,
                provider="ollama",
                max_retries=3,
            )

    # Should have tried 3 times
    assert mock_llm.ainvoke.call_count == 3


# ============================================================================
# Test Provider Detection
# ============================================================================


@pytest.mark.asyncio
async def test_unknown_provider_defaults_to_json_mode(simple_decision_json: str):
    """Test that unknown providers default to JSON mode fallback."""
    # Mock LLM for JSON mode fallback (no .bind())
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content=simple_decision_json)

    messages = [HumanMessage(content="Test")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        # Provider not in the dict defaults to False
        mock_settings.provider_supports_structured_output = {}

        result = await get_structured_output(
            llm=mock_llm, messages=messages, schema=SimpleDecision, provider="unknown_provider"
        )

    # Should use JSON mode fallback
    assert isinstance(result, SimpleDecision)
    mock_llm.ainvoke.assert_called_once()


# ============================================================================
# Test invoke_kwargs Propagation
# ============================================================================


@pytest.mark.asyncio
async def test_invoke_kwargs_passed_to_native_llm(mock_native_llm: Mock):
    """Test that additional invoke kwargs are passed to native structured output."""
    messages = [HumanMessage(content="Test")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"openai": True}

        await get_structured_output(
            llm=mock_native_llm,
            messages=messages,
            schema=SimpleDecision,
            provider="openai",
            timeout=30,  # Extra kwarg
            temperature=0.5,  # Extra kwarg
        )

    # Verify kwargs were passed to ainvoke
    structured_llm = mock_native_llm.with_structured_output.return_value
    call_kwargs = structured_llm.ainvoke.call_args[1]
    assert call_kwargs["timeout"] == 30
    assert call_kwargs["temperature"] == 0.5


@pytest.mark.asyncio
async def test_invoke_kwargs_passed_to_json_mode(
    mock_json_mode_llm: AsyncMock, simple_decision_json: str
):
    """Test that additional invoke kwargs are passed to JSON mode fallback."""
    messages = [HumanMessage(content="Test")]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"ollama": False}

        await get_structured_output(
            llm=mock_json_mode_llm,
            messages=messages,
            schema=SimpleDecision,
            provider="ollama",
            max_tokens=2000,  # Extra kwarg
        )

    # Verify kwargs were passed to ainvoke (called directly, no .bind())
    call_kwargs = mock_json_mode_llm.ainvoke.call_args[1]
    assert call_kwargs["max_tokens"] == 2000


# ============================================================================
# Test ChatPromptTemplate Support (Edge Cases)
# ============================================================================


@pytest.mark.asyncio
async def test_native_structured_output_with_chat_prompt_template():
    """Test native structured output with ChatPromptTemplate.

    This test covers lines 191-196 (specifically line 194): the ChatPromptTemplate
    message extraction logic in get_structured_output(). It verifies that when
    a ChatPromptTemplate is passed directly (not invoked), the function correctly
    extracts template.messages.

    Note: The function expects an UN-invoked ChatPromptTemplate, not a ChatPromptValue.
    """
    from langchain_core.prompts import ChatPromptTemplate

    mock_llm = Mock()
    structured_llm = AsyncMock()
    structured_llm.ainvoke.return_value = SimpleDecision(
        reasoning="Template processed successfully",
        action="route_to_search",
        confidence=0.92,
    )
    mock_llm.with_structured_output.return_value = structured_llm

    # Create ChatPromptTemplate (do NOT invoke it)
    # The function will access template.messages directly
    template = ChatPromptTemplate.from_messages(
        [
            ("system", "You are a routing assistant"),
            ("human", "Route this query"),
        ]
    )

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"openai": True}

        result = await get_structured_output(
            llm=mock_llm,
            messages=template,  # Pass template directly (NOT invoked)
            schema=SimpleDecision,
            provider="openai",
        )

    # Verify result
    assert isinstance(result, SimpleDecision)
    assert result.reasoning == "Template processed successfully"
    assert result.action == "route_to_search"

    # Verify that structured_llm.ainvoke was called with template.messages
    structured_llm.ainvoke.assert_called_once()
    call_args = structured_llm.ainvoke.call_args
    messages_passed = call_args[0][0]

    # Verify messages were extracted from template.messages
    # Note: template.messages contains MessagePromptTemplate objects, not BaseMessage
    # The function passes them as-is to the LLM
    assert isinstance(messages_passed, list)
    assert len(messages_passed) == 2  # system + human messages from template


@pytest.mark.asyncio
async def test_json_mode_fallback_with_chat_prompt_template(simple_decision_json: str):
    """Test JSON mode fallback with ChatPromptTemplate.

    This test also covers lines 191-196 (specifically line 194), but for the
    JSON mode fallback path. It ensures that ChatPromptTemplate message extraction
    works correctly for providers that don't support native structured output.
    """
    from langchain_core.prompts import ChatPromptTemplate

    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = AIMessage(content=simple_decision_json)

    # Create ChatPromptTemplate (do NOT invoke it)
    template = ChatPromptTemplate.from_messages(
        [
            ("system", "You are a router"),
            ("human", "Search for contacts"),
        ]
    )

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"ollama": False}

        result = await get_structured_output(
            llm=mock_llm,
            messages=template,  # Pass template directly (NOT invoked)
            schema=SimpleDecision,
            provider="ollama",
        )

    # Verify result
    assert isinstance(result, SimpleDecision)
    assert result.reasoning == "User requested search"
    assert result.action == "search_contacts"

    # Verify llm.ainvoke was called
    mock_llm.ainvoke.assert_called_once()
    call_args = mock_llm.ainvoke.call_args
    messages_passed = call_args[0][0]

    # Verify messages include augmented JSON instructions + template messages
    # Should be: [SystemMessage (JSON instructions), *template.messages]
    assert isinstance(messages_passed, list)
    assert len(messages_passed) == 3  # JSON instruction + 2 template messages
    assert isinstance(messages_passed[0], SystemMessage)  # JSON instructions (prepended)
    assert "JSON" in messages_passed[0].content
    # Note: messages_passed[1] and [2] are MessagePromptTemplate from template.messages


# ============================================================================
# Integration-Style Tests
# ============================================================================


@pytest.mark.asyncio
async def test_full_flow_native_structured_output():
    """Integration test: Full flow with native structured output (simulated)."""

    # Create a more realistic mock that simulates OpenAI's behavior
    class MockStructuredLLM:
        async def ainvoke(self, messages: list[BaseMessage], **kwargs: Any) -> SimpleDecision:
            # Simulate LLM processing and returning Pydantic instance
            return SimpleDecision(
                reasoning="Analyzed request and determined intent",
                action="execute_search",
                confidence=0.95,
            )

    mock_llm = Mock()
    mock_llm.with_structured_output.return_value = MockStructuredLLM()

    messages = [
        SystemMessage(content="You are a routing assistant"),
        HumanMessage(content="Find my contact John Doe"),
    ]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"openai": True}

        result = await get_structured_output(
            llm=mock_llm, messages=messages, schema=SimpleDecision, provider="openai"
        )

    assert result.reasoning == "Analyzed request and determined intent"
    assert result.action == "execute_search"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_full_flow_json_mode_fallback():
    """Integration test: Full flow with JSON mode fallback (simulated)."""

    class MockJSONLLM:
        async def ainvoke(self, messages: list[BaseMessage], **kwargs: Any) -> AIMessage:
            # Simulate Ollama returning valid JSON
            json_output = json.dumps(
                {
                    "reasoning": "Processed query with JSON mode",
                    "action": "search_database",
                    "confidence": 0.88,
                }
            )
            return AIMessage(content=json_output)

    # Use the mock class directly (no .bind() for JSON mode fallback)
    mock_llm = MockJSONLLM()

    messages = [
        SystemMessage(content="You are a routing assistant"),
        HumanMessage(content="Search for contacts named Alice"),
    ]

    with patch("src.infrastructure.llm.structured_output.settings") as mock_settings:
        mock_settings.provider_supports_structured_output = {"ollama": False}

        result = await get_structured_output(
            llm=mock_llm, messages=messages, schema=SimpleDecision, provider="ollama"
        )

    assert result.reasoning == "Processed query with JSON mode"
    assert result.action == "search_database"
    assert result.confidence == 0.88
