"""
Tests for conditional step evaluation in parallel_executor.

PHASE 3.2.1 - Critical missing tests (T-CRIT-003)
Tests the condition evaluation logic in condition_evaluator.py
"""

import pytest

from src.domains.agents.orchestration.condition_evaluator import ConditionEvaluator


class TestConditionEvaluator:
    """Test ConditionEvaluator for conditional step execution"""

    def test_simple_equality_condition(self):
        """Test simple equality condition"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"total_count": 5, "success": True}}

        # When: Evaluate condition
        result = evaluator.evaluate("$steps.search_contacts.total_count == 5", step_results)

        # Then: Condition evaluates to True
        assert result is True

    def test_simple_inequality_condition(self):
        """Test simple inequality condition"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"total_count": 5, "success": True}}

        # When: Evaluate condition
        result = evaluator.evaluate("$steps.search_contacts.total_count > 10", step_results)

        # Then: Condition evaluates to False
        assert result is False

    def test_boolean_json_style_normalization(self):
        """Test JSON-style boolean (true) normalization to Python (True)"""
        # Given: Evaluator and step results with boolean value
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"success": True, "total_count": 5}}

        # When: Evaluate condition with JSON-style "true" (lowercase)
        result = evaluator.evaluate(
            "$steps.search_contacts.success == true",
            step_results,  # JSON-style lowercase
        )

        # Then: Condition evaluates correctly (true normalized to True)
        assert result is True

    def test_boolean_false_normalization(self):
        """Test JSON-style boolean (false) normalization to Python (False)"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"success": False}}

        # When: Evaluate condition with JSON-style "false"
        result = evaluator.evaluate(
            "$steps.search_contacts.success == false",
            step_results,  # JSON-style lowercase
        )

        # Then: Condition evaluates correctly
        assert result is True

    def test_null_normalization(self):
        """Test JSON-style null normalization to Python None"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"error": None}}

        # When: Evaluate condition with JSON-style "null"
        result = evaluator.evaluate(
            "$steps.search_contacts.error == null",
            step_results,  # JSON-style null
        )

        # Then: Condition evaluates correctly (null normalized to None)
        assert result is True

    def test_len_function_condition(self):
        """Test condition using len() function (only allowed function)"""
        # Given: Evaluator and step results with array
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"contacts": [{"name": "John"}, {"name": "Jane"}]}}

        # When: Evaluate condition using len()
        result = evaluator.evaluate("len($steps.search_contacts.contacts) > 1", step_results)

        # Then: Condition evaluates correctly
        assert result is True

    def test_len_function_with_zero(self):
        """Test len() condition with empty array"""
        # Given: Evaluator and step results with empty array
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"contacts": []}}

        # When: Evaluate condition
        result = evaluator.evaluate("len($steps.search_contacts.contacts) == 0", step_results)

        # Then: Condition evaluates to True
        assert result is True

    def test_complex_boolean_condition_and(self):
        """Test complex condition with AND operator"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"total_count": 5, "success": True}}

        # When: Evaluate condition with AND
        result = evaluator.evaluate(
            "$steps.search_contacts.total_count > 0 and $steps.search_contacts.success == True",
            step_results,
        )

        # Then: Condition evaluates to True
        assert result is True

    def test_complex_boolean_condition_or(self):
        """Test complex condition with OR operator"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"total_count": 0, "success": False}}

        # When: Evaluate condition with OR
        result = evaluator.evaluate(
            "$steps.search_contacts.total_count > 0 or $steps.search_contacts.success == True",
            step_results,
        )

        # Then: Condition evaluates to False (both conditions false)
        assert result is False

    def test_nested_field_access(self):
        """Test condition with nested field access"""
        # Given: Evaluator and step results with nested structure
        evaluator = ConditionEvaluator()
        step_results = {
            "get_contact": {
                "contact": {
                    "name": "John Doe",
                    "emails": [{"value": "john@example.com", "type": "work"}],
                }
            }
        }

        # When: Evaluate condition with nested access
        # Note: Array index access in conditions
        result = evaluator.evaluate("len($steps.get_contact.contact.emails) > 0", step_results)

        # Then: Condition evaluates correctly
        assert result is True

    def test_string_comparison(self):
        """Test condition with string comparison"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"get_contact": {"status": "found"}}

        # When: Evaluate string equality
        result = evaluator.evaluate("$steps.get_contact.status == 'found'", step_results)

        # Then: Condition evaluates to True
        assert result is True

    def test_in_operator(self):
        """Test condition with 'in' operator"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"tags": ["work", "important"]}}

        # When: Evaluate 'in' condition
        result = evaluator.evaluate("'work' in $steps.search_contacts.tags", step_results)

        # Then: Condition evaluates to True
        assert result is True

    def test_not_in_operator(self):
        """Test condition with 'not in' operator"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"tags": ["work", "important"]}}

        # When: Evaluate 'not in' condition
        result = evaluator.evaluate("'personal' not in $steps.search_contacts.tags", step_results)

        # Then: Condition evaluates to True
        assert result is True

    def test_unary_not_operator(self):
        """Test condition with unary 'not' operator"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"success": False}}

        # When: Evaluate 'not' condition
        result = evaluator.evaluate("not $steps.search_contacts.success", step_results)

        # Then: Condition evaluates to True
        assert result is True

    def test_reference_to_non_existent_step(self):
        """Test condition referencing non-existent step (should raise KeyError)"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"total_count": 5}}

        # When/Then: Evaluate condition referencing non-existent step
        with pytest.raises(KeyError, match="Reference to non-existent step"):
            evaluator.evaluate("$steps.non_existent_step.total_count > 0", step_results)

    def test_invalid_syntax_condition(self):
        """Test condition with invalid Python syntax"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"total_count": 5}}

        # When/Then: Evaluate condition with syntax error
        with pytest.raises(ValueError, match="Invalid condition syntax"):
            evaluator.evaluate(
                "$steps.search_contacts.total_count == ",
                step_results,  # Incomplete expression
            )

    def test_unsafe_ast_node_rejected(self):
        """Test that unsafe AST nodes are rejected"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"total_count": 5}}

        # When/Then: Evaluate condition with unsafe operation (e.g., import)
        # Note: This is caught by the disallowed function check (only len() allowed)
        with pytest.raises(ValueError, match="Only len\\(\\) function allowed"):
            evaluator.evaluate("__import__('os').system('echo pwned')", step_results)

    def test_disallowed_function_rejected(self):
        """Test that functions other than len() are rejected"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"name": "John"}}

        # When/Then: Evaluate condition with disallowed function (e.g., str())
        with pytest.raises(ValueError, match="Only len\\(\\) function allowed"):
            evaluator.evaluate("str($steps.search_contacts.name) == 'John'", step_results)

    def test_comparison_operators_all_supported(self):
        """Test all comparison operators (==, !=, <, <=, >, >=)"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"count": 10}}

        # When/Then: Test all comparison operators
        assert evaluator.evaluate("$steps.search_contacts.count == 10", step_results) is True
        assert evaluator.evaluate("$steps.search_contacts.count != 5", step_results) is True
        assert evaluator.evaluate("$steps.search_contacts.count < 20", step_results) is True
        assert evaluator.evaluate("$steps.search_contacts.count <= 10", step_results) is True
        assert evaluator.evaluate("$steps.search_contacts.count > 5", step_results) is True
        assert evaluator.evaluate("$steps.search_contacts.count >= 10", step_results) is True

    def test_empty_step_results(self):
        """Test condition evaluation with empty step results"""
        # Given: Evaluator with no step results
        evaluator = ConditionEvaluator()
        step_results = {}

        # When/Then: Evaluate condition referencing non-existent step
        with pytest.raises(KeyError, match="Reference to non-existent step"):
            evaluator.evaluate("$steps.search_contacts.total_count > 0", step_results)

    def test_numeric_comparison_with_floats(self):
        """Test numeric comparison with float values"""
        # Given: Evaluator and step results with float
        evaluator = ConditionEvaluator()
        step_results = {"calculate_score": {"score": 8.5}}

        # When: Evaluate condition with float comparison
        result = evaluator.evaluate("$steps.calculate_score.score > 8.0", step_results)

        # Then: Condition evaluates correctly
        assert result is True

    def test_condition_with_list_literal(self):
        """Test condition comparing against list literal"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"statuses": ["active", "pending"]}}

        # When: Evaluate condition with list comparison
        result = evaluator.evaluate(
            "$steps.search_contacts.statuses == ['active', 'pending']", step_results
        )

        # Then: Condition evaluates correctly
        assert result is True

    def test_condition_evaluation_returns_boolean(self):
        """Test that condition evaluation always returns boolean"""
        # Given: Evaluator and step results
        evaluator = ConditionEvaluator()
        step_results = {"search_contacts": {"total_count": 5}}

        # When: Evaluate condition
        result = evaluator.evaluate("$steps.search_contacts.total_count > 0", step_results)

        # Then: Result is boolean
        assert isinstance(result, bool)
        assert result is True

    def test_condition_with_dict_access(self):
        """Test condition accessing nested dict values"""
        # Given: Evaluator and step results with nested dict
        evaluator = ConditionEvaluator()
        step_results = {"get_contact": {"contact": {"metadata": {"verified": True, "score": 95}}}}

        # When: Evaluate condition with nested dict access
        result = evaluator.evaluate(
            "$steps.get_contact.contact.metadata.verified == True and $steps.get_contact.contact.metadata.score > 90",
            step_results,
        )

        # Then: Condition evaluates correctly
        assert result is True
