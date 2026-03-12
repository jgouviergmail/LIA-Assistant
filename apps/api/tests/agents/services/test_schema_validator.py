"""Tests for HITL Schema Validator."""

import pytest

from src.domains.agents.services.hitl.schema_validator import (
    HitlSchemaValidator,
)


@pytest.fixture
def schema_validator():
    """Create schema validator instance for testing."""
    return HitlSchemaValidator()


# =============================================================================
# Test: Tool Registry
# =============================================================================


def test_tool_registry_initialized(schema_validator):
    """Test that tool registry is initialized with tools."""
    # At least one tool should be registered
    assert len(schema_validator.tools) >= 1
    # Unified contacts tool should be present
    assert "get_contacts_tool" in schema_validator.tools


def test_all_tools_have_schema(schema_validator):
    """Test that all registered tools have args_schema (critical validation)."""
    for tool_name, tool in schema_validator.tools.items():
        assert tool.args_schema is not None, f"Tool {tool_name} has no args_schema"


# =============================================================================
# Test: Validation Success
# =============================================================================


def test_validate_valid_args(schema_validator):
    """Test validation with valid arguments."""
    # Arrange - using unified get_contacts_tool
    tool_name = "get_contacts_tool"
    merged_args = {
        "query": "test",
        "max_results": 10,
        "force_refresh": False,
    }

    # Act
    result = schema_validator.validate_tool_args(tool_name, merged_args)

    # Assert
    assert result.is_valid is True
    assert result.validated_args is not None
    assert result.validated_args.get("query") == "test"
    assert result.validated_args.get("max_results") == 10
    assert result.errors == []


def test_validate_minimal_args(schema_validator):
    """Test validation with minimal arguments (all optional for get_contacts_tool)."""
    # Arrange - get_contacts_tool has all optional params
    tool_name = "get_contacts_tool"
    merged_args = {"query": "test"}

    # Act
    result = schema_validator.validate_tool_args(tool_name, merged_args)

    # Assert
    assert result.is_valid is True
    assert result.validated_args is not None
    assert result.validated_args.get("query") == "test"


# =============================================================================
# Test: Validation Errors
# =============================================================================


def test_validate_type_mismatch(schema_validator):
    """Test validation detects type mismatches."""
    # Arrange
    tool_name = "get_contacts_tool"
    merged_args = {
        "query": "test",
        "max_results": "abc",  # Should be int, not string
    }

    # Act
    result = schema_validator.validate_tool_args(tool_name, merged_args)

    # Assert
    assert result.is_valid is False
    assert result.validated_args is None
    assert len(result.errors) > 0
    assert any("max_results" in error for error in result.errors)


def test_validate_unknown_tool(schema_validator):
    """Test validation handles unknown tool gracefully."""
    # Arrange
    tool_name = "unknown_tool_xyz"
    merged_args = {"param": "value"}

    # Act
    result = schema_validator.validate_tool_args(tool_name, merged_args)

    # Assert
    assert result.is_valid is False
    assert result.validated_args is None
    assert len(result.errors) == 1
    assert "Unknown tool" in result.errors[0]


# =============================================================================
# Test: Runtime Param Filtering
# =============================================================================


def test_validate_filters_runtime_param(schema_validator):
    """Test that 'runtime' parameter is filtered out before validation."""
    # Arrange
    tool_name = "get_contacts_tool"
    merged_args = {
        "query": "test",
        "runtime": "should_be_filtered",  # Injected by LangChain, not in schema
    }

    # Act
    result = schema_validator.validate_tool_args(tool_name, merged_args)

    # Assert
    assert result.is_valid is True  # Should pass despite 'runtime' param
    assert "runtime" not in result.validated_args  # Should be filtered out
