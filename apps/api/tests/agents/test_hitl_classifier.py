"""
Comprehensive tests for HITL Response Classifier.

Tests the HitlResponseClassifier service covering:
- Classification decisions (APPROVE/REJECT/EDIT/AMBIGUOUS)
- Action type extraction (search/send/delete/create/list/get/generic)
- Context formatting and prompt building
- Contextual examples generation
- EDIT demotion logic (missing params and low confidence)
- Result parsing and validation
- Error handling and LLM failures
- Metrics tracking
- Edge cases (empty context, ambiguous responses)

Coverage target: 85%+ for hitl_classifier.py
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import SystemMessage

from src.core.constants import HITL_CLASSIFIER_PROMPT_VERSION_DEFAULT
from src.domains.agents.constants import (
    ACTION_TYPE_CREATE,
    ACTION_TYPE_DELETE,
    ACTION_TYPE_GENERIC,
    ACTION_TYPE_GET,
    ACTION_TYPE_LIST,
    ACTION_TYPE_SEARCH,
    ACTION_TYPE_SEND,
)
from src.domains.agents.services.hitl_classifier import (
    ClassificationResult,
    HitlResponseClassifier,
)

# ============================================================================
# Fixtures
# ============================================================================


# Skip all tests if OPENAI_API_KEY is not set (integration tests that call real LLM)
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY for integration tests with real LLM",
)


@pytest.fixture
def mock_llm():
    """Mock get_llm factory to return mocked LLM."""
    with patch("src.domains.agents.services.hitl_classifier.get_llm") as mock:
        llm_instance = MagicMock()
        llm_instance.ainvoke = AsyncMock()
        mock.return_value = llm_instance
        yield llm_instance


@pytest.fixture
def classifier(mock_llm):
    """HitlResponseClassifier instance with mocked LLM."""
    return HitlResponseClassifier()


@pytest.fixture
def mock_tracker():
    """Mock TrackingContext for token tracking."""
    tracker = MagicMock()
    tracker.get_summary = MagicMock(return_value={"tokens_in": 50, "tokens_out": 100})
    return tracker


# ============================================================================
# Test ClassificationResult Model
# ============================================================================


class TestClassificationResult:
    """Test ClassificationResult Pydantic model."""

    def test_valid_approve_result(self):
        """Test creating valid APPROVE result."""
        result = ClassificationResult(
            decision="APPROVE", confidence=0.95, reasoning="User confirmed with 'oui'"
        )
        assert result.decision == "APPROVE"
        assert result.confidence == 0.95
        assert result.reasoning == "User confirmed with 'oui'"
        assert result.edited_params is None
        assert result.clarification_question is None

    def test_valid_reject_result(self):
        """Test creating valid REJECT result."""
        result = ClassificationResult(
            decision="REJECT", confidence=0.90, reasoning="User said 'non annule'"
        )
        assert result.decision == "REJECT"
        assert result.confidence == 0.90

    def test_valid_edit_result_with_params(self):
        """Test creating valid EDIT result with edited_params."""
        result = ClassificationResult(
            decision="EDIT",
            confidence=0.85,
            reasoning="User corrected query to 'paul'",
            edited_params={"query": "paul"},
        )
        assert result.decision == "EDIT"
        assert result.edited_params == {"query": "paul"}

    def test_valid_ambiguous_result_with_clarification(self):
        """Test creating valid AMBIGUOUS result with clarification question."""
        result = ClassificationResult(
            decision="AMBIGUOUS",
            confidence=0.50,
            reasoning="User response is unclear",
            clarification_question="Peux-tu préciser ?",
        )
        assert result.decision == "AMBIGUOUS"
        assert result.clarification_question == "Peux-tu préciser ?"

    def test_invalid_decision_type(self):
        """Test that invalid decision type raises validation error."""
        with pytest.raises(ValueError):
            ClassificationResult(
                decision="INVALID",
                confidence=0.5,
                reasoning="Test",  # type: ignore
            )

    def test_confidence_validation_range(self):
        """Test confidence score validation (0.0-1.0)."""
        # Valid confidence scores
        ClassificationResult(decision="APPROVE", confidence=0.0, reasoning="Test")
        ClassificationResult(decision="APPROVE", confidence=1.0, reasoning="Test")

        # Invalid confidence scores
        with pytest.raises(ValueError):
            ClassificationResult(decision="APPROVE", confidence=-0.1, reasoning="Test")
        with pytest.raises(ValueError):
            ClassificationResult(decision="APPROVE", confidence=1.5, reasoning="Test")


# ============================================================================
# Test Classifier Initialization
# ============================================================================


class TestClassifierInit:
    """Test HitlResponseClassifier initialization with get_llm factory."""

    def test_init_default_params(self):
        """Test classifier initialization with default parameters."""
        with patch("src.domains.agents.services.hitl_classifier.get_llm") as mock_get_llm:
            mock_get_llm.return_value = MagicMock()
            HitlResponseClassifier()

            # Verify get_llm factory was called with correct llm_type
            mock_get_llm.assert_called_once()
            call_kwargs = mock_get_llm.call_args.kwargs
            assert call_kwargs.get("llm_type") == "hitl_classifier"
            # No config_override when using defaults
            assert call_kwargs.get("config_override") is None

    def test_init_custom_params(self):
        """Test classifier initialization with custom parameters."""
        with patch("src.domains.agents.services.hitl_classifier.get_llm") as mock_get_llm:
            mock_get_llm.return_value = MagicMock()
            HitlResponseClassifier(
                model="gpt-4.1-mini",
                temperature=0.2,
                top_p=0.95,
                frequency_penalty=0.5,
                presence_penalty=0.3,
            )

            # Verify get_llm factory was called with custom config_override
            mock_get_llm.assert_called_once()
            call_kwargs = mock_get_llm.call_args.kwargs
            assert call_kwargs.get("llm_type") == "hitl_classifier"
            config_override = call_kwargs.get("config_override")
            assert config_override is not None
            assert config_override.get("model") == "gpt-4.1-mini"
            assert config_override.get("temperature") == 0.2
            assert config_override.get("top_p") == 0.95
            assert config_override.get("frequency_penalty") == 0.5
            assert config_override.get("presence_penalty") == 0.3

    def test_init_stores_llm_from_factory(self):
        """Test that classifier stores the LLM instance from factory."""
        with patch("src.domains.agents.services.hitl_classifier.get_llm") as mock_get_llm:
            mock_llm_instance = MagicMock()
            mock_get_llm.return_value = mock_llm_instance

            classifier = HitlResponseClassifier()

            # Verify the LLM instance is stored
            assert classifier.llm is mock_llm_instance


# ============================================================================
# Test Action Type Extraction
# ============================================================================


class TestActionTypeExtraction:
    """Test _extract_action_type method."""

    def test_extract_search_action_type(self, classifier):
        """Test extracting SEARCH action type."""
        context = [{"name": "search_contacts", "args": {"query": "John"}}]
        action_type = classifier._extract_action_type(context)
        assert action_type == ACTION_TYPE_SEARCH

    def test_extract_send_action_type(self, classifier):
        """Test extracting SEND action type."""
        context = [{"name": "send_email", "args": {"to": "john@example.com"}}]
        action_type = classifier._extract_action_type(context)
        assert action_type == ACTION_TYPE_SEND

    def test_extract_delete_action_type(self, classifier):
        """Test extracting DELETE action type."""
        context = [{"name": "delete_contact", "args": {"id": "123"}}]
        action_type = classifier._extract_action_type(context)
        assert action_type == ACTION_TYPE_DELETE

    def test_extract_create_action_type(self, classifier):
        """Test extracting CREATE action type."""
        context = [{"name": "create_contact", "args": {"name": "Jane"}}]
        action_type = classifier._extract_action_type(context)
        assert action_type == ACTION_TYPE_CREATE

    def test_extract_list_action_type(self, classifier):
        """Test extracting LIST action type."""
        context = [{"name": "list_contacts", "args": {}}]
        action_type = classifier._extract_action_type(context)
        assert action_type == ACTION_TYPE_LIST

    def test_extract_get_action_type(self, classifier):
        """Test extracting GET action type."""
        context = [{"name": "get_contact_details", "args": {"id": "123"}}]
        action_type = classifier._extract_action_type(context)
        assert action_type == ACTION_TYPE_GET

    def test_extract_generic_action_type(self, classifier):
        """Test extracting GENERIC action type for unknown tools."""
        context = [{"name": "unknown_tool", "args": {}}]
        action_type = classifier._extract_action_type(context)
        assert action_type == ACTION_TYPE_GENERIC

    def test_extract_action_type_legacy_keys(self, classifier):
        """Test action type extraction with legacy tool_name/tool_args keys."""
        context = [{"tool_name": "search_contacts", "tool_args": {"query": "John"}}]
        action_type = classifier._extract_action_type(context)
        assert action_type == ACTION_TYPE_SEARCH

    def test_extract_action_type_empty_context(self, classifier):
        """Test action type extraction with empty context."""
        action_type = classifier._extract_action_type([])
        assert action_type == ACTION_TYPE_GENERIC

    def test_extract_action_type_multiple_actions(self, classifier):
        """Test action type extraction with multiple actions (future multi-HITL)."""
        context = [
            {"name": "search_contacts", "args": {"query": "John"}},
            {"name": "send_email", "args": {"to": "john@example.com"}},
        ]
        action_type = classifier._extract_action_type(context)
        assert action_type == ACTION_TYPE_GENERIC

    def test_extract_action_type_french_keywords(self, classifier):
        """Test action type extraction with French keywords."""
        context = [{"name": "recherche_contacts", "args": {"query": "Jean"}}]
        action_type = classifier._extract_action_type(context)
        assert action_type == ACTION_TYPE_SEARCH

    def test_extract_action_type_case_insensitive(self, classifier):
        """Test action type extraction is case-insensitive."""
        context = [{"name": "SEARCH_CONTACTS", "args": {"query": "John"}}]
        action_type = classifier._extract_action_type(context)
        assert action_type == ACTION_TYPE_SEARCH


# ============================================================================
# Test Context Formatting
# ============================================================================


class TestContextFormatting:
    """Test _format_action_context method."""

    def test_format_search_context(self, classifier):
        """Test formatting search action context."""
        context = [{"name": "search_contacts", "args": {"query": "John"}}]
        formatted = classifier._format_action_context(context)
        assert "recherche de 'John'" in formatted
        assert "paramètre: query" in formatted

    def test_format_delete_context(self, classifier):
        """Test formatting delete action context."""
        context = [{"name": "delete_contact", "args": {"id": "123"}}]
        formatted = classifier._format_action_context(context)
        assert "suppression" in formatted
        assert "delete_contact" in formatted

    def test_format_send_context(self, classifier):
        """Test formatting send action context."""
        context = [{"name": "send_email", "args": {"to": "john@example.com"}}]
        formatted = classifier._format_action_context(context)
        assert "envoi" in formatted
        assert "send_email" in formatted

    def test_format_create_context(self, classifier):
        """Test formatting create action context."""
        context = [{"name": "create_contact", "args": {"name": "Jane"}}]
        formatted = classifier._format_action_context(context)
        assert "création" in formatted
        assert "create_contact" in formatted

    def test_format_generic_context(self, classifier):
        """Test formatting generic action context."""
        context = [{"name": "unknown_tool", "args": {"param": "value"}}]
        formatted = classifier._format_action_context(context)
        assert "unknown_tool" in formatted
        assert "param" in formatted

    def test_format_empty_context(self, classifier):
        """Test formatting empty context."""
        formatted = classifier._format_action_context([])
        assert formatted == "une action"

    def test_format_multiple_actions(self, classifier):
        """Test formatting multiple actions."""
        context = [
            {"name": "search_contacts", "args": {"query": "John"}},
            {"name": "send_email", "args": {"to": "john@example.com"}},
        ]
        formatted = classifier._format_action_context(context)
        assert "2 actions" in formatted

    def test_format_context_legacy_keys(self, classifier):
        """Test formatting context with legacy tool_name/tool_args keys."""
        context = [{"tool_name": "search_contacts", "tool_args": {"query": "Marie"}}]
        formatted = classifier._format_action_context(context)
        assert "recherche de 'Marie'" in formatted

    def test_format_context_with_alternate_query_key(self, classifier):
        """Test formatting context with alternate query key 'q'."""
        context = [{"name": "search_contacts", "args": {"q": "Paul"}}]
        formatted = classifier._format_action_context(context)
        assert "recherche de 'Paul'" in formatted

    def test_format_context_none_tool_name(self, classifier):
        """Test formatting context when name is None."""
        context = [{"name": None, "args": {"param": "value"}}]
        formatted = classifier._format_action_context(context)
        assert "action" in formatted


# ============================================================================
# Test Contextual Examples Generation
# ============================================================================


class TestContextualExamples:
    """Test _get_contextual_examples method."""

    def test_get_search_examples(self, classifier):
        """Test getting contextual examples for SEARCH actions."""
        examples = classifier._get_contextual_examples(ACTION_TYPE_SEARCH, "recherche de 'John'")
        assert "APPROVE" in examples
        assert "REJECT" in examples
        assert "EDIT" in examples
        assert "non recherche paul" in examples
        assert "oui" in examples

    def test_get_send_examples(self, classifier):
        """Test getting contextual examples for SEND actions."""
        examples = classifier._get_contextual_examples(ACTION_TYPE_SEND, "envoi d'email")
        assert "APPROVE" in examples
        assert "REJECT" in examples
        assert "EDIT" in examples
        assert "non envoie à jean" in examples

    def test_get_delete_examples(self, classifier):
        """Test getting contextual examples for DELETE actions."""
        examples = classifier._get_contextual_examples(ACTION_TYPE_DELETE, "suppression")
        assert "APPROVE" in examples
        assert "REJECT" in examples
        assert "EDIT" in examples
        assert "oui supprime" in examples

    def test_get_generic_examples(self, classifier):
        """Test getting contextual examples for GENERIC actions."""
        examples = classifier._get_contextual_examples(ACTION_TYPE_GENERIC, "action")
        assert "APPROVE" in examples
        assert "REJECT" in examples
        assert "EDIT" in examples


# ============================================================================
# Test Prompt Building
# ============================================================================


class TestPromptBuilding:
    """Test _build_prompt method."""

    @patch("src.domains.agents.services.hitl_classifier.load_prompt")
    @patch("src.core.config.get_settings")
    def test_build_prompt_with_versioned_template(
        self, mock_settings, mock_load_prompt, classifier
    ):
        """Test building prompt with versioned template."""
        # Mock settings
        settings_mock = MagicMock()
        settings_mock.hitl_classifier_prompt_version = HITL_CLASSIFIER_PROMPT_VERSION_DEFAULT
        mock_settings.return_value = settings_mock

        # Mock prompt template
        mock_load_prompt.return_value = "Classification for {action_type}: {action_desc}\nResponse: {response}\n{{EXAMPLES_PLACEHOLDER}}"

        context = [{"name": "search_contacts", "args": {"query": "John"}}]
        messages = classifier._build_prompt("oui", context)

        # Verify returned structure
        assert len(messages) == 1
        assert isinstance(messages[0], SystemMessage)
        assert "recherche" in messages[0].content.lower()
        assert "oui" in messages[0].content

        # Verify versioned prompt was loaded
        mock_load_prompt.assert_called_once_with(
            "hitl_classifier_prompt", version=HITL_CLASSIFIER_PROMPT_VERSION_DEFAULT
        )

    def test_build_prompt_uses_versioned_settings(self, classifier):
        """Test that prompt building uses version from settings."""
        # This test verifies the integration works end-to-end
        # without needing to mock the entire chain
        context = [{"name": "search_contacts", "args": {"query": "John"}}]
        messages = classifier._build_prompt("oui", context)

        # Verify prompt structure
        assert len(messages) == 1
        assert isinstance(messages[0], SystemMessage)
        # Should contain response and action context
        assert "oui" in messages[0].content
        # Should contain examples for search type
        assert "APPROVE" in messages[0].content or "approve" in messages[0].content.lower()

    def test_build_prompt_with_different_action_types(self, classifier):
        """Test building prompts for different action types."""
        test_cases = [
            (ACTION_TYPE_SEARCH, [{"name": "search_contacts", "args": {"query": "John"}}]),
            (ACTION_TYPE_SEND, [{"name": "send_email", "args": {"to": "john@example.com"}}]),
            (ACTION_TYPE_DELETE, [{"name": "delete_contact", "args": {"id": "123"}}]),
        ]

        for _expected_type, context in test_cases:
            messages = classifier._build_prompt("oui", context)
            assert len(messages) == 1
            assert isinstance(messages[0], SystemMessage)


# ============================================================================
# Test Result Parsing
# ============================================================================


class TestResultParsing:
    """Test _parse_result method."""

    def test_parse_valid_approve_result(self, classifier):
        """Test parsing valid APPROVE JSON result."""
        json_content = json.dumps(
            {
                "decision": "APPROVE",
                "confidence": 0.95,
                "reasoning": "User said 'oui'",
            }
        )

        result = classifier._parse_result(json_content)
        assert isinstance(result, ClassificationResult)
        assert result.decision == "APPROVE"
        assert result.confidence == 0.95
        assert result.reasoning == "User said 'oui'"

    def test_parse_valid_edit_result_with_params(self, classifier):
        """Test parsing valid EDIT result with edited_params."""
        json_content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.85,
                "reasoning": "User corrected query",
                "edited_params": {"query": "paul"},
            }
        )

        result = classifier._parse_result(json_content)
        assert result.decision == "EDIT"
        assert result.edited_params == {"query": "paul"}

    def test_parse_valid_ambiguous_result_with_clarification(self, classifier):
        """Test parsing valid AMBIGUOUS result with clarification."""
        json_content = json.dumps(
            {
                "decision": "AMBIGUOUS",
                "confidence": 0.50,
                "reasoning": "Unclear response",
                "clarification_question": "Peux-tu préciser ?",
            }
        )

        result = classifier._parse_result(json_content)
        assert result.decision == "AMBIGUOUS"
        assert result.clarification_question == "Peux-tu préciser ?"

    def test_parse_invalid_json(self, classifier):
        """Test parsing invalid JSON raises ValueError."""
        invalid_json = "not valid json"
        with pytest.raises(ValueError, match="Invalid JSON from classifier"):
            classifier._parse_result(invalid_json)

    def test_parse_missing_required_fields(self, classifier):
        """Test parsing JSON missing required fields raises ValueError."""
        # Missing confidence
        json_content = json.dumps({"decision": "APPROVE", "reasoning": "Test"})
        with pytest.raises(ValueError, match="Missing required fields"):
            classifier._parse_result(json_content)

        # Missing decision
        json_content = json.dumps({"confidence": 0.9, "reasoning": "Test"})
        with pytest.raises(ValueError, match="Missing required fields"):
            classifier._parse_result(json_content)

        # Missing reasoning
        json_content = json.dumps({"decision": "APPROVE", "confidence": 0.9})
        with pytest.raises(ValueError, match="Missing required fields"):
            classifier._parse_result(json_content)

    def test_parse_invalid_decision_type(self, classifier):
        """Test parsing JSON with invalid decision type."""
        json_content = json.dumps(
            {
                "decision": "INVALID_TYPE",
                "confidence": 0.9,
                "reasoning": "Test",
            }
        )
        with pytest.raises(ValueError):  # Pydantic validation error
            classifier._parse_result(json_content)


# ============================================================================
# Test Classification with APPROVE Decision
# ============================================================================


@pytest.mark.asyncio
class TestClassifyApprove:
    """Test classify method with APPROVE decisions."""

    async def test_classify_approve_simple_yes(self, classifier, mock_llm):
        """Test classification of simple 'oui' as APPROVE."""
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "APPROVE",
                "confidence": 0.95,
                "reasoning": "User confirmed with 'oui'",
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "John"}}]
        result = await classifier.classify("oui", context)

        assert result.decision == "APPROVE"
        assert result.confidence == 0.95
        assert mock_llm.ainvoke.called

    async def test_classify_approve_ok_vas_y(self, classifier, mock_llm):
        """Test classification of 'ok vas-y' as APPROVE."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "APPROVE",
                "confidence": 0.90,
                "reasoning": "User confirmed with 'ok vas-y'",
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "send_email", "args": {"to": "john@example.com"}}]
        result = await classifier.classify("ok vas-y", context)

        assert result.decision == "APPROVE"
        assert result.confidence >= 0.90


# ============================================================================
# Test Classification with REJECT Decision
# ============================================================================


@pytest.mark.asyncio
class TestClassifyReject:
    """Test classify method with REJECT decisions."""

    async def test_classify_reject_simple_no(self, classifier, mock_llm):
        """Test classification of simple 'non' as REJECT."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "REJECT",
                "confidence": 0.92,
                "reasoning": "User rejected with 'non'",
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "John"}}]
        result = await classifier.classify("non", context)

        assert result.decision == "REJECT"
        assert result.confidence >= 0.90

    async def test_classify_reject_non_annule(self, classifier, mock_llm):
        """Test classification of 'non annule' as REJECT."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "REJECT",
                "confidence": 0.95,
                "reasoning": "User rejected with 'non annule'",
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "delete_contact", "args": {"id": "123"}}]
        result = await classifier.classify("non annule", context)

        assert result.decision == "REJECT"


# ============================================================================
# Test Classification with EDIT Decision
# ============================================================================


@pytest.mark.asyncio
class TestClassifyEdit:
    """Test classify method with EDIT decisions."""

    async def test_classify_edit_with_new_query(self, classifier, mock_llm):
        """Test classification of 'non recherche paul' as EDIT with new query."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.88,
                "reasoning": "User wants to search for 'paul' instead",
                "edited_params": {"query": "paul"},
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        result = await classifier.classify("non recherche paul", context)

        assert result.decision == "EDIT"
        assert result.edited_params == {"query": "paul"}
        assert result.confidence >= 0.75  # Above demotion threshold

    async def test_classify_edit_plutot_matheo(self, classifier, mock_llm):
        """Test classification of 'plutôt jean' as EDIT."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.85,
                "reasoning": "User wants to search for 'jean' instead",
                "edited_params": {"query": "jean"},
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "marie"}}]
        result = await classifier.classify("plutôt jean", context)

        assert result.decision == "EDIT"
        assert result.edited_params == {"query": "jean"}


# ============================================================================
# Test EDIT Demotion Logic
# ============================================================================


@pytest.mark.asyncio
class TestEditDemotion:
    """Test EDIT decision demotion logic."""

    @pytest.fixture(autouse=True)
    def mock_metrics(self):
        """Mock Prometheus metrics to avoid multiprocess registry issues in tests."""
        with (
            patch(
                "src.infrastructure.observability.metrics_agents.hitl_classification_demoted_total"
            ) as mock_demoted,
            patch(
                "src.infrastructure.observability.metrics_agents.hitl_clarification_fallback_total"
            ) as mock_fallback,
        ):
            # Mock the labels().inc() chain
            mock_demoted.labels.return_value.inc = MagicMock()
            mock_fallback.inc = MagicMock()
            yield {"demoted": mock_demoted, "fallback": mock_fallback}

    async def test_edit_demoted_missing_params(self, classifier, mock_llm):
        """Test EDIT demoted to AMBIGUOUS when edited_params is missing."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.85,
                "reasoning": "User wants to edit but params unclear",
                # No edited_params field
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        result = await classifier.classify("change it", context)

        # Should be demoted to AMBIGUOUS
        assert result.decision == "AMBIGUOUS"
        assert result.confidence == 0.5  # Reset to 0.5
        assert result.clarification_question is not None
        assert result.edited_params == {}

    async def test_edit_demoted_empty_params(self, classifier, mock_llm):
        """Test EDIT demoted to AMBIGUOUS when edited_params is empty dict."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.80,
                "reasoning": "User wants to edit",
                "edited_params": {},  # Empty dict
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        result = await classifier.classify("change it", context)

        # Should be demoted to AMBIGUOUS (empty dict is falsy)
        assert result.decision == "AMBIGUOUS"
        assert result.clarification_question is not None

    async def test_edit_not_demoted_low_confidence_with_valid_params(self, classifier, mock_llm):
        """Test EDIT NOT demoted when confidence < 0.75 but params are present.

        Issue #60 Fix: Don't demote if edited_params contains valid values!
        If the LLM extracted actual parameters, trust the extraction even with lower confidence.
        """
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.70,  # Below 0.75 threshold but HAS valid params
                "reasoning": "Edit intent with params",
                "edited_params": {"query": "paul"},  # Valid params = no demotion
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        result = await classifier.classify("maybe paul", context)

        # Should NOT be demoted because edited_params has values (Issue #60)
        assert result.decision == "EDIT"
        assert result.confidence == 0.70  # Original confidence kept
        assert result.edited_params == {"query": "paul"}  # Params preserved

    async def test_edit_not_demoted_high_confidence_with_params(self, classifier, mock_llm):
        """Test EDIT not demoted when confidence >= 0.75 and params present."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.85,  # Above threshold
                "reasoning": "Clear edit intent",
                "edited_params": {"query": "paul"},
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        result = await classifier.classify("non recherche paul", context)

        # Should NOT be demoted
        assert result.decision == "EDIT"
        assert result.confidence == 0.85
        assert result.edited_params == {"query": "paul"}

    async def test_edit_demoted_with_existing_clarification(self, classifier, mock_llm):
        """Test EDIT demotion preserves existing clarification question."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.85,
                "reasoning": "Edit unclear",
                "clarification_question": "Did you mean to edit the query?",
                # No edited_params
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        result = await classifier.classify("edit it", context)

        # Should preserve existing clarification
        assert result.decision == "AMBIGUOUS"
        assert result.clarification_question == "Did you mean to edit the query?"


# ============================================================================
# Test Classification with AMBIGUOUS Decision
# ============================================================================


@pytest.mark.asyncio
class TestClassifyAmbiguous:
    """Test classify method with AMBIGUOUS decisions."""

    @pytest.fixture(autouse=True)
    def mock_metrics(self):
        """Mock Prometheus metrics for AMBIGUOUS decision tests."""
        with patch(
            "src.infrastructure.observability.metrics_agents.hitl_clarification_fallback_total"
        ) as mock_fallback:
            mock_fallback.inc = MagicMock()
            yield mock_fallback

    async def test_classify_ambiguous_unclear_response(self, classifier, mock_llm):
        """Test classification of unclear response as AMBIGUOUS."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "AMBIGUOUS",
                "confidence": 0.60,
                "reasoning": "Response is unclear",
                "clarification_question": "Peux-tu confirmer (oui/non) ?",
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        result = await classifier.classify("peut-être", context)

        assert result.decision == "AMBIGUOUS"
        assert result.clarification_question is not None


# ============================================================================
# Test Classification with Tracker
# ============================================================================


@pytest.mark.asyncio
class TestClassifyWithTracker:
    """Test classify method with token tracking."""

    async def test_classify_with_tracker(self, classifier, mock_llm, mock_tracker):
        """Test classification with tracker passes it to LLM."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "APPROVE",
                "confidence": 0.95,
                "reasoning": "Approved",
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        await classifier.classify("oui", context, tracker=mock_tracker)

        # Verify tracker was passed to LLM
        mock_llm.ainvoke.assert_called_once()
        call_kwargs = mock_llm.ainvoke.call_args.kwargs
        assert "config" in call_kwargs
        assert "callbacks" in call_kwargs["config"]
        assert mock_tracker in call_kwargs["config"]["callbacks"]

    async def test_classify_without_tracker(self, classifier, mock_llm):
        """Test classification without tracker (no config parameter)."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "APPROVE",
                "confidence": 0.95,
                "reasoning": "Approved",
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        await classifier.classify("oui", context, tracker=None)

        # Verify no config was passed
        mock_llm.ainvoke.assert_called_once()
        call_args = mock_llm.ainvoke.call_args
        # Should be called with just the prompt (no config)
        assert len(call_args.args) == 1 or "config" not in call_args.kwargs


# ============================================================================
# Test Error Handling
# ============================================================================


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling in classification."""

    async def test_classify_llm_error(self, classifier, mock_llm):
        """Test classification handles LLM errors."""
        mock_llm.ainvoke.side_effect = Exception("LLM API error")

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        with pytest.raises(Exception, match="LLM API error"):
            await classifier.classify("oui", context)

    async def test_classify_json_parse_error(self, classifier, mock_llm):
        """Test classification handles JSON parsing errors."""
        mock_response = MagicMock()
        mock_response.content = "not valid json"
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        with pytest.raises(ValueError, match="Invalid JSON from classifier"):
            await classifier.classify("oui", context)

    async def test_classify_handles_list_content(self, classifier, mock_llm):
        """Test classification handles LLM returning list content."""
        mock_response = MagicMock()
        mock_response.content = ["not", "a", "string"]  # List instead of string
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]

        # Should convert to string and fail JSON parsing
        with pytest.raises(ValueError):
            await classifier.classify("oui", context)


# ============================================================================
# Test Metrics Tracking
# ============================================================================


@pytest.mark.asyncio
class TestMetricsTracking:
    """Test Prometheus metrics tracking."""

    @patch("src.infrastructure.observability.metrics_agents.hitl_classification_method_total")
    @patch("src.infrastructure.observability.metrics_agents.hitl_classification_duration_seconds")
    @patch("src.infrastructure.observability.metrics_agents.hitl_classification_confidence")
    async def test_metrics_recorded_on_approve(
        self, mock_confidence, mock_duration, mock_method, classifier, mock_llm
    ):
        """Test metrics are recorded for APPROVE classification."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "APPROVE",
                "confidence": 0.95,
                "reasoning": "Approved",
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        await classifier.classify("oui", context)

        # Verify metrics were incremented
        mock_method.labels.assert_called_with(method="llm", decision="APPROVE")
        mock_method.labels.return_value.inc.assert_called_once()

        mock_duration.labels.assert_called_with(method="llm")
        mock_duration.labels.return_value.observe.assert_called_once()

        mock_confidence.labels.assert_called_with(decision="APPROVE")
        mock_confidence.labels.return_value.observe.assert_called_with(0.95)

    @patch("src.infrastructure.observability.metrics_agents.hitl_clarification_fallback_total")
    @patch("src.infrastructure.observability.metrics_agents.hitl_classification_demoted_total")
    async def test_metrics_recorded_on_edit_demotion_missing_params(
        self, mock_demoted, mock_fallback, classifier, mock_llm
    ):
        """Test demotion metric recorded when EDIT demoted for missing params."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.85,
                "reasoning": "Edit unclear",
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        await classifier.classify("change it", context)

        # Verify demotion metric was incremented
        mock_demoted.labels.assert_called_with(
            from_decision="EDIT", to_decision="AMBIGUOUS", reason="missing_params"
        )
        mock_demoted.labels.return_value.inc.assert_called_once()

    @patch("src.infrastructure.observability.metrics_agents.hitl_clarification_fallback_total")
    @patch("src.infrastructure.observability.metrics_agents.hitl_classification_demoted_total")
    async def test_metrics_recorded_on_edit_demotion_low_confidence(
        self, mock_demoted, mock_fallback, classifier, mock_llm
    ):
        """Test demotion metric recorded when EDIT demoted for low confidence.

        Issue #60 Fix: Demotion only happens if confidence is low AND no params extracted.
        This test uses empty params to trigger the demotion path.
        """
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.70,  # Below threshold
                "reasoning": "Low confidence",
                "edited_params": {},  # Empty params = demotion eligible (Issue #60)
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        await classifier.classify("maybe paul", context)

        # Verify demotion metric was incremented (empty params triggers missing_params path)
        mock_demoted.labels.assert_called_with(
            from_decision="EDIT", to_decision="AMBIGUOUS", reason="missing_params"
        )
        mock_demoted.labels.return_value.inc.assert_called_once()

    @patch("src.infrastructure.observability.metrics_agents.hitl_clarification_fallback_total")
    async def test_metrics_recorded_on_ambiguous(self, mock_fallback, classifier, mock_llm):
        """Test clarification fallback metric recorded for AMBIGUOUS."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "AMBIGUOUS",
                "confidence": 0.60,
                "reasoning": "Unclear",
                "clarification_question": "Peux-tu préciser ?",
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        await classifier.classify("peut-être", context)

        # Verify clarification fallback metric was incremented
        mock_fallback.inc.assert_called_once()


# ============================================================================
# Test Edge Cases
# ============================================================================


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture(autouse=True)
    def mock_metrics(self):
        """Mock Prometheus metrics for edge case tests."""
        with patch(
            "src.infrastructure.observability.metrics_agents.hitl_clarification_fallback_total"
        ) as mock_fallback:
            mock_fallback.inc = MagicMock()
            yield mock_fallback

    async def test_classify_empty_response(self, classifier, mock_llm):
        """Test classification with empty user response."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "AMBIGUOUS",
                "confidence": 0.50,
                "reasoning": "Empty response",
                "clarification_question": "Pouvez-vous clarifier votre demande ?",
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        result = await classifier.classify("", context)

        assert result.decision == "AMBIGUOUS"
        # Verify fallback clarification is used
        assert "clarifier" in result.clarification_question.lower()

    async def test_classify_very_long_response(self, classifier, mock_llm):
        """Test classification with very long user response."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.85,
                "reasoning": "User provided detailed correction",
                "edited_params": {"query": "new_value"},
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        long_response = "non, " * 100 + "recherche paul"
        result = await classifier.classify(long_response, context)

        assert result.decision == "EDIT"

    async def test_classify_empty_action_context(self, classifier, mock_llm):
        """Test classification with empty action context."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "APPROVE",
                "confidence": 0.90,
                "reasoning": "User confirmed",
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        result = await classifier.classify("oui", [])

        assert result.decision == "APPROVE"

    async def test_classify_with_unicode_characters(self, classifier, mock_llm):
        """Test classification with Unicode characters in response."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.88,
                "reasoning": "User corrected with accents",
                "edited_params": {"query": "Huà"},
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "jean"}}]
        result = await classifier.classify("non recherche Huà", context)

        assert result.decision == "EDIT"
        assert result.edited_params["query"] == "Huà"

    async def test_classify_confidence_exactly_at_threshold(self, classifier, mock_llm):
        """Test EDIT with confidence exactly at 0.75 threshold (should NOT demote)."""
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "decision": "EDIT",
                "confidence": 0.75,  # Exactly at threshold
                "reasoning": "Edit at threshold",
                "edited_params": {"query": "paul"},
            }
        )
        mock_llm.ainvoke.return_value = mock_response

        context = [{"name": "search_contacts", "args": {"query": "john"}}]
        result = await classifier.classify("recherche paul", context)

        # Should NOT be demoted (>= 0.75)
        assert result.decision == "EDIT"
        assert result.confidence == 0.75
