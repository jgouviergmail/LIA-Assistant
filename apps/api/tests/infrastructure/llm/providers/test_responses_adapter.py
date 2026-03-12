"""
Tests for ResponsesLLM adapter.

Tests the OpenAI Responses API adapter including:
- Model eligibility checking
- Streaming (ChatGenerationChunk vs ChatGeneration - the bug that caused TypeError)
- Fallback to Chat Completions
- with_structured_output delegation
"""

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGenerationChunk

from src.infrastructure.llm.providers.responses_adapter import (
    ResponsesLLM,
    is_responses_api_eligible,
)


class TestIsResponsesApiEligible:
    """Tests for model eligibility checking."""

    def test_eligible_gpt41_mini(self):
        """GPT-4.1-mini should be eligible."""
        assert is_responses_api_eligible("gpt-4.1-mini") is True

    def test_eligible_gpt41(self):
        """GPT-4.1 should be eligible."""
        assert is_responses_api_eligible("gpt-4.1") is True

    def test_eligible_gpt5(self):
        """GPT-5 should be eligible."""
        assert is_responses_api_eligible("gpt-5") is True

    def test_eligible_o_series(self):
        """O-series models should be eligible."""
        assert is_responses_api_eligible("o1") is True
        assert is_responses_api_eligible("o3-mini") is True
        assert is_responses_api_eligible("o4-mini") is True

    def test_ineligible_gpt4(self):
        """GPT-4 (without .1) should NOT be eligible."""
        assert is_responses_api_eligible("gpt-4") is False

    def test_ineligible_gpt4_turbo(self):
        """GPT-4-turbo should NOT be eligible."""
        assert is_responses_api_eligible("gpt-4-turbo") is False

    def test_ineligible_gpt35(self):
        """GPT-3.5 should NOT be eligible."""
        assert is_responses_api_eligible("gpt-3.5-turbo") is False

    def test_case_insensitive(self):
        """Model check should be case-insensitive."""
        assert is_responses_api_eligible("GPT-4.1-MINI") is True
        assert is_responses_api_eligible("Gpt-4.1-Mini") is True

    def test_versioned_model(self):
        """Versioned models should be eligible if base is eligible."""
        assert is_responses_api_eligible("gpt-4.1-mini-2025-04-14") is True
        assert is_responses_api_eligible("gpt-4.1-2025-04-14") is True


class TestResponsesLLMStream:
    """
    Tests for ResponsesLLM._stream() method.

    CRITICAL: This tests the bug that caused TypeError in production.
    _stream() MUST return ChatGenerationChunk, not ChatGeneration.
    """

    @patch("src.infrastructure.llm.providers.responses_adapter.OpenAI")
    def test_stream_returns_chat_generation_chunk(self, mock_openai_class):
        """
        _stream() must return ChatGenerationChunk for LangChain compatibility.

        This is the root cause of the TypeError:
        'unsupported operand type(s) for +=: 'ChatGeneration' and 'list''
        """
        # Setup mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Mock Chat Completions streaming response (fallback path for non-eligible models)
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Hello"
        mock_client.chat.completions.create.return_value = iter([mock_chunk])

        # Create LLM with non-eligible model to test fallback streaming
        llm = ResponsesLLM(
            model="gpt-4-turbo",  # Not eligible for Responses API
            api_key="test-key",
        )

        messages = [HumanMessage(content="Hi")]

        # Get stream results
        chunks = list(llm._stream(messages))

        # CRITICAL ASSERTION: Must be ChatGenerationChunk, not ChatGeneration
        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, ChatGenerationChunk), (
                f"Expected ChatGenerationChunk, got {type(chunk).__name__}. "
                "This causes TypeError when LangChain tries to aggregate chunks with +="
            )

    @patch("src.infrastructure.llm.providers.responses_adapter.OpenAI")
    def test_stream_responses_api_returns_chunks(self, mock_openai_class):
        """
        Streaming must return ChatGenerationChunk for eligible models.

        NOTE: Currently streaming always uses Chat Completions fallback
        while we investigate emoji display issues with Responses API.
        This test mocks Chat Completions which is the current path.
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Mock Chat Completions streaming response (current fallback path)
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Hello"
        mock_chunk.usage = None  # No usage on content chunks
        mock_client.chat.completions.create.return_value = iter([mock_chunk])

        # Create LLM with eligible model
        llm = ResponsesLLM(
            model="gpt-4.1-mini",  # Eligible for Responses API
            api_key="test-key",
        )

        messages = [HumanMessage(content="Hi")]
        chunks = list(llm._stream(messages))

        # Should have at least one chunk
        assert len(chunks) >= 1
        for chunk in chunks:
            assert isinstance(
                chunk, ChatGenerationChunk
            ), f"Streaming returned {type(chunk).__name__} instead of ChatGenerationChunk"

    @patch("src.infrastructure.llm.providers.responses_adapter.OpenAI")
    def test_stream_fallback_on_error(self, mock_openai_class):
        """
        When Responses API fails, should fallback to Chat Completions.
        """
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Make Responses API fail
        mock_client.responses.create.side_effect = Exception("API error")

        # Setup Chat Completions fallback
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Fallback"
        mock_client.chat.completions.create.return_value = iter([mock_chunk])

        llm = ResponsesLLM(
            model="gpt-4.1-mini",
            api_key="test-key",
            fallback_enabled=True,
        )

        messages = [HumanMessage(content="Hi")]
        chunks = list(llm._stream(messages))

        # Should have fallback response
        assert len(chunks) > 0
        assert isinstance(chunks[0], ChatGenerationChunk)

        # Chat Completions should have been called as fallback
        mock_client.chat.completions.create.assert_called_once()


class TestResponsesLLMGenerate:
    """Tests for ResponsesLLM._generate() method."""

    @patch("src.infrastructure.llm.providers.responses_adapter.OpenAI")
    def test_generate_non_eligible_uses_chat_completions(self, mock_openai_class):
        """Non-eligible models should use Chat Completions directly."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Setup response
        mock_response = MagicMock()
        mock_response.id = "chatcmpl-123"
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_client.chat.completions.create.return_value = mock_response

        llm = ResponsesLLM(
            model="gpt-4-turbo",
            api_key="test-key",
        )

        messages = [HumanMessage(content="Hi")]
        result = llm._generate(messages)

        assert len(result.generations) == 1
        assert result.generations[0].message.content == "Hello!"

        # Chat Completions should have been called (not Responses API)
        mock_client.chat.completions.create.assert_called_once()
        mock_client.responses.create.assert_not_called()


class TestResponsesLLMWithStructuredOutput:
    """Tests for with_structured_output() using native Responses API."""

    @patch("src.infrastructure.llm.providers.responses_adapter.OpenAI")
    def test_with_structured_output_returns_runnable(self, mock_openai_class):
        """with_structured_output should return a _StructuredResponsesRunnable."""
        from pydantic import BaseModel

        from src.infrastructure.llm.providers.responses_adapter import (
            _StructuredResponsesRunnable,
        )

        class TestSchema(BaseModel):
            name: str
            value: int

        llm = ResponsesLLM(
            model="gpt-4.1-mini",
            api_key="test-key",
        )

        result = llm.with_structured_output(TestSchema)

        # Should return native runnable, not delegate to ChatOpenAI
        assert isinstance(result, _StructuredResponsesRunnable)
        assert result.schema == TestSchema
        assert result.strict is True

    @patch("src.infrastructure.llm.providers.responses_adapter.OpenAI")
    def test_structured_output_uses_responses_api(self, mock_openai_class):
        """Structured output should call Responses API with text.format."""
        from pydantic import BaseModel

        class TestSchema(BaseModel):
            name: str
            value: int

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Mock Responses API response
        mock_response = MagicMock()
        mock_response.id = "resp_123"
        mock_response.output_text = '{"name": "test", "value": 42}'
        mock_client.responses.create.return_value = mock_response

        llm = ResponsesLLM(
            model="gpt-4.1-mini",
            api_key="test-key",
        )

        structured = llm.with_structured_output(TestSchema)
        result = structured.invoke([HumanMessage(content="Get data")])

        # Should call Responses API
        mock_client.responses.create.assert_called_once()

        # Check text.format was passed
        call_kwargs = mock_client.responses.create.call_args[1]
        assert "text" in call_kwargs
        assert call_kwargs["text"]["format"]["type"] == "json_schema"
        assert call_kwargs["text"]["format"]["name"] == "TestSchema"
        assert call_kwargs["text"]["format"]["strict"] is True

        # Should return parsed Pydantic model
        assert isinstance(result, TestSchema)
        assert result.name == "test"
        assert result.value == 42

    @patch("src.infrastructure.llm.providers.responses_adapter.OpenAI")
    def test_structured_output_include_raw(self, mock_openai_class):
        """include_raw should return dict with raw and parsed."""
        from pydantic import BaseModel

        class TestSchema(BaseModel):
            result: str

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.id = "resp_456"
        mock_response.output_text = '{"result": "hello"}'
        mock_client.responses.create.return_value = mock_response

        llm = ResponsesLLM(
            model="gpt-4.1-mini",
            api_key="test-key",
        )

        structured = llm.with_structured_output(TestSchema, include_raw=True)
        result = structured.invoke([HumanMessage(content="Test")])

        assert isinstance(result, dict)
        assert "raw" in result
        assert "parsed" in result
        assert "response_id" in result
        assert result["raw"] == '{"result": "hello"}'
        assert isinstance(result["parsed"], TestSchema)
        assert result["response_id"] == "resp_456"

    @patch("src.infrastructure.llm.providers.responses_adapter.OpenAI")
    @patch("langchain_openai.ChatOpenAI")
    def test_structured_output_fallback_on_error(self, mock_chat_openai_class, mock_openai_class):
        """Should fallback to ChatOpenAI on Responses API error."""
        from pydantic import BaseModel

        class TestSchema(BaseModel):
            data: str

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Make Responses API fail
        mock_client.responses.create.side_effect = Exception("API error")

        # Setup ChatOpenAI fallback
        mock_chat_llm = MagicMock()
        mock_chat_openai_class.return_value = mock_chat_llm
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = TestSchema(data="fallback")
        mock_chat_llm.with_structured_output.return_value = mock_structured

        llm = ResponsesLLM(
            model="gpt-4.1-mini",
            api_key="test-key",
            fallback_enabled=True,
        )

        structured = llm.with_structured_output(TestSchema)
        result = structured.invoke([HumanMessage(content="Test")])

        # Should have fallen back to ChatOpenAI
        mock_chat_openai_class.assert_called_once()
        assert result.data == "fallback"

    @patch("src.infrastructure.llm.providers.responses_adapter.OpenAI")
    def test_structured_output_strict_schema(self, mock_openai_class):
        """Strict mode should add additionalProperties: false."""
        from pydantic import BaseModel

        class NestedSchema(BaseModel):
            inner: str

        class TestSchema(BaseModel):
            outer: NestedSchema
            items: list[str]

        llm = ResponsesLLM(
            model="gpt-4.1-mini",
            api_key="test-key",
        )

        runnable = llm.with_structured_output(TestSchema, strict=True)

        # Get the processed schema
        json_schema = TestSchema.model_json_schema()
        processed = runnable._ensure_strict_schema(json_schema)

        # Root should have additionalProperties: false
        assert processed.get("additionalProperties") is False

        # Nested objects in $defs should also have it
        if "$defs" in processed:
            for def_schema in processed["$defs"].values():
                if def_schema.get("type") == "object":
                    assert def_schema.get("additionalProperties") is False

    @patch("src.infrastructure.llm.providers.responses_adapter.OpenAI")
    def test_structured_output_ref_no_sibling_keywords(self, mock_openai_class):
        """$ref properties must not have sibling keywords like description.

        OpenAI strict mode error:
        "Invalid schema: context=('properties', 'issue_type'), $ref cannot have keywords {'description'}"
        """
        from enum import Enum

        from pydantic import BaseModel, Field

        class IssueType(str, Enum):
            """Issue type enum that creates a $ref in JSON schema."""

            MISSING_INFO = "missing_info"
            AMBIGUOUS = "ambiguous"

        class ValidationSchema(BaseModel):
            """Schema with $ref + description pattern that causes OpenAI errors."""

            issue_type: IssueType = Field(description="Type of validation issue")
            message: str = Field(description="Issue message")

        llm = ResponsesLLM(
            model="gpt-4.1-mini",
            api_key="test-key",
        )

        runnable = llm.with_structured_output(ValidationSchema, strict=True)

        # Get the processed schema
        json_schema = ValidationSchema.model_json_schema()
        processed = runnable._ensure_strict_schema(json_schema)

        # Check that properties with $ref don't have description or other siblings
        for prop_name, prop_schema in processed.get("properties", {}).items():
            if "$ref" in prop_schema:
                # CRITICAL: $ref must be the ONLY key
                assert set(prop_schema.keys()) == {"$ref"}, (
                    f"Property '{prop_name}' has $ref with sibling keywords: "
                    f"{set(prop_schema.keys()) - {'$ref'}}"
                )


class TestResponsesLLMMessageConversion:
    """Tests for message format conversion."""

    @patch("src.infrastructure.llm.providers.responses_adapter.OpenAI")
    def test_convert_messages_with_system(self, mock_openai_class):
        """System messages should become instructions."""
        llm = ResponsesLLM(
            model="gpt-4.1-mini",
            api_key="test-key",
        )

        messages = [
            SystemMessage(content="You are helpful"),
            HumanMessage(content="Hi"),
        ]

        input_items, instructions = llm._convert_messages_to_input(messages)

        assert instructions == "You are helpful"
        assert len(input_items) == 1
        assert input_items[0]["role"] == "user"
        assert input_items[0]["content"] == "Hi"

    @patch("src.infrastructure.llm.providers.responses_adapter.OpenAI")
    def test_convert_messages_multi_turn(self, mock_openai_class):
        """Multi-turn conversation should be converted correctly."""
        llm = ResponsesLLM(
            model="gpt-4.1-mini",
            api_key="test-key",
        )

        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
            HumanMessage(content="How are you?"),
        ]

        input_items, instructions = llm._convert_messages_to_input(messages)

        assert instructions is None
        assert len(input_items) == 3
        assert input_items[0]["role"] == "user"
        assert input_items[1]["role"] == "assistant"
        assert input_items[2]["role"] == "user"
