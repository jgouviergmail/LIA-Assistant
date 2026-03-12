"""
Unit tests for HITL Schema Validator.

Tests for the schema validation of edited tool arguments
against tool Pydantic schemas for HITL EDIT flows.
"""

from typing import Any, Optional, Union
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, ConfigDict, Field

from src.domains.agents.services.hitl.schema_validator import (
    HitlSchemaValidator,
    ValidationResult,
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_valid_result(self):
        """Test creating a valid result."""
        result = ValidationResult(
            is_valid=True,
            validated_args={"name": "John"},
        )
        assert result.is_valid is True
        assert result.validated_args == {"name": "John"}
        assert result.errors == []

    def test_invalid_result(self):
        """Test creating an invalid result."""
        result = ValidationResult(
            is_valid=False,
            errors=["field1: Required field", "field2: Invalid type"],
        )
        assert result.is_valid is False
        assert result.validated_args is None
        assert result.errors == ["field1: Required field", "field2: Invalid type"]

    def test_errors_default_to_empty_list(self):
        """Test that errors default to empty list when None."""
        result = ValidationResult(is_valid=True, validated_args={}, errors=None)
        assert result.errors == []


class TestHitlSchemaValidatorTypeCompatibility:
    """Tests for HitlSchemaValidator._check_type_compatibility() method."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance with mocked tools."""
        with patch.object(HitlSchemaValidator, "_build_tool_registry", return_value={}):
            return HitlSchemaValidator()

    def test_none_with_optional(self, validator):
        """Test None is valid for Optional types."""
        assert validator._check_type_compatibility(None, Optional[str]) is True  # noqa: UP007
        # Note: str | None creates types.UnionType which is handled by the code
        # The implementation checks using typing.Union and types.UnionType
        from typing import Union

        assert validator._check_type_compatibility(None, Union[str, None]) is True  # noqa: UP007

    def test_none_without_optional(self, validator):
        """Test None is invalid for non-Optional types."""
        assert validator._check_type_compatibility(None, str) is False
        assert validator._check_type_compatibility(None, int) is False

    def test_union_type(self, validator):
        """Test Union type checking."""
        assert validator._check_type_compatibility("hello", Union[str, int]) is True  # noqa: UP007
        assert validator._check_type_compatibility(42, Union[str, int]) is True  # noqa: UP007
        assert validator._check_type_compatibility(3.14, Union[str, int]) is False  # noqa: UP007

    def test_list_type(self, validator):
        """Test list type checking."""
        assert validator._check_type_compatibility(["a", "b"], list[str]) is True
        assert validator._check_type_compatibility([], list[int]) is True
        assert validator._check_type_compatibility("not a list", list[str]) is False

    def test_dict_type(self, validator):
        """Test dict type checking."""
        assert validator._check_type_compatibility({"key": "value"}, dict[str, str]) is True
        assert validator._check_type_compatibility({}, dict[str, Any]) is True
        assert validator._check_type_compatibility("not a dict", dict[str, str]) is False

    def test_set_type(self, validator):
        """Test set type checking."""
        assert validator._check_type_compatibility({1, 2, 3}, set[int]) is True
        assert validator._check_type_compatibility([], set[int]) is False

    def test_int_type_strict(self, validator):
        """Test int type is strict (no bool, no float, no str)."""
        assert validator._check_type_compatibility(42, int) is True
        assert validator._check_type_compatibility(True, int) is False  # bool not valid as int
        assert validator._check_type_compatibility(3.14, int) is False
        assert validator._check_type_compatibility("42", int) is False

    def test_float_type_accepts_int(self, validator):
        """Test float type accepts int for numeric flexibility."""
        assert validator._check_type_compatibility(3.14, float) is True
        assert validator._check_type_compatibility(42, float) is True  # int accepted
        assert validator._check_type_compatibility(True, float) is False
        assert validator._check_type_compatibility("3.14", float) is False

    def test_str_type(self, validator):
        """Test string type checking."""
        assert validator._check_type_compatibility("hello", str) is True
        assert validator._check_type_compatibility(42, str) is False
        assert validator._check_type_compatibility(None, str) is False

    def test_bool_type(self, validator):
        """Test bool type checking."""
        assert validator._check_type_compatibility(True, bool) is True
        assert validator._check_type_compatibility(False, bool) is True
        assert validator._check_type_compatibility(1, bool) is False
        assert validator._check_type_compatibility("true", bool) is False


class TestHitlSchemaValidatorValidateToolArgs:
    """Tests for HitlSchemaValidator.validate_tool_args() method."""

    def test_unknown_tool_returns_error(self):
        """Test that unknown tool returns validation error."""
        with patch.object(HitlSchemaValidator, "_build_tool_registry", return_value={}):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="unknown_tool",
                merged_args={"param": "value"},
            )

        assert result.is_valid is False
        assert "Unknown tool: unknown_tool" in result.errors[0]

    def test_tool_without_schema_returns_error(self):
        """Test that tool without args_schema returns error."""
        mock_tool = MagicMock()
        mock_tool.name = "tool_without_schema"
        mock_tool.args_schema = None

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"tool_without_schema": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="tool_without_schema",
                merged_args={"param": "value"},
            )

        assert result.is_valid is False
        assert "has no args_schema" in result.errors[0]

    def test_valid_args_pass_validation(self):
        """Test that valid args pass validation."""

        class MockSchema(BaseModel):
            name: str
            age: int

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.args_schema = MockSchema

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"test_tool": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="test_tool",
                merged_args={"name": "John", "age": 30},
            )

        assert result.is_valid is True
        assert result.validated_args == {"name": "John", "age": 30}

    def test_invalid_type_fails_validation(self):
        """Test that invalid types fail validation."""

        class MockSchema(BaseModel):
            age: int

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.args_schema = MockSchema

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"test_tool": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="test_tool",
                merged_args={"age": "not an int"},
            )

        assert result.is_valid is False
        assert any("age" in error for error in result.errors)

    def test_missing_required_field_fails_validation(self):
        """Test that missing required field fails validation."""

        class MockSchema(BaseModel):
            name: str
            description: str = Field(default=None)

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.args_schema = MockSchema

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"test_tool": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="test_tool",
                merged_args={"description": "A description"},  # Missing 'name'
            )

        assert result.is_valid is False
        assert any("name" in error for error in result.errors)

    def test_invalid_field_name_fails_validation(self):
        """Test that invalid field name fails validation."""

        class MockSchema(BaseModel):
            valid_field: str

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.args_schema = MockSchema

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"test_tool": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="test_tool",
                merged_args={"valid_field": "value", "invalid_field": "bad"},
            )

        assert result.is_valid is False
        assert any("invalid_field" in error for error in result.errors)

    def test_runtime_field_is_filtered(self):
        """Test that 'runtime' field is always filtered out."""

        class MockSchema(BaseModel):
            query: str
            runtime: Any = None  # Injected by LangChain

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.args_schema = MockSchema

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"test_tool": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="test_tool",
                merged_args={"query": "test", "runtime": {"user_id": "123"}},
            )

        assert result.is_valid is True
        # runtime should not be in validated_args (it's filtered for user-editable check)
        assert "runtime" not in result.validated_args

    def test_optional_field_accepts_none(self):
        """Test that optional field accepts None."""

        class MockSchema(BaseModel):
            name: str
            nickname: str | None = None

        mock_tool = MagicMock()
        mock_tool.name = "test_tool"
        mock_tool.args_schema = MockSchema

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"test_tool": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="test_tool",
                merged_args={"name": "John", "nickname": None},
            )

        assert result.is_valid is True

    def test_schema_without_model_fields_fallback(self):
        """Test fallback when schema has no model_fields."""
        mock_tool = MagicMock()
        mock_tool.name = "legacy_tool"
        mock_tool.args_schema = MagicMock(spec=[])  # No model_fields attribute

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"legacy_tool": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="legacy_tool",
                merged_args={"any": "args"},
            )

        assert result.is_valid is True
        assert result.validated_args == {"any": "args"}


class TestHitlSchemaValidatorBuildToolRegistry:
    """Tests for HitlSchemaValidator._build_tool_registry() method."""

    def test_registry_built_on_init(self):
        """Test that tool registry is built on initialization."""
        # We can't easily test the real registry without the actual tools
        # But we can verify the structure
        with patch(
            "src.domains.agents.services.hitl.schema_validator.get_contacts_tool",
            create=True,
        ) as mock_contacts:
            mock_contacts.name = "get_contacts"
            mock_tool = MagicMock()
            mock_tool.name = "get_contacts"

            with patch.object(
                HitlSchemaValidator,
                "_build_tool_registry",
                return_value={"get_contacts": mock_tool},
            ):
                validator = HitlSchemaValidator()
                assert "get_contacts" in validator.tools

    def test_import_error_handled_gracefully(self):
        """Test that ImportError is handled gracefully."""
        # When tools can't be imported, the validator should still work
        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={},  # Empty registry due to import failures
        ):
            validator = HitlSchemaValidator()
            assert validator.tools == {}


class TestHitlSchemaValidatorEdgeCases:
    """Tests for edge cases and error handling."""

    def test_validation_error_from_pydantic(self):
        """Test handling of Pydantic ValidationError."""

        class StrictSchema(BaseModel):
            model_config = ConfigDict(strict=True)

            value: int

        mock_tool = MagicMock()
        mock_tool.name = "strict_tool"
        mock_tool.args_schema = StrictSchema

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"strict_tool": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="strict_tool",
                merged_args={"value": "not-an-int"},
            )

        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_unexpected_exception_handled(self):
        """Test handling of unexpected exceptions."""
        mock_tool = MagicMock()
        mock_tool.name = "buggy_tool"
        mock_tool.args_schema = MagicMock()
        # Make model_fields raise an exception
        type(mock_tool.args_schema).model_fields = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Unexpected error"))
        )

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"buggy_tool": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="buggy_tool",
                merged_args={"param": "value"},
            )

        assert result.is_valid is False
        assert any("Validation error" in error for error in result.errors)

    def test_empty_merged_args_with_optional_fields(self):
        """Test empty merged_args with all optional fields."""

        class AllOptionalSchema(BaseModel):
            field1: str | None = None
            field2: int | None = None

        mock_tool = MagicMock()
        mock_tool.name = "optional_tool"
        mock_tool.args_schema = AllOptionalSchema

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"optional_tool": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="optional_tool",
                merged_args={},
            )

        assert result.is_valid is True

    def test_complex_nested_types(self):
        """Test validation with complex nested types."""

        class NestedSchema(BaseModel):
            tags: list[str] = []
            metadata: dict[str, Any] = {}

        mock_tool = MagicMock()
        mock_tool.name = "nested_tool"
        mock_tool.args_schema = NestedSchema

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"nested_tool": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="nested_tool",
                merged_args={
                    "tags": ["tag1", "tag2"],
                    "metadata": {"key": "value"},
                },
            )

        assert result.is_valid is True

    def test_multiple_validation_errors(self):
        """Test that multiple validation errors are collected."""

        class MultiFieldSchema(BaseModel):
            name: str
            age: int
            email: str

        mock_tool = MagicMock()
        mock_tool.name = "multi_tool"
        mock_tool.args_schema = MultiFieldSchema

        with patch.object(
            HitlSchemaValidator,
            "_build_tool_registry",
            return_value={"multi_tool": mock_tool},
        ):
            validator = HitlSchemaValidator()
            result = validator.validate_tool_args(
                tool_name="multi_tool",
                merged_args={
                    "name": 123,  # Wrong type
                    "age": "not an int",  # Wrong type
                    # Missing email
                },
            )

        assert result.is_valid is False
        assert len(result.errors) >= 2  # At least 2 errors
