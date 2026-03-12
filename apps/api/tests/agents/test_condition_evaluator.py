"""
Tests pour ConditionEvaluator (Phase 5.2).

Tests de l'évaluation sécurisée des conditions pour CONDITIONAL steps.
"""

import pytest

from src.domains.agents.orchestration.condition_evaluator import (
    ConditionEvaluator,
    ReferenceResolver,
)


class TestConditionEvaluator:
    """Tests pour ConditionEvaluator."""

    @pytest.fixture
    def evaluator(self):
        """Create evaluator instance."""
        return ConditionEvaluator()

    @pytest.fixture
    def sample_results(self):
        """Sample step results for testing."""
        return {
            "search": {
                "results": [
                    {"id": 1, "name": "John Doe"},
                    {"id": 2, "name": "Jane Smith"},
                ],
                "count": 2,
            },
            "get_details": {
                "contact": {
                    "id": 1,
                    "name": "John Doe",
                    "emails": ["john@example.com"],
                },
            },
        }

    # ========================================================================
    # Basic Comparisons
    # ========================================================================

    def test_simple_length_check(self, evaluator, sample_results):
        """Test simple length check condition."""
        condition = "len($steps.search.results) > 0"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    def test_length_equals(self, evaluator, sample_results):
        """Test length equality check."""
        condition = "len($steps.search.results) == 2"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    def test_length_less_than(self, evaluator, sample_results):
        """Test length less than check."""
        condition = "len($steps.search.results) < 10"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    def test_field_comparison(self, evaluator, sample_results):
        """Test direct field comparison."""
        condition = "$steps.search.count == 2"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    def test_string_comparison(self, evaluator, sample_results):
        """Test string field comparison."""
        condition = "$steps.get_details.contact.name == 'John Doe'"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    # ========================================================================
    # Boolean Logic
    # ========================================================================

    def test_and_condition(self, evaluator, sample_results):
        """Test AND boolean operator."""
        condition = "len($steps.search.results) > 0 and $steps.search.count == 2"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    def test_or_condition(self, evaluator, sample_results):
        """Test OR boolean operator."""
        condition = "len($steps.search.results) == 0 or $steps.search.count > 1"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    def test_not_condition(self, evaluator, sample_results):
        """Test NOT boolean operator."""
        condition = "not len($steps.search.results) == 0"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    def test_complex_boolean(self, evaluator, sample_results):
        """Test complex boolean expression."""
        condition = "(len($steps.search.results) > 0 and $steps.search.count == 2) or $steps.search.count == 0"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    # ========================================================================
    # Array Access
    # ========================================================================

    def test_array_index_access(self, evaluator, sample_results):
        """Test accessing array elements by index."""
        condition = "$steps.search.results[0].id == 1"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    def test_array_index_string(self, evaluator, sample_results):
        """Test accessing array element string field."""
        condition = "$steps.search.results[1].name == 'Jane Smith'"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    def test_nested_array_access(self, evaluator, sample_results):
        """Test accessing nested arrays."""
        condition = "$steps.get_details.contact.emails[0] == 'john@example.com'"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    # ========================================================================
    # in / not in Operators
    # ========================================================================

    def test_in_operator(self, evaluator, sample_results):
        """Test 'in' operator."""
        condition = "'john@example.com' in $steps.get_details.contact.emails"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    def test_not_in_operator(self, evaluator, sample_results):
        """Test 'not in' operator."""
        condition = "'invalid@example.com' not in $steps.get_details.contact.emails"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    # ========================================================================
    # Edge Cases
    # ========================================================================

    def test_false_condition(self, evaluator, sample_results):
        """Test condition that evaluates to False."""
        condition = "len($steps.search.results) == 0"
        result = evaluator.evaluate(condition, sample_results)
        assert result is False

    def test_nonexistent_step_reference(self, evaluator, sample_results):
        """Test reference to non-existent step."""
        condition = "len($steps.nonexistent.results) > 0"
        with pytest.raises(KeyError) as exc_info:
            evaluator.evaluate(condition, sample_results)
        assert "non-existent step: nonexistent" in str(exc_info.value)

    def test_invalid_field_access(self, evaluator, sample_results):
        """Test accessing non-existent field."""
        condition = "$steps.search.nonexistent_field == 1"
        with pytest.raises((ValueError, KeyError)):
            evaluator.evaluate(condition, sample_results)

    # ========================================================================
    # Security Tests (AST Whitelist)
    # ========================================================================

    def test_unsafe_function_call_rejected(self, evaluator, sample_results):
        """Test that unsafe functions are rejected."""
        condition = "eval($steps.search.count)"
        with pytest.raises(ValueError) as exc_info:
            evaluator.evaluate(condition, sample_results)
        assert "Only len() function allowed" in str(exc_info.value)

    def test_import_statement_rejected(self, evaluator, sample_results):
        """Test that import statements are rejected."""
        condition = "import os"
        with pytest.raises(ValueError) as exc_info:
            evaluator.evaluate(condition, sample_results)
        assert "Invalid condition syntax" in str(exc_info.value)

    def test_lambda_rejected(self, evaluator, sample_results):
        """Test that lambda expressions are rejected."""
        condition = "(lambda x: x > 0)(len($steps.search.results))"
        with pytest.raises(ValueError) as exc_info:
            evaluator.evaluate(condition, sample_results)
        # Lambda may be caught as unsafe function or unsafe AST node
        assert "Unsafe AST node" in str(exc_info.value) or "Only len()" in str(exc_info.value)

    def test_list_comprehension_rejected(self, evaluator, sample_results):
        """Test that list comprehensions are rejected."""
        condition = "len([x for x in $steps.search.results if x.id > 0]) > 0"
        with pytest.raises(ValueError) as exc_info:
            evaluator.evaluate(condition, sample_results)
        assert "Unsafe AST node" in str(exc_info.value)

    def test_attribute_assignment_rejected(self, evaluator, sample_results):
        """Test that attribute assignments are rejected."""
        condition = "$steps.search.count = 10"
        with pytest.raises(ValueError) as exc_info:
            evaluator.evaluate(condition, sample_results)
        assert "Invalid condition syntax" in str(exc_info.value)

    # ========================================================================
    # Reference Resolution
    # ========================================================================

    def test_multiple_references_same_step(self, evaluator, sample_results):
        """Test multiple references to same step."""
        condition = "$steps.search.count > 0 and len($steps.search.results) > 0"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    def test_references_different_steps(self, evaluator, sample_results):
        """Test references to different steps."""
        condition = "len($steps.search.results) > 0 and $steps.get_details.contact.id == 1"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    def test_nested_field_access(self, evaluator, sample_results):
        """Test deeply nested field access."""
        condition = "$steps.get_details.contact.emails[0] == 'john@example.com'"
        result = evaluator.evaluate(condition, sample_results)
        assert result is True

    # ========================================================================
    # Empty/Null Cases
    # ========================================================================

    def test_empty_results(self, evaluator):
        """Test condition with empty results."""
        empty_results = {"search": {"results": [], "count": 0}}
        condition = "len($steps.search.results) == 0"
        result = evaluator.evaluate(condition, empty_results)
        assert result is True

    def test_none_value_comparison(self, evaluator):
        """Test comparison with None value."""
        none_results = {"search": {"value": None}}
        condition = "$steps.search.value == None"
        result = evaluator.evaluate(condition, none_results)
        assert result is True

    # ========================================================================
    # Comma-Separated References (resolve_args)
    # ========================================================================


class TestReferenceResolverCommaSeparated:
    """Tests for comma-separated $steps reference resolution."""

    @pytest.fixture
    def resolver(self):
        return ReferenceResolver()

    @pytest.fixture
    def contacts_results(self):
        return {
            "step_1": {
                "contacts": [
                    {"emailAddresses": [{"value": "wife@example.com"}]},
                    {"emailAddresses": [{"value": "son@example.com"}]},
                ],
            },
        }

    def test_comma_separated_references_no_space(self, resolver, contacts_results):
        """Test comma-separated $steps references without space."""
        args = {
            "to": "$steps.step_1.contacts[0].emailAddresses[0].value,$steps.step_1.contacts[1].emailAddresses[0].value",
        }
        resolved = resolver.resolve_args(args, contacts_results)
        assert resolved["to"] == "wife@example.com,son@example.com"

    def test_comma_separated_references_with_space(self, resolver, contacts_results):
        """Test comma-separated $steps references with space after comma."""
        args = {
            "to": "$steps.step_1.contacts[0].emailAddresses[0].value, $steps.step_1.contacts[1].emailAddresses[0].value",
        }
        resolved = resolver.resolve_args(args, contacts_results)
        assert resolved["to"] == "wife@example.com,son@example.com"

    def test_comma_separated_references_multiple_spaces(self, resolver, contacts_results):
        """Test comma-separated $steps references with multiple spaces."""
        args = {
            "to": "$steps.step_1.contacts[0].emailAddresses[0].value,  $steps.step_1.contacts[1].emailAddresses[0].value",
        }
        resolved = resolver.resolve_args(args, contacts_results)
        assert resolved["to"] == "wife@example.com,son@example.com"

    def test_is_comma_separated_with_space(self, resolver):
        """Test _is_comma_separated_references detects space variants."""
        assert resolver._is_comma_separated_references("$steps.a.x, $steps.b.y")
        assert resolver._is_comma_separated_references("$steps.a.x,$steps.b.y")
        assert not resolver._is_comma_separated_references("$steps.a.x")
        assert not resolver._is_comma_separated_references("plain string")
