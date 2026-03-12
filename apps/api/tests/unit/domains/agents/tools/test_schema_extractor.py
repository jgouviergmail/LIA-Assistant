"""
Unit tests for schema extractor.

Tests for SchemaExtractor class that extracts JSON schemas from formatter classes
by analyzing their FIELD_EXTRACTORS and OPERATION_DEFAULT_FIELDS attributes.
"""

from src.domains.agents.tools.schema_extractor import SchemaExtractor

# ============================================================================
# Tests for MOCK_CONTACT constant
# ============================================================================


class TestMockContact:
    """Tests for MOCK_CONTACT constant structure."""

    def test_has_resource_name(self):
        """Test that MOCK_CONTACT has resourceName field."""
        assert "resourceName" in SchemaExtractor.MOCK_CONTACT
        assert SchemaExtractor.MOCK_CONTACT["resourceName"].startswith("people/")

    def test_has_names(self):
        """Test that MOCK_CONTACT has names field with proper structure."""
        assert "names" in SchemaExtractor.MOCK_CONTACT
        assert isinstance(SchemaExtractor.MOCK_CONTACT["names"], list)
        assert len(SchemaExtractor.MOCK_CONTACT["names"]) > 0
        assert "displayName" in SchemaExtractor.MOCK_CONTACT["names"][0]

    def test_has_email_addresses(self):
        """Test that MOCK_CONTACT has emailAddresses field."""
        assert "emailAddresses" in SchemaExtractor.MOCK_CONTACT
        assert isinstance(SchemaExtractor.MOCK_CONTACT["emailAddresses"], list)
        assert "value" in SchemaExtractor.MOCK_CONTACT["emailAddresses"][0]

    def test_has_phone_numbers(self):
        """Test that MOCK_CONTACT has phoneNumbers field."""
        assert "phoneNumbers" in SchemaExtractor.MOCK_CONTACT
        assert isinstance(SchemaExtractor.MOCK_CONTACT["phoneNumbers"], list)
        assert "value" in SchemaExtractor.MOCK_CONTACT["phoneNumbers"][0]

    def test_has_organizations(self):
        """Test that MOCK_CONTACT has organizations field."""
        assert "organizations" in SchemaExtractor.MOCK_CONTACT
        assert isinstance(SchemaExtractor.MOCK_CONTACT["organizations"], list)
        assert "name" in SchemaExtractor.MOCK_CONTACT["organizations"][0]

    def test_has_addresses(self):
        """Test that MOCK_CONTACT has addresses field."""
        assert "addresses" in SchemaExtractor.MOCK_CONTACT
        assert isinstance(SchemaExtractor.MOCK_CONTACT["addresses"], list)
        assert "formattedValue" in SchemaExtractor.MOCK_CONTACT["addresses"][0]

    def test_has_birthdays(self):
        """Test that MOCK_CONTACT has birthdays field."""
        assert "birthdays" in SchemaExtractor.MOCK_CONTACT
        assert isinstance(SchemaExtractor.MOCK_CONTACT["birthdays"], list)
        assert "date" in SchemaExtractor.MOCK_CONTACT["birthdays"][0]

    def test_has_relations(self):
        """Test that MOCK_CONTACT has relations field."""
        assert "relations" in SchemaExtractor.MOCK_CONTACT
        assert isinstance(SchemaExtractor.MOCK_CONTACT["relations"], list)
        assert "person" in SchemaExtractor.MOCK_CONTACT["relations"][0]

    def test_has_photos(self):
        """Test that MOCK_CONTACT has photos field."""
        assert "photos" in SchemaExtractor.MOCK_CONTACT
        assert isinstance(SchemaExtractor.MOCK_CONTACT["photos"], list)
        assert "url" in SchemaExtractor.MOCK_CONTACT["photos"][0]


# ============================================================================
# Tests for MOCK_EMAIL constant
# ============================================================================


class TestMockEmail:
    """Tests for MOCK_EMAIL constant structure."""

    def test_has_id(self):
        """Test that MOCK_EMAIL has id field."""
        assert "id" in SchemaExtractor.MOCK_EMAIL
        assert isinstance(SchemaExtractor.MOCK_EMAIL["id"], str)

    def test_has_thread_id(self):
        """Test that MOCK_EMAIL has threadId field."""
        assert "threadId" in SchemaExtractor.MOCK_EMAIL
        assert isinstance(SchemaExtractor.MOCK_EMAIL["threadId"], str)

    def test_has_label_ids(self):
        """Test that MOCK_EMAIL has labelIds field."""
        assert "labelIds" in SchemaExtractor.MOCK_EMAIL
        assert isinstance(SchemaExtractor.MOCK_EMAIL["labelIds"], list)
        assert "INBOX" in SchemaExtractor.MOCK_EMAIL["labelIds"]

    def test_has_snippet(self):
        """Test that MOCK_EMAIL has snippet field."""
        assert "snippet" in SchemaExtractor.MOCK_EMAIL
        assert isinstance(SchemaExtractor.MOCK_EMAIL["snippet"], str)

    def test_has_payload(self):
        """Test that MOCK_EMAIL has payload field with headers."""
        assert "payload" in SchemaExtractor.MOCK_EMAIL
        assert "headers" in SchemaExtractor.MOCK_EMAIL["payload"]
        assert isinstance(SchemaExtractor.MOCK_EMAIL["payload"]["headers"], list)

    def test_has_size_estimate(self):
        """Test that MOCK_EMAIL has sizeEstimate field."""
        assert "sizeEstimate" in SchemaExtractor.MOCK_EMAIL
        assert isinstance(SchemaExtractor.MOCK_EMAIL["sizeEstimate"], int)


# ============================================================================
# Tests for _infer_schema_from_value
# ============================================================================


class TestInferSchemaFromValuePrimitives:
    """Tests for _infer_schema_from_value with primitive types."""

    def test_infers_string_type(self):
        """Test that string value infers to string type."""
        result = SchemaExtractor._infer_schema_from_value("test")
        assert result == {"type": "string"}

    def test_infers_empty_string(self):
        """Test that empty string still infers to string type."""
        result = SchemaExtractor._infer_schema_from_value("")
        assert result == {"type": "string"}

    def test_infers_boolean_true(self):
        """Test that True infers to boolean type."""
        result = SchemaExtractor._infer_schema_from_value(True)
        assert result == {"type": "boolean"}

    def test_infers_boolean_false(self):
        """Test that False infers to boolean type."""
        result = SchemaExtractor._infer_schema_from_value(False)
        assert result == {"type": "boolean"}

    def test_infers_integer_type(self):
        """Test that integer value infers to number type."""
        result = SchemaExtractor._infer_schema_from_value(42)
        assert result == {"type": "number"}

    def test_infers_float_type(self):
        """Test that float value infers to number type."""
        result = SchemaExtractor._infer_schema_from_value(3.14)
        assert result == {"type": "number"}

    def test_infers_zero(self):
        """Test that zero infers to number type."""
        result = SchemaExtractor._infer_schema_from_value(0)
        assert result == {"type": "number"}

    def test_infers_negative_number(self):
        """Test that negative number infers to number type."""
        result = SchemaExtractor._infer_schema_from_value(-123)
        assert result == {"type": "number"}

    def test_infers_none_type(self):
        """Test that None infers to null type."""
        result = SchemaExtractor._infer_schema_from_value(None)
        assert result == {"type": "null"}


class TestInferSchemaFromValueList:
    """Tests for _infer_schema_from_value with list types."""

    def test_infers_empty_list(self):
        """Test that empty list infers to array with empty items."""
        result = SchemaExtractor._infer_schema_from_value([])
        assert result == {"type": "array", "items": {}}

    def test_infers_list_of_strings(self):
        """Test that list of strings infers properly."""
        result = SchemaExtractor._infer_schema_from_value(["a", "b", "c"])
        assert result == {"type": "array", "items": {"type": "string"}}

    def test_infers_list_of_numbers(self):
        """Test that list of numbers infers properly."""
        result = SchemaExtractor._infer_schema_from_value([1, 2, 3])
        assert result == {"type": "array", "items": {"type": "number"}}

    def test_infers_list_of_booleans(self):
        """Test that list of booleans infers properly."""
        result = SchemaExtractor._infer_schema_from_value([True, False])
        assert result == {"type": "array", "items": {"type": "boolean"}}

    def test_infers_list_of_dicts(self):
        """Test that list of dicts infers properly."""
        result = SchemaExtractor._infer_schema_from_value(
            [{"value": "test@example.com", "type": "home"}]
        )

        assert result["type"] == "array"
        assert result["items"]["type"] == "object"
        assert "value" in result["items"]["properties"]
        assert "type" in result["items"]["properties"]

    def test_uses_first_item_for_schema(self):
        """Test that schema is inferred from first item only."""
        # Heterogeneous list - only first item matters
        result = SchemaExtractor._infer_schema_from_value(["string", 123, True])
        assert result == {"type": "array", "items": {"type": "string"}}


class TestInferSchemaFromValueDict:
    """Tests for _infer_schema_from_value with dict types."""

    def test_infers_empty_dict(self):
        """Test that empty dict infers to object with empty properties."""
        result = SchemaExtractor._infer_schema_from_value({})
        assert result == {"type": "object", "properties": {}}

    def test_infers_simple_dict(self):
        """Test that simple dict infers properly."""
        result = SchemaExtractor._infer_schema_from_value(
            {
                "name": "John",
                "age": 30,
            }
        )

        assert result["type"] == "object"
        assert result["properties"]["name"] == {"type": "string"}
        assert result["properties"]["age"] == {"type": "number"}

    def test_infers_nested_dict(self):
        """Test that nested dict infers recursively."""
        result = SchemaExtractor._infer_schema_from_value(
            {
                "metadata": {
                    "primary": True,
                    "source": {"type": "CONTACT", "id": "123"},
                }
            }
        )

        assert result["type"] == "object"
        assert result["properties"]["metadata"]["type"] == "object"
        nested = result["properties"]["metadata"]["properties"]
        assert nested["primary"] == {"type": "boolean"}
        assert nested["source"]["type"] == "object"

    def test_infers_dict_with_list_value(self):
        """Test that dict with list value infers properly."""
        result = SchemaExtractor._infer_schema_from_value({"contacts": [{"name": "John"}]})

        assert result["type"] == "object"
        assert result["properties"]["contacts"]["type"] == "array"
        assert result["properties"]["contacts"]["items"]["type"] == "object"


class TestInferSchemaFromValueComplex:
    """Tests for _infer_schema_from_value with complex nested structures."""

    def test_infers_google_contact_like_structure(self):
        """Test inference of Google Contacts API-like structure."""
        contact = {
            "resourceName": "people/c123",
            "names": [{"displayName": "John Doe", "givenName": "John"}],
            "emailAddresses": [{"value": "john@example.com", "type": "home"}],
        }

        result = SchemaExtractor._infer_schema_from_value(contact)

        assert result["type"] == "object"
        assert result["properties"]["resourceName"] == {"type": "string"}
        assert result["properties"]["names"]["type"] == "array"
        assert result["properties"]["emailAddresses"]["type"] == "array"

    def test_infers_gmail_message_like_structure(self):
        """Test inference of Gmail API-like structure."""
        message = {
            "id": "msg123",
            "labelIds": ["INBOX", "UNREAD"],
            "payload": {
                "headers": [{"name": "Subject", "value": "Test"}],
            },
        }

        result = SchemaExtractor._infer_schema_from_value(message)

        assert result["type"] == "object"
        assert result["properties"]["id"] == {"type": "string"}
        assert result["properties"]["labelIds"]["type"] == "array"
        assert result["properties"]["payload"]["type"] == "object"


class TestInferSchemaFromValueUnknownTypes:
    """Tests for _infer_schema_from_value with unknown/special types."""

    def test_infers_tuple_as_string_fallback(self):
        """Test that tuple falls back to string type."""
        result = SchemaExtractor._infer_schema_from_value((1, 2, 3))
        assert result == {"type": "string"}

    def test_infers_set_as_string_fallback(self):
        """Test that set falls back to string type."""
        result = SchemaExtractor._infer_schema_from_value({1, 2, 3})
        # Note: set is not dict, so falls back to string
        assert result == {"type": "string"}

    def test_infers_custom_object_as_string_fallback(self):
        """Test that custom object falls back to string type."""

        class CustomClass:
            pass

        result = SchemaExtractor._infer_schema_from_value(CustomClass())
        assert result == {"type": "string"}


# ============================================================================
# Tests for _analyze_extractor
# ============================================================================


class TestAnalyzeExtractor:
    """Tests for _analyze_extractor method."""

    def test_analyzes_extractor_returning_string(self):
        """Test analyzing extractor that returns string."""

        def extractor(person):
            return person.get("resourceName", "")

        result = SchemaExtractor._analyze_extractor(extractor, "resourceName")
        assert result == {"type": "string"}

    def test_analyzes_extractor_returning_list(self):
        """Test analyzing extractor that returns list of dicts."""

        def extractor(person):
            return person.get("emailAddresses", [])

        result = SchemaExtractor._analyze_extractor(extractor, "emailAddresses")
        assert result["type"] == "array"
        assert result["items"]["type"] == "object"

    def test_analyzes_extractor_returning_dict(self):
        """Test analyzing extractor that returns dict."""

        def extractor(person):
            return {"key": "value", "count": 5}

        result = SchemaExtractor._analyze_extractor(extractor, "metadata")
        assert result["type"] == "object"
        assert result["properties"]["key"] == {"type": "string"}
        assert result["properties"]["count"] == {"type": "number"}

    def test_analyzes_extractor_returning_none(self):
        """Test analyzing extractor that returns None."""

        def extractor(person):
            return None

        result = SchemaExtractor._analyze_extractor(extractor, "optional_field")
        assert result == {"type": "null"}

    def test_fallback_when_extractor_raises(self):
        """Test fallback to string when extractor raises exception."""

        def failing_extractor(person):
            raise ValueError("Intentional failure")

        result = SchemaExtractor._analyze_extractor(failing_extractor, "broken_field")
        assert result == {"type": "string"}

    def test_fallback_when_extractor_has_wrong_signature(self):
        """Test fallback when extractor doesn't accept person argument."""

        def bad_extractor():
            return "value"

        result = SchemaExtractor._analyze_extractor(bad_extractor, "no_args_field")
        assert result == {"type": "string"}


# ============================================================================
# Tests for extract_from_formatter
# ============================================================================


class TestExtractFromFormatterBasic:
    """Tests for extract_from_formatter method - basic scenarios."""

    def test_extracts_schema_with_field_extractors(self):
        """Test extraction from formatter with FIELD_EXTRACTORS."""

        class MockFormatter:
            FIELD_EXTRACTORS = {
                "name": lambda p: p.get("names", [{}])[0].get("displayName", ""),
                "email": lambda p: p.get("emailAddresses", [{}])[0].get("value", ""),
            }
            OPERATION_DEFAULT_FIELDS = {
                "search": ["name", "email"],
            }

            def __init__(self, tool_name, operation):
                pass

            def _get_items_key(self):
                return "items"

        result = SchemaExtractor.extract_from_formatter(MockFormatter, "search")

        assert result["type"] == "object"
        assert "items" in result["properties"]
        assert result["properties"]["items"]["type"] == "array"
        item_props = result["properties"]["items"]["items"]["properties"]
        assert "name" in item_props
        assert "email" in item_props

    def test_extracts_schema_with_different_operations(self):
        """Test that different operations extract different fields."""

        class MockFormatter:
            FIELD_EXTRACTORS = {
                "name": lambda p: "",
                "email": lambda p: "",
                "phone": lambda p: "",
                "address": lambda p: "",
            }
            OPERATION_DEFAULT_FIELDS = {
                "search": ["name", "email"],
                "details": ["name", "email", "phone", "address"],
            }

            def __init__(self, tool_name, operation):
                pass

            def _get_items_key(self):
                return "contacts"

        search_result = SchemaExtractor.extract_from_formatter(MockFormatter, "search")
        details_result = SchemaExtractor.extract_from_formatter(MockFormatter, "details")

        search_props = search_result["properties"]["contacts"]["items"]["properties"]
        details_props = details_result["properties"]["contacts"]["items"]["properties"]

        assert len(search_props) == 2
        assert len(details_props) == 4

    def test_handles_field_without_extractor(self):
        """Test that fields without extractor default to string type."""

        class MockFormatter:
            FIELD_EXTRACTORS = {
                "name": lambda p: "",
            }
            OPERATION_DEFAULT_FIELDS = {
                "search": ["name", "missing_field"],
            }

            def __init__(self, tool_name, operation):
                pass

            def _get_items_key(self):
                return "items"

        result = SchemaExtractor.extract_from_formatter(MockFormatter, "search")

        item_props = result["properties"]["items"]["items"]["properties"]
        assert "name" in item_props
        assert "missing_field" in item_props
        assert item_props["missing_field"] == {"type": "string"}

    def test_uses_default_fields_for_unknown_operation(self):
        """Test that DEFAULT_FIELDS is used for unknown operation."""

        class MockFormatter:
            FIELD_EXTRACTORS = {
                "id": lambda p: "",
                "default_field": lambda p: "",
            }
            OPERATION_DEFAULT_FIELDS = {
                "search": ["id"],
            }
            DEFAULT_FIELDS = ["default_field"]

            def __init__(self, tool_name, operation):
                pass

            def _get_items_key(self):
                return "items"

        result = SchemaExtractor.extract_from_formatter(MockFormatter, "unknown_op")

        item_props = result["properties"]["items"]["items"]["properties"]
        assert "default_field" in item_props
        assert "id" not in item_props


class TestExtractFromFormatterFallback:
    """Tests for extract_from_formatter fallback behavior."""

    def test_returns_unwrapped_when_instantiation_fails(self):
        """Test that unwrapped schema is returned when formatter instantiation fails."""

        class FailingFormatter:
            FIELD_EXTRACTORS = {
                "name": lambda p: "",
            }
            OPERATION_DEFAULT_FIELDS = {
                "search": ["name"],
            }

            def __init__(self, tool_name, operation):
                raise ValueError("Cannot instantiate")

        result = SchemaExtractor.extract_from_formatter(FailingFormatter, "search")

        # Should return unwrapped item schema
        assert result["type"] == "object"
        assert "properties" in result
        assert "name" in result["properties"]
        # Should NOT have the items_key wrapper
        assert "items" not in result.get("properties", {})

    def test_handles_missing_operation_default_fields(self):
        """Test handling when OPERATION_DEFAULT_FIELDS is missing."""

        class MinimalFormatter:
            FIELD_EXTRACTORS = {
                "id": lambda p: "",
            }
            DEFAULT_FIELDS = ["id"]

            def __init__(self, tool_name, operation):
                pass

            def _get_items_key(self):
                return "items"

        # Should not raise, should use DEFAULT_FIELDS
        result = SchemaExtractor.extract_from_formatter(MinimalFormatter, "search")

        item_props = result["properties"]["items"]["items"]["properties"]
        assert "id" in item_props


class TestExtractFromFormatterItemsKey:
    """Tests for items_key handling in extract_from_formatter."""

    def test_uses_items_key_from_formatter(self):
        """Test that items_key from formatter instance is used."""

        class ContactsLikeFormatter:
            FIELD_EXTRACTORS = {"name": lambda p: ""}
            OPERATION_DEFAULT_FIELDS = {"search": ["name"]}

            def __init__(self, tool_name, operation):
                pass

            def _get_items_key(self):
                return "contacts"

        result = SchemaExtractor.extract_from_formatter(ContactsLikeFormatter, "search")
        assert "contacts" in result["properties"]

    def test_different_formatters_use_different_keys(self):
        """Test that different formatters can use different items_key."""

        class EmailsFormatter:
            FIELD_EXTRACTORS = {"subject": lambda p: ""}
            OPERATION_DEFAULT_FIELDS = {"list": ["subject"]}

            def __init__(self, tool_name, operation):
                pass

            def _get_items_key(self):
                return "emails"

        class PlacesFormatter:
            FIELD_EXTRACTORS = {"name": lambda p: ""}
            OPERATION_DEFAULT_FIELDS = {"search": ["name"]}

            def __init__(self, tool_name, operation):
                pass

            def _get_items_key(self):
                return "places"

        emails_result = SchemaExtractor.extract_from_formatter(EmailsFormatter, "list")
        places_result = SchemaExtractor.extract_from_formatter(PlacesFormatter, "search")

        assert "emails" in emails_result["properties"]
        assert "places" in places_result["properties"]


class TestExtractFromFormatterEdgeCases:
    """Tests for edge cases in extract_from_formatter."""

    def test_handles_empty_field_extractors(self):
        """Test handling of empty FIELD_EXTRACTORS."""

        class EmptyFormatter:
            FIELD_EXTRACTORS = {}
            OPERATION_DEFAULT_FIELDS = {"search": []}

            def __init__(self, tool_name, operation):
                pass

            def _get_items_key(self):
                return "items"

        result = SchemaExtractor.extract_from_formatter(EmptyFormatter, "search")

        assert result["type"] == "object"
        item_schema = result["properties"]["items"]["items"]
        assert item_schema["properties"] == {}

    def test_handles_extractor_using_mock_contact(self):
        """Test that extractors receive MOCK_CONTACT data."""

        class RealExtractorFormatter:
            FIELD_EXTRACTORS = {
                "displayName": lambda p: p.get("names", [{}])[0].get("displayName", ""),
                "primaryEmail": lambda p: p.get("emailAddresses", [{}])[0].get("value", ""),
            }
            OPERATION_DEFAULT_FIELDS = {"search": ["displayName", "primaryEmail"]}

            def __init__(self, tool_name, operation):
                pass

            def _get_items_key(self):
                return "contacts"

        result = SchemaExtractor.extract_from_formatter(RealExtractorFormatter, "search")

        item_props = result["properties"]["contacts"]["items"]["properties"]
        # These should be inferred as strings from MOCK_CONTACT
        assert item_props["displayName"] == {"type": "string"}
        assert item_props["primaryEmail"] == {"type": "string"}
