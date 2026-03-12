"""
Tests for _coerce_args_to_schema() in parallel_executor.

MCP FIX: Tests for list/dict → JSON string coercion when tool expects str.
This handles the case where LLMs generate native JSON arrays/objects in plan
parameters instead of escaped JSON strings (e.g., Excalidraw elements).
"""

import json

from pydantic import BaseModel, Field

from src.domains.agents.orchestration.parallel_executor import _coerce_args_to_schema

# ============================================================================
# Test Schemas (simulate MCP tool schemas from build_args_schema)
# ============================================================================


class SimpleStringSchema(BaseModel):
    """Schema with a string parameter (like Excalidraw create_view elements)."""

    elements: str = Field(description="JSON string of elements")


class MixedSchema(BaseModel):
    """Schema with mixed parameter types."""

    name: str = Field(description="Name")
    count: int = Field(description="Count")
    items: list = Field(description="List of items")


class OptionalStringSchema(BaseModel):
    """Schema with optional string parameter."""

    data: str | None = Field(default=None, description="Optional data")


# ============================================================================
# Tests: list → str coercion (MCP FIX)
# ============================================================================


class TestCoerceListToStr:
    """Tests for list → JSON string coercion."""

    def test_list_coerced_to_json_string(self):
        """When tool expects str but gets list, serialize to JSON string."""
        args = {
            "elements": [
                {"type": "rectangle", "id": "r1", "x": 100, "y": 100},
                {"type": "text", "id": "t1", "text": "Hello"},
            ]
        }
        result = _coerce_args_to_schema(args, SimpleStringSchema)

        assert isinstance(result["elements"], str)
        parsed = json.loads(result["elements"])
        assert len(parsed) == 2
        assert parsed[0]["type"] == "rectangle"
        assert parsed[0]["x"] == 100
        assert parsed[1]["text"] == "Hello"

    def test_dict_coerced_to_json_string(self):
        """When tool expects str but gets dict, serialize to JSON string."""
        args = {"elements": {"type": "rectangle", "x": 100, "y": 200}}
        result = _coerce_args_to_schema(args, SimpleStringSchema)

        assert isinstance(result["elements"], str)
        parsed = json.loads(result["elements"])
        assert parsed["type"] == "rectangle"
        assert parsed["x"] == 100

    def test_empty_list_coerced_to_json_string(self):
        """Empty list should become '[]' string."""
        args = {"elements": []}
        result = _coerce_args_to_schema(args, SimpleStringSchema)

        assert result["elements"] == "[]"

    def test_empty_dict_coerced_to_json_string(self):
        """Empty dict should become '{}' string."""
        args = {"elements": {}}
        result = _coerce_args_to_schema(args, SimpleStringSchema)

        assert result["elements"] == "{}"

    def test_nested_structures_preserved(self):
        """Nested JSON structures should be fully preserved."""
        args = {
            "elements": [
                {
                    "type": "arrow",
                    "points": [[0, 0], [200, 100]],
                    "label": {"text": "Connection", "fontSize": 16},
                }
            ]
        }
        result = _coerce_args_to_schema(args, SimpleStringSchema)

        assert isinstance(result["elements"], str)
        parsed = json.loads(result["elements"])
        assert parsed[0]["points"] == [[0, 0], [200, 100]]
        assert parsed[0]["label"]["text"] == "Connection"

    def test_string_value_not_double_serialized(self):
        """String values should NOT be re-serialized."""
        args = {"elements": '[{"type": "rectangle"}]'}
        result = _coerce_args_to_schema(args, SimpleStringSchema)

        # Should remain as-is, not double-encoded
        assert result["elements"] == '[{"type": "rectangle"}]'

    def test_int_still_coerced_to_str(self):
        """Existing int → str coercion should still work."""
        args = {"elements": 42}
        result = _coerce_args_to_schema(args, SimpleStringSchema)
        assert result["elements"] == "42"


# ============================================================================
# Tests: existing coercions still work
# ============================================================================


class TestExistingCoercions:
    """Verify existing coercion rules are not broken."""

    def test_float_to_int(self):
        """Float → int coercion."""
        args = {"name": "test", "count": 5.0, "items": ["a"]}
        result = _coerce_args_to_schema(args, MixedSchema)
        assert result["count"] == 5
        assert isinstance(result["count"], int)

    def test_string_values_preserved(self):
        """String values stay as strings."""
        args = {"name": "hello", "count": 3, "items": ["a", "b"]}
        result = _coerce_args_to_schema(args, MixedSchema)
        assert result["name"] == "hello"

    def test_unknown_keys_preserved(self):
        """Keys not in schema are preserved as-is."""
        args = {"elements": "valid_string", "unknown_key": [1, 2, 3]}
        result = _coerce_args_to_schema(args, SimpleStringSchema)
        assert result["unknown_key"] == [1, 2, 3]

    def test_non_basemodel_schema_returns_args_unchanged(self):
        """Non-BaseModel schema returns args unchanged."""
        args = {"elements": [1, 2, 3]}
        result = _coerce_args_to_schema(args, dict)  # type: ignore
        assert result == args


# ============================================================================
# Tests: Excalidraw-realistic scenarios
# ============================================================================


class TestExcalidrawRealisticScenarios:
    """Realistic scenarios matching Excalidraw MCP tool usage."""

    def test_full_excalidraw_elements_array(self):
        """Test with realistic Excalidraw element array."""
        elements = [
            {
                "type": "rectangle",
                "id": "api-box",
                "x": 300,
                "y": 100,
                "width": 200,
                "height": 80,
                "backgroundColor": "#a5d8ff",
                "strokeColor": "#1e1e1e",
            },
            {
                "type": "text",
                "id": "api-label",
                "text": "API Server",
                "containerId": "api-box",
                "x": 0,
                "y": 0,
                "width": 100,
                "height": 20,
                "fontSize": 16,
            },
            {
                "type": "arrow",
                "id": "arrow-1",
                "x": 200,
                "y": 140,
                "width": 100,
                "height": 0,
                "points": [[0, 0], [100, 0]],
                "endArrowhead": "arrow",
            },
        ]

        args = {"elements": elements}
        result = _coerce_args_to_schema(args, SimpleStringSchema)

        assert isinstance(result["elements"], str)
        parsed = json.loads(result["elements"])
        assert len(parsed) == 3

        # Verify coordinates are preserved exactly
        rect = parsed[0]
        assert rect["x"] == 300
        assert rect["y"] == 100
        assert rect["backgroundColor"] == "#a5d8ff"

        # Verify containerId binding is preserved
        text = parsed[1]
        assert text["containerId"] == "api-box"
        assert text["x"] == 0
        assert text["y"] == 0

        # Verify arrow points are preserved
        arrow = parsed[2]
        assert arrow["points"] == [[0, 0], [100, 0]]

    def test_elements_with_unicode(self):
        """Test elements with Unicode characters (multilingual labels)."""
        args = {
            "elements": [
                {"type": "text", "id": "t1", "text": "Serveur d'API", "x": 0, "y": 0},
                {"type": "text", "id": "t2", "text": "Base de données", "x": 0, "y": 100},
            ]
        }
        result = _coerce_args_to_schema(args, SimpleStringSchema)

        parsed = json.loads(result["elements"])
        assert parsed[0]["text"] == "Serveur d'API"
        assert parsed[1]["text"] == "Base de données"
