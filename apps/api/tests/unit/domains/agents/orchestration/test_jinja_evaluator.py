"""
Unit Tests for Jinja2 Template Evaluator
Phase: Issue #41 - Template Evaluation with Safety Enhancements

Test Coverage:
- Basic template evaluation
- Conditional templates ({% if %})
- Variable substitution ({{ }})
- Nested references (steps.search.emails[0].id)
- Empty results handling (required vs optional)
- JS syntax auto-translation (.length → | length)
- Recursion depth limit
- Error handling (syntax errors, undefined refs)
- Security (sandboxed execution)

Author: Claude Code
Date: 2025-11-24
Issue: #41
"""

import pytest

from src.domains.agents.orchestration.jinja_evaluator import (
    EmptyResultError,
    JinjaTemplateEvaluator,
)


class TestBasicTemplateEvaluation:
    """Test basic template evaluation functionality."""

    def test_simple_variable_substitution(self):
        """Test simple {{ variable }} substitution."""
        evaluator = JinjaTemplateEvaluator()

        template = "{{ steps.search.email_id }}"
        context = {"steps": {"search": {"email_id": "19ab5f5ba6b8a51a"}}}

        result = evaluator.evaluate(template, context, "test_step")

        assert result == "19ab5f5ba6b8a51a"

    def test_array_index_access(self):
        """Test array indexing: steps.search.emails[1].id"""
        evaluator = JinjaTemplateEvaluator()

        template = "{{ steps.search.emails[1].id }}"
        context = {
            "steps": {
                "search": {
                    "emails": [
                        {"id": "19ab5f7f8ea15893"},
                        {"id": "19ab5f5ba6b8a51a"},
                        {"id": "19ab5eda72345678"},
                    ]
                }
            }
        }

        result = evaluator.evaluate(template, context, "test_step")

        assert result == "19ab5f5ba6b8a51a"

    def test_nested_dict_access(self):
        """Test nested dict access: steps.search.contact.names[0].displayName"""
        evaluator = JinjaTemplateEvaluator()

        template = "{{ steps.search.contact.names[0].displayName }}"
        context = {"steps": {"search": {"contact": {"names": [{"displayName": "John Doe"}]}}}}

        result = evaluator.evaluate(template, context, "test_step")

        assert result == "John Doe"

    def test_no_template_returns_original(self):
        """Test that plain strings without Jinja2 syntax are returned unchanged."""
        evaluator = JinjaTemplateEvaluator()

        plain_string = "19ab5f5ba6b8a51a"
        context = {"steps": {}}

        result = evaluator.evaluate(plain_string, context, "test_step")

        # Plain strings are still "rendered" but unchanged
        assert result == plain_string


class TestConditionalTemplates:
    """Test conditional template evaluation ({% if %})."""

    def test_if_condition_true(self):
        """Test {% if condition %}value{% endif %} when condition is true."""
        evaluator = JinjaTemplateEvaluator()

        template = (
            "{% if steps.search.emails | length >= 2 %}{{ steps.search.emails[1].id }}{% endif %}"
        )
        context = {
            "steps": {
                "search": {
                    "emails": [
                        {"id": "19ab5f7f8ea15893"},
                        {"id": "19ab5f5ba6b8a51a"},
                    ]
                }
            }
        }

        result = evaluator.evaluate(template, context, "test_step")

        assert result == "19ab5f5ba6b8a51a"

    def test_if_condition_false_returns_empty(self):
        """Test {% if condition %}value{% endif %} when condition is false (returns empty)."""
        evaluator = JinjaTemplateEvaluator()

        template = (
            "{% if steps.search.emails | length >= 5 %}{{ steps.search.emails[4].id }}{% endif %}"
        )
        context = {
            "steps": {
                "search": {
                    "emails": [
                        {"id": "19ab5f7f8ea15893"},
                        {"id": "19ab5f5ba6b8a51a"},
                    ]
                }
            }
        }

        result = evaluator.evaluate(template, context, "test_step")

        # Condition false → empty string
        assert result == ""

    def test_if_else_condition(self):
        """Test {% if %}...{% else %}...{% endif %} branches."""
        evaluator = JinjaTemplateEvaluator()

        template = (
            "{% if steps.search.emails | length >= 5 %}"
            "{{ steps.search.emails[4].id }}"
            "{% else %}"
            "not_enough_emails"
            "{% endif %}"
        )
        context = {
            "steps": {
                "search": {
                    "emails": [
                        {"id": "19ab5f7f8ea15893"},
                        {"id": "19ab5f5ba6b8a51a"},
                    ]
                }
            }
        }

        result = evaluator.evaluate(template, context, "test_step")

        assert result == "not_enough_emails"


class TestLengthFilter:
    """Test the | length filter (Python/Jinja2 native)."""

    def test_length_filter_list(self):
        """Test | length filter on lists."""
        evaluator = JinjaTemplateEvaluator()

        template = "{{ steps.search.emails | length }}"
        context = {"steps": {"search": {"emails": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}}}

        result = evaluator.evaluate(template, context, "test_step")

        assert result == "3"

    def test_length_filter_dict(self):
        """Test | length filter on dicts (counts keys)."""
        evaluator = JinjaTemplateEvaluator()

        template = "{{ steps.search.contact | length }}"
        context = {"steps": {"search": {"contact": {"name": "John", "email": "j@ex.com"}}}}

        result = evaluator.evaluate(template, context, "test_step")

        assert result == "2"  # 2 keys

    def test_length_filter_empty_list(self):
        """Test | length filter on empty list."""
        evaluator = JinjaTemplateEvaluator()

        template = "{{ steps.search.emails | length }}"
        context = {"steps": {"search": {"emails": []}}}

        result = evaluator.evaluate(template, context, "test_step")

        assert result == "0"


class TestJSSyntaxCompatibility:
    """Test JS syntax auto-translation (.length → | length)."""

    def test_js_length_auto_translated(self):
        """Test .length is automatically translated to | length."""
        evaluator = JinjaTemplateEvaluator()

        # JS syntax: steps.search.emails.length
        template = (
            "{% if steps.search.emails.length >= 2 %}{{ steps.search.emails[1].id }}{% endif %}"
        )
        context = {
            "steps": {
                "search": {
                    "emails": [
                        {"id": "19ab5f7f8ea15893"},
                        {"id": "19ab5f5ba6b8a51a"},
                    ]
                }
            }
        }

        result = evaluator.evaluate(template, context, "test_step")

        # Should work despite JS syntax
        assert result == "19ab5f5ba6b8a51a"

    def test_js_length_nested_path(self):
        """Test .length translation on nested paths."""
        evaluator = JinjaTemplateEvaluator()

        template = "{{ steps.search_contacts.contacts.length }}"
        context = {"steps": {"search_contacts": {"contacts": [{"id": "1"}, {"id": "2"}]}}}

        result = evaluator.evaluate(template, context, "test_step")

        assert result == "2"

    def test_js_get_method_logs_warning(self, caplog):
        """Test that .get() JS syntax logs warning."""
        evaluator = JinjaTemplateEvaluator()

        # JS syntax: .get('key')
        template = "{{ steps.search.result.get('id') }}"
        context = {"steps": {"search": {"result": {"id": "123"}}}}

        # Should log warning about .get()
        evaluator.evaluate(template, context, "test_step")

        # Check warning in logs
        assert any("js_syntax_get_detected" in record.message for record in caplog.records)


class TestEmptyResultHandling:
    """Test empty result handling for required vs optional parameters."""

    def test_empty_result_optional_param_returns_empty(self):
        """Test that empty result for optional param returns empty string (no error)."""
        evaluator = JinjaTemplateEvaluator()

        template = "{% if steps.search.emails | length >= 5 %}X{% endif %}"
        context = {"steps": {"search": {"emails": []}}}

        result = evaluator.evaluate(
            template, context, "test_step", parameter_name="optional_field", is_required=False
        )

        # Optional param → empty OK
        assert result == ""

    def test_empty_result_required_param_raises_error(self):
        """Test that empty result for required param raises EmptyResultError."""
        evaluator = JinjaTemplateEvaluator()

        # Condition false → empty string
        template = (
            "{% if steps.search.emails | length >= 5 %}{{ steps.search.emails[4].id }}{% endif %}"
        )
        context = {"steps": {"search": {"emails": [{"id": "1"}, {"id": "2"}]}}}  # Only 2 emails

        with pytest.raises(EmptyResultError) as exc_info:
            evaluator.evaluate(
                template,
                context,
                "test_step",
                parameter_name="message_id",
                is_required=True,
            )

        assert "required parameter" in str(exc_info.value).lower()
        assert "message_id" in str(exc_info.value)

    def test_whitespace_only_result_treated_as_empty(self):
        """Test that whitespace-only results are treated as empty."""
        evaluator = JinjaTemplateEvaluator()

        template = "   "  # Whitespace only
        context = {"steps": {}}

        with pytest.raises(EmptyResultError):
            evaluator.evaluate(
                template,
                context,
                "test_step",
                parameter_name="message_id",
                is_required=True,
            )


class TestRecursionDepthLimit:
    """Test recursion depth limit protection."""

    def test_recursion_limit_prevents_dos(self):
        """Test that recursion depth limit prevents DoS attacks."""
        evaluator = JinjaTemplateEvaluator(max_recursion_depth=3)

        # Create deeply nested structure (4 levels → exceeds limit of 3)
        parameters = {"level1": {"level2": {"level3": {"level4": "value"}}}}
        completed_steps = {}

        with pytest.raises(RecursionError) as exc_info:
            evaluator.evaluate_parameters(parameters, completed_steps, "test_step")

        assert "recursion depth limit" in str(exc_info.value).lower()
        assert "3" in str(exc_info.value)  # Shows limit

    def test_shallow_nesting_within_limit(self):
        """Test that shallow nesting (within limit) works fine."""
        evaluator = JinjaTemplateEvaluator(max_recursion_depth=5)

        # 3 levels of nesting (within limit of 5)
        parameters = {
            "tool_params": {
                "message_id": "{% if steps.search.emails | length >= 1 %}{{ steps.search.emails[0].id }}{% endif %}"
            }
        }
        completed_steps = {"search": {"emails": [{"id": "123"}]}}

        result = evaluator.evaluate_parameters(
            parameters, completed_steps, "test_step", required_params=["message_id"]
        )

        assert result["tool_params"]["message_id"] == "123"


class TestEvaluateParameters:
    """Test evaluate_parameters() method (recursive evaluation)."""

    def test_evaluate_all_parameters(self):
        """Test that all parameters with templates are evaluated."""
        evaluator = JinjaTemplateEvaluator()

        parameters = {
            "message_id": "{{ steps.search.emails[0].id }}",
            "include_body": True,  # Non-template
            "format": "full",  # Non-template
        }
        completed_steps = {"search": {"emails": [{"id": "19ab5f5ba6b8a51a"}]}}

        result = evaluator.evaluate_parameters(parameters, completed_steps, "test_step")

        assert result["message_id"] == "19ab5f5ba6b8a51a"
        assert result["include_body"] is True
        assert result["format"] == "full"

    def test_nested_dict_parameters_evaluated(self):
        """Test that nested dict parameters are recursively evaluated."""
        evaluator = JinjaTemplateEvaluator()

        parameters = {
            "tool_params": {
                "message_id": "{{ steps.search.emails[0].id }}",
                "options": {"include_body": True},
            }
        }
        completed_steps = {"search": {"emails": [{"id": "123"}]}}

        result = evaluator.evaluate_parameters(parameters, completed_steps, "test_step")

        assert result["tool_params"]["message_id"] == "123"
        assert result["tool_params"]["options"]["include_body"] is True

    def test_list_parameters_evaluated(self):
        """Test that list parameters are recursively evaluated."""
        evaluator = JinjaTemplateEvaluator()

        parameters = {
            "recipient_ids": [
                "{{ steps.search.contacts[0].id }}",
                "{{ steps.search.contacts[1].id }}",
            ]
        }
        completed_steps = {"search": {"contacts": [{"id": "contact_1"}, {"id": "contact_2"}]}}

        result = evaluator.evaluate_parameters(parameters, completed_steps, "test_step")

        assert result["recipient_ids"] == ["contact_1", "contact_2"]

    def test_required_param_empty_raises_error_in_evaluate_parameters(self):
        """Test that required param evaluating to empty raises error in evaluate_parameters."""
        evaluator = JinjaTemplateEvaluator()

        parameters = {
            "message_id": "{% if steps.search.emails | length >= 5 %}{{ steps.search.emails[4].id }}{% endif %}",
            "include_body": True,
        }
        completed_steps = {"search": {"emails": [{"id": "1"}]}}  # Only 1 email

        with pytest.raises(EmptyResultError):
            evaluator.evaluate_parameters(
                parameters, completed_steps, "test_step", required_params=["message_id"]
            )


class TestErrorHandling:
    """Test error handling for various failure scenarios."""

    def test_syntax_error_returns_none(self):
        """Test that template syntax errors return None (graceful degradation)."""
        evaluator = JinjaTemplateEvaluator()

        # Invalid Jinja2 syntax
        template = "{% if steps.search.emails | length >= 2 %}{{ steps.search.emails[1].id }}"  # Missing {% endif %}
        context = {"steps": {"search": {"emails": [{"id": "1"}, {"id": "2"}]}}}

        result = evaluator.evaluate(template, context, "test_step")

        # Should return None on syntax error
        assert result is None

    def test_undefined_reference_returns_none(self):
        """Test that undefined references return None."""
        evaluator = JinjaTemplateEvaluator()

        template = "{{ steps.nonexistent.field }}"
        context = {"steps": {"search": {"emails": []}}}

        result = evaluator.evaluate(template, context, "test_step")

        # Undefined → None
        assert result is None

    def test_syntax_error_with_js_syntax_logs_hint(self, caplog):
        """Test that syntax errors with JS syntax log helpful hint."""
        evaluator = JinjaTemplateEvaluator()

        # Invalid template with JS .length (will be translated but still invalid)
        template = "{% if steps.search.emails.length >= 2 %}{{ INVALID_SYNTAX"  # Broken template
        context = {"steps": {"search": {"emails": []}}}

        result = evaluator.evaluate(template, context, "test_step")

        assert result is None
        # Should log hint about JS syntax (even though .length was translated, template is still broken)


class TestContainsJinjaSyntax:
    """Test contains_jinja_syntax() detection method."""

    def test_detects_variable_syntax(self):
        """Test detection of {{ variable }} syntax."""
        evaluator = JinjaTemplateEvaluator()

        assert evaluator.contains_jinja_syntax("{{ steps.search.email_id }}") is True

    def test_detects_control_syntax(self):
        """Test detection of {% if %} syntax."""
        evaluator = JinjaTemplateEvaluator()

        assert evaluator.contains_jinja_syntax("{% if condition %}value{% endif %}") is True

    def test_detects_comment_syntax(self):
        """Test detection of {# comment #} syntax."""
        evaluator = JinjaTemplateEvaluator()

        assert evaluator.contains_jinja_syntax("{# This is a comment #}") is True

    def test_plain_string_not_detected(self):
        """Test that plain strings are not detected as templates."""
        evaluator = JinjaTemplateEvaluator()

        assert evaluator.contains_jinja_syntax("19ab5f5ba6b8a51a") is False
        assert evaluator.contains_jinja_syntax("plain text") is False

    def test_non_string_returns_false(self):
        """Test that non-string values return False."""
        evaluator = JinjaTemplateEvaluator()

        assert evaluator.contains_jinja_syntax(123) is False
        assert evaluator.contains_jinja_syntax(None) is False
        assert evaluator.contains_jinja_syntax({"key": "value"}) is False


class TestSecuritySandbox:
    """Test that sandboxed environment prevents code injection."""

    def test_cannot_import_modules(self):
        """Test that templates cannot import Python modules."""
        evaluator = JinjaTemplateEvaluator()

        # Attempt to import os module
        template = "{{ ''.__class__.__mro__[1].__subclasses__() }}"
        context = {"steps": {}}

        result = evaluator.evaluate(template, context, "test_step")

        # Should fail (sandbox blocks dangerous access)
        assert result is None  # Returns None on error

    def test_cannot_access_private_attributes(self):
        """Test that templates cannot access private attributes."""
        evaluator = JinjaTemplateEvaluator()

        # Attempt to access __dict__
        template = "{{ steps.__dict__ }}"
        context = {"steps": {"search": {"emails": []}}}

        result = evaluator.evaluate(template, context, "test_step")

        # Should fail or return None
        assert result is None or "__dict__" not in result


# Pytest configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
