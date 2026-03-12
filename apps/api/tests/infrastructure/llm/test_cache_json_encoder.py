"""
Unit tests for CacheJSONEncoder (Phase 2.1.8 - RC4 Fix).

Tests robust JSON serialization of complex types commonly found in LLM responses:
    - Pydantic models (RouterOutput, structured outputs)
    - Decimal objects (from cost calculations)
    - datetime objects (timestamps)
    - Nested structures (lists, dicts with complex types)

User feedback: "attention à la sérialisation JSON d'objets riches (Pydantic, Decimal, etc.).
Il faudra probablement un encodeur personnalisé (pydantic_encoder)"
"""

import json
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import BaseModel

from src.infrastructure.cache.llm_cache import CacheJSONEncoder

# ============================================================================
# Test Fixtures - Mock Pydantic Models
# ============================================================================


class SimpleModel(BaseModel):
    """Simple Pydantic model for basic serialization tests."""

    name: str
    value: int


class NestedModel(BaseModel):
    """Nested Pydantic model with complex types."""

    id: str
    cost: Decimal
    created_at: datetime
    metadata: dict


class RouterOutput(BaseModel):
    """
    Mock RouterOutput model (similar to actual AgentOutput).

    Represents typical LLM structured output with Pydantic validation.
    """

    next_node: str
    confidence: float
    reasoning: str | None = None


# ============================================================================
# CacheJSONEncoder - Basic Type Tests
# ============================================================================


def test_encode_pydantic_simple():
    """
    Test encoding simple Pydantic model.

    Scenario:
        - Model with string and int fields
        - Should serialize to dict via model_dump()

    Validates: Basic Pydantic serialization
    """
    model = SimpleModel(name="test", value=42)

    encoded = json.dumps(model, cls=CacheJSONEncoder)
    decoded = json.loads(encoded)

    assert decoded == {"name": "test", "value": 42}
    assert isinstance(decoded, dict)


def test_encode_pydantic_nested():
    """
    Test encoding nested Pydantic model with complex types.

    Scenario:
        - Model with Decimal, datetime, dict fields
        - Should recursively serialize all fields
        - Note: Pydantic's model_dump(mode="json") converts Decimal → str (safe for precision)

    Validates: Complex Pydantic serialization
    """
    now = datetime(2025, 1, 1, 12, 0, 0)
    model = NestedModel(
        id="test-123",
        cost=Decimal("0.00025"),
        created_at=now,
        metadata={"key": "value"},
    )

    encoded = json.dumps(model, cls=CacheJSONEncoder)
    decoded = json.loads(encoded)

    assert decoded["id"] == "test-123"
    # Pydantic's mode="json" converts Decimal to string (preserves precision)
    assert decoded["cost"] == "0.00025"
    assert decoded["created_at"] == "2025-01-01T12:00:00"  # datetime ISO format
    assert decoded["metadata"] == {"key": "value"}


def test_encode_decimal():
    """
    Test encoding Decimal objects (from cost calculations).

    Scenario:
        - Standalone Decimal values
        - Should convert to float for JSON compatibility

    Validates: Decimal serialization
    """
    data = {
        "cost_eur": Decimal("0.000123"),
        "cost_usd": Decimal("0.000135"),
    }

    encoded = json.dumps(data, cls=CacheJSONEncoder)
    decoded = json.loads(encoded)

    assert decoded["cost_eur"] == 0.000123
    assert decoded["cost_usd"] == 0.000135
    assert isinstance(decoded["cost_eur"], float)


def test_encode_datetime():
    """
    Test encoding datetime objects.

    Scenario:
        - Standalone datetime values
        - Should serialize to ISO 8601 format

    Validates: datetime serialization
    """
    data = {
        "cached_at": datetime(2025, 1, 1, 12, 0, 0),
        "expires_at": datetime(2025, 1, 1, 18, 0, 0),
    }

    encoded = json.dumps(data, cls=CacheJSONEncoder)
    decoded = json.loads(encoded)

    assert decoded["cached_at"] == "2025-01-01T12:00:00"
    assert decoded["expires_at"] == "2025-01-01T18:00:00"
    assert isinstance(decoded["cached_at"], str)


# ============================================================================
# CacheJSONEncoder - Complex Scenarios
# ============================================================================


def test_encode_cache_value_v2_format():
    """
    Test encoding complete cache value v2 format.

    Scenario:
        - Cache value with result (Pydantic model) and metadata (usage, timestamps)
        - Represents actual cache MISS storage format

    Validates: Real-world cache serialization
    """
    import time

    router_output = RouterOutput(
        next_node="response_node",
        confidence=0.95,
        reasoning="User query is clear and actionable",
    )

    cache_value = {
        "result": router_output,
        "metadata": {
            "version": 2,
            "cached_at": time.time(),
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cached_tokens": 0,
                "model_name": "gpt-4.1-mini",
            },
        },
    }

    # Should not raise exception
    encoded = json.dumps(cache_value, cls=CacheJSONEncoder, ensure_ascii=False)
    decoded = json.loads(encoded)

    # Verify structure
    assert "result" in decoded
    assert "metadata" in decoded
    assert decoded["metadata"]["version"] == 2
    assert decoded["metadata"]["usage"]["input_tokens"] == 100
    assert decoded["result"]["next_node"] == "response_node"


def test_encode_list_of_pydantic_models():
    """
    Test encoding list containing Pydantic models.

    Scenario:
        - LLM might return list of structured outputs
        - Each element should be serialized correctly

    Validates: Collection serialization
    """
    models = [
        SimpleModel(name="item1", value=1),
        SimpleModel(name="item2", value=2),
        SimpleModel(name="item3", value=3),
    ]

    encoded = json.dumps(models, cls=CacheJSONEncoder)
    decoded = json.loads(encoded)

    assert len(decoded) == 3
    assert decoded[0] == {"name": "item1", "value": 1}
    assert decoded[2] == {"name": "item3", "value": 3}


def test_encode_deeply_nested_structures():
    """
    Test encoding deeply nested structures with mixed types.

    Scenario:
        - Complex cache value with nested Pydantic, Decimal, datetime
        - Represents edge case with maximum complexity
        - Mix of standalone Decimals (→ float) and Pydantic Decimals (→ string)

    Validates: Recursive serialization
    """
    now = datetime(2025, 1, 1, 12, 0, 0)

    data = {
        "result": {
            "models": [
                NestedModel(
                    id="item1",
                    cost=Decimal("0.0001"),
                    created_at=now,
                    metadata={"nested": {"key": "value"}},
                ),
                NestedModel(
                    id="item2",
                    cost=Decimal("0.0002"),
                    created_at=now,
                    metadata={"nested": {"key": "value2"}},
                ),
            ],
            "total_cost": Decimal("0.0003"),  # Standalone Decimal → float
        },
        "metadata": {
            "cached_at": now,
            "version": 2,
        },
    }

    # Should handle complex nesting
    encoded = json.dumps(data, cls=CacheJSONEncoder)
    decoded = json.loads(encoded)

    # Standalone Decimal (not in Pydantic model) → float
    assert decoded["result"]["total_cost"] == 0.0003
    # Decimal inside Pydantic model → string (Pydantic behavior)
    assert decoded["result"]["models"][0]["cost"] == "0.0001"
    assert decoded["metadata"]["cached_at"] == "2025-01-01T12:00:00"


# ============================================================================
# CacheJSONEncoder - Edge Cases
# ============================================================================


def test_encode_none_values():
    """
    Test encoding None values (optional fields).

    Scenario:
        - Pydantic model with optional fields = None
        - Should serialize as null in JSON

    Validates: None handling
    """
    model = RouterOutput(next_node="response_node", confidence=0.95, reasoning=None)

    encoded = json.dumps(model, cls=CacheJSONEncoder)
    decoded = json.loads(encoded)

    assert decoded["reasoning"] is None


def test_encode_empty_collections():
    """
    Test encoding empty lists and dicts.

    Scenario:
        - Cache value with empty metadata or results
        - Should serialize as empty collections

    Validates: Empty collection handling
    """
    data = {
        "result": {},
        "metadata": {
            "usage": {},
            "tags": [],
        },
    }

    encoded = json.dumps(data, cls=CacheJSONEncoder)
    decoded = json.loads(encoded)

    assert decoded["result"] == {}
    assert decoded["metadata"]["usage"] == {}
    assert decoded["metadata"]["tags"] == []


def test_encode_unicode_strings():
    """
    Test encoding Unicode strings (international characters).

    Scenario:
        - LLM response with non-ASCII characters
        - Should preserve Unicode with ensure_ascii=False

    Validates: Unicode support (critical for i18n)
    """
    model = SimpleModel(name="tëst with émojis 🎉", value=42)

    encoded = json.dumps(model, cls=CacheJSONEncoder, ensure_ascii=False)
    decoded = json.loads(encoded)

    assert decoded["name"] == "tëst with émojis 🎉"


def test_encode_standard_types_unchanged():
    """
    Test that standard JSON types pass through unchanged.

    Scenario:
        - Data with only str, int, float, bool, list, dict
        - Should serialize normally without custom handling

    Validates: Backward compatibility with standard JSON
    """
    data = {
        "string": "test",
        "integer": 42,
        "float": 3.14,
        "boolean": True,
        "null": None,
        "list": [1, 2, 3],
        "dict": {"nested": "value"},
    }

    # Should work identically to standard json.dumps
    encoded_custom = json.dumps(data, cls=CacheJSONEncoder)
    encoded_standard = json.dumps(data)

    assert encoded_custom == encoded_standard


# ============================================================================
# CacheJSONEncoder - Error Handling
# ============================================================================


def test_encode_unsupported_type_fallback():
    """
    Test that unsupported types raise TypeError (expected behavior).

    Scenario:
        - Object without __dict__, model_dump(), or isoformat()
        - Should raise TypeError (standard json.dumps behavior)

    Validates: Graceful failure for truly unsupported types
    """

    class UnsupportedClass:
        """Class without serialization support."""

        def __init__(self):
            self.data = "test"

    data = {"unsupported": UnsupportedClass()}

    with pytest.raises(TypeError):
        json.dumps(data, cls=CacheJSONEncoder)


def test_encode_circular_reference_protection():
    """
    Test that circular references are caught (Pydantic prevents this).

    Scenario:
        - Attempt to create circular reference in dict
        - Should raise ValueError (standard json.dumps behavior)

    Validates: Protection against infinite recursion
    """
    # Create circular reference
    data = {"key": "value"}
    data["self"] = data

    with pytest.raises(ValueError, match="Circular reference"):
        json.dumps(data, cls=CacheJSONEncoder)
