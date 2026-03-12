"""
Schema Extractor - Extract JSON Schema from formatter FIELD_EXTRACTORS.

This module automatically extracts JSON schemas from formatter classes by analyzing
their FIELD_EXTRACTORS and OPERATION_DEFAULT_FIELDS attributes.

Phase 2.1 - Schema Mismatch Resolution (Issue #32)

Problem:
    Tool response schemas are defined in formatters (via FIELD_EXTRACTORS),
    but are not accessible to the planner. This leads to schema drift where
    the planner guesses field names incorrectly.

Solution:
    Auto-extract schemas from formatters using type inference on extractor functions.
    This ensures schemas stay synchronized with actual tool responses.

Algorithm:
    1. Get FIELD_EXTRACTORS dict from formatter class
    2. Get OPERATION_DEFAULT_FIELDS for specific operation (search/list/details)
    3. For each field in operation:
       a. Call extractor with mock data
       b. Infer type from return value (list/dict/string/number)
       c. Recursively extract nested field schemas
    4. Build JSON Schema object
    5. Return complete schema

Type Inference:
    - list → {"type": "array", "items": <inferred from first item>}
    - dict → {"type": "object", "properties": <inferred recursively>}
    - str → {"type": "string"}
    - int/float → {"type": "number"}
    - bool → {"type": "boolean"}
    - None → {"type": "null"}

Usage:
    >>> from src.domains.agents.tools.formatters import ContactsFormatter
    >>> extractor = SchemaExtractor()
    >>> schema = extractor.extract_from_formatter(ContactsFormatter, operation="search")
    >>> assert "emailAddresses" in schema["properties"]  # Not "emails"!

Best Practices (2025):
    - Type inference from runtime values
    - Comprehensive mock data for accuracy
    - Defensive error handling
    - Structured logging for debugging

Author: Phase 2.1 Implementation
Created: 2025-11-23
"""

from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SchemaExtractor:
    """
    Extract JSON Schema from formatter FIELD_EXTRACTORS.

    This class analyzes formatter classes to automatically generate JSON schemas
    describing tool response structures. It uses type inference by calling
    extractor functions with mock data and inspecting return values.

    Attributes:
        MOCK_CONTACT: Mock Google Contacts API person object for type inference
        MOCK_EMAIL: Mock Gmail API message object for type inference

    Examples:
        >>> # Extract schema from ContactsFormatter
        >>> extractor = SchemaExtractor()
        >>> schema = extractor.extract_from_formatter(
        ...     ContactsFormatter,
        ...     operation="search"
        ... )
        >>>
        >>> # Verify schema structure
        >>> assert schema["type"] == "object"
        >>> assert "emailAddresses" in schema["properties"]
        >>> assert schema["properties"]["emailAddresses"]["type"] == "array"
        >>>
        >>> # Verify nested structure
        >>> email_items = schema["properties"]["emailAddresses"]["items"]
        >>> assert "value" in email_items["properties"]
        >>> assert email_items["properties"]["value"]["type"] == "string"
    """

    # Mock Google Contacts API person object
    # Reference: https://developers.google.com/people/api/rest/v1/people
    MOCK_CONTACT = {
        "resourceName": "people/c123456789012345678",
        "etag": "%EgUBAgMEB…",
        "names": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "displayName": "Test User",
                "familyName": "User",
                "givenName": "Test",
                "displayNameLastFirst": "User, Test",
            }
        ],
        "emailAddresses": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "value": "test@example.com",
                "type": "home",
            },
            {
                "metadata": {"primary": False, "source": {"type": "CONTACT", "id": "123"}},
                "value": "test.work@company.com",
                "type": "work",
            },
        ],
        "phoneNumbers": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "value": "+33123456789",
                "type": "mobile",
                "canonicalForm": "+33123456789",
            }
        ],
        "organizations": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "name": "Acme Corp",
                "title": "Senior Engineer",
                "department": "Engineering",
                "current": True,
            }
        ],
        "addresses": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "formattedValue": "123 Main St\n75001 Paris\nFrance",
                "type": "home",
                "streetAddress": "123 Main St",
                "city": "Paris",
                "postalCode": "75001",
                "country": "France",
            }
        ],
        "birthdays": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "date": {"year": 1990, "month": 6, "day": 15},
            }
        ],
        "relations": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "person": "Jane Doe",
                "type": "spouse",
            }
        ],
        "events": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "date": {"year": 2020, "month": 6, "day": 1},
                "type": "anniversary",
            }
        ],
        "photos": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "url": "https://lh3.googleusercontent.com/contacts/photo.jpg",
            }
        ],
        "nicknames": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "value": "Testy",
            }
        ],
        "biographies": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "value": "Software engineer passionate about clean code.",
                "contentType": "TEXT_PLAIN",
            }
        ],
        "occupations": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "value": "Software Engineer",
            }
        ],
        "interests": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "value": "Coding",
            }
        ],
        "skills": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "value": "Python",
            }
        ],
        "locations": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "value": "Paris, France",
                "type": "desk",
            }
        ],
        "imClients": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "username": "test_user",
                "type": "slack",
                "protocol": "slack",
            }
        ],
        "calendarUrls": [
            {
                "metadata": {"primary": True, "source": {"type": "CONTACT", "id": "123"}},
                "url": "https://calendar.google.com/calendar/u/0/embed?src=test@example.com",
                "type": "work",
            }
        ],
    }

    # Mock Gmail API message object
    # Reference: https://developers.google.com/gmail/api/reference/rest/v1/users.messages
    MOCK_EMAIL = {
        "id": "18f1234567890abcd",
        "threadId": "18f1234567890abcd",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "This is a test email message...",
        "historyId": "123456",
        "internalDate": "1700000000000",
        "payload": {
            "partId": "",
            "mimeType": "multipart/alternative",
            "filename": "",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Subject", "value": "Test Email Subject"},
                {"name": "Date", "value": "Mon, 20 Nov 2023 10:00:00 +0000"},
            ],
            "body": {"size": 1234},
        },
        "sizeEstimate": 5678,
    }

    @staticmethod
    def extract_from_formatter(
        formatter_class: type,
        operation: str = "search",
    ) -> dict[str, Any]:
        """
        Extract JSON Schema from formatter class.

        Analyzes a formatter's FIELD_EXTRACTORS to generate a JSON schema
        describing the tool's response structure for a specific operation.

        Args:
            formatter_class: Formatter class (e.g., ContactsFormatter, EmailFormatter)
                Must have FIELD_EXTRACTORS dict and OPERATION_DEFAULT_FIELDS dict
            operation: Operation type ("search", "list", "details")
                Determines which fields to extract based on OPERATION_DEFAULT_FIELDS

        Returns:
            JSON Schema dict with type="object" and properties for each field

        Raises:
            AttributeError: If formatter_class missing required attributes
            Exception: If extractor function fails (logged as warning, continues)

        Algorithm:
            1. Get FIELD_EXTRACTORS from formatter
            2. Get fields for operation from OPERATION_DEFAULT_FIELDS
            3. For each field:
               - Call extractor with mock data
               - Infer schema from return value
               - Add to properties dict
            4. Return complete schema

        Examples:
            >>> from src.domains.agents.tools.formatters import ContactsFormatter
            >>> extractor = SchemaExtractor()
            >>>
            >>> # Extract search schema
            >>> search_schema = extractor.extract_from_formatter(
            ...     ContactsFormatter,
            ...     operation="search"
            ... )
            >>> assert "emailAddresses" in search_schema["properties"]
            >>>
            >>> # Extract details schema (more fields)
            >>> details_schema = extractor.extract_from_formatter(
            ...     ContactsFormatter,
            ...     operation="details"
            ... )
            >>> assert len(details_schema["properties"]) > len(search_schema["properties"])
        """
        # Get formatter attributes
        field_extractors = getattr(formatter_class, "FIELD_EXTRACTORS", {})
        operation_fields = getattr(formatter_class, "OPERATION_DEFAULT_FIELDS", {})

        # Get fields for this operation
        fields_to_extract = operation_fields.get(
            operation, getattr(formatter_class, "DEFAULT_FIELDS", [])
        )

        # Build item schema (individual contact/email/etc.)
        item_schema = {"type": "object", "properties": {}}

        # Extract schema for each field
        for field_name in fields_to_extract:
            if field_name in field_extractors:
                extractor_fn = field_extractors[field_name]
                field_schema = SchemaExtractor._analyze_extractor(extractor_fn, field_name)
                item_schema["properties"][field_name] = field_schema
            else:
                # Field without extractor - default to string
                logger.debug(
                    "field_without_extractor",
                    field_name=field_name,
                    formatter=formatter_class.__name__,
                    message=f"Field {field_name} has no extractor, defaulting to string",
                )
                item_schema["properties"][field_name] = {"type": "string"}

        # Wrap in response structure (e.g., {"contacts": [...]} for ContactsFormatter)
        # Get items key from formatter instance
        try:
            # Instantiate formatter to get items_key
            # Note: formatter.__init__ expects tool_name and operation parameters
            # Use dummy tool_name for schema extraction
            formatter_instance = formatter_class(tool_name="schema_extractor", operation=operation)
            items_key = formatter_instance._get_items_key()

            # Wrap item schema in array under items_key
            wrapped_schema = {
                "type": "object",
                "properties": {
                    items_key: {
                        "type": "array",
                        "items": item_schema,
                    }
                },
            }

            logger.info(
                "schema_extracted",
                formatter=formatter_class.__name__,
                operation=operation,
                fields_count=len(item_schema["properties"]),
                fields=list(item_schema["properties"].keys()),
                items_key=items_key,
                message=f"Extracted schema for {formatter_class.__name__}.{operation} (wrapped in '{items_key}')",
            )

            return wrapped_schema

        except Exception as e:
            # Fallback: return unwrapped schema if instantiation fails
            logger.warning(
                "schema_wrapping_failed",
                formatter=formatter_class.__name__,
                operation=operation,
                error=str(e),
                message="Could not wrap schema in items_key, returning unwrapped schema",
            )

            logger.info(
                "schema_extracted",
                formatter=formatter_class.__name__,
                operation=operation,
                fields_count=len(item_schema["properties"]),
                fields=list(item_schema["properties"].keys()),
                message=f"Extracted schema for {formatter_class.__name__}.{operation}",
            )

            return item_schema

    @staticmethod
    def _analyze_extractor(extractor: Callable, field_name: str) -> dict[str, Any]:
        """
        Analyze extractor function to infer schema.

        Calls the extractor with mock data and infers the JSON schema
        from the return value's type and structure.

        Args:
            extractor: Extractor function (e.g., ContactsFormatter._extract_emails)
            field_name: Field name (for logging)

        Returns:
            JSON Schema dict for this field

        Algorithm:
            1. Call extractor with MOCK_CONTACT
            2. Infer schema from return value type
            3. Return schema dict

        Fallback:
            If extractor raises exception, logs warning and returns {"type": "string"}

        Examples:
            >>> # Extractor that returns list of dicts
            >>> def extract_emails(person):
            ...     return [{"value": "test@example.com", "type": "home"}]
            >>>
            >>> schema = SchemaExtractor._analyze_extractor(extract_emails, "emailAddresses")
            >>> assert schema == {
            ...     "type": "array",
            ...     "items": {
            ...         "type": "object",
            ...         "properties": {
            ...             "value": {"type": "string"},
            ...             "type": {"type": "string"}
            ...         }
            ...     }
            ... }
        """
        try:
            # Call extractor with mock data
            result = extractor(SchemaExtractor.MOCK_CONTACT)

            # Infer schema from result
            field_schema = SchemaExtractor._infer_schema_from_value(result)

            logger.debug(
                "extractor_analyzed",
                field_name=field_name,
                result_type=type(result).__name__,
                schema_type=field_schema.get("type"),
                message=f"Analyzed extractor for {field_name}",
            )

            return field_schema

        except Exception as e:
            # Extractor failed - log warning and fallback to string
            logger.warning(
                "extractor_analysis_failed",
                field_name=field_name,
                error=str(e),
                error_type=type(e).__name__,
                message=f"Extractor for {field_name} failed, falling back to string",
            )

            # Fallback to string type
            return {"type": "string"}

    @staticmethod
    def _infer_schema_from_value(value: Any) -> dict[str, Any]:
        """
        Infer JSON Schema from Python value (recursive).

        Analyzes a Python value and generates the corresponding JSON schema.
        Handles nested structures (lists of dicts, dicts of lists, etc.).

        Args:
            value: Python value to analyze

        Returns:
            JSON Schema dict

        Type Mapping:
            - list → {"type": "array", "items": <schema of first item>}
            - dict → {"type": "object", "properties": {k: <schema of v>}}
            - str → {"type": "string"}
            - bool → {"type": "boolean"}
            - int/float → {"type": "number"}
            - None → {"type": "null"}
            - other → {"type": "string"} (fallback)

        Examples:
            >>> # String
            >>> SchemaExtractor._infer_schema_from_value("test")
            {'type': 'string'}
            >>>
            >>> # List of strings
            >>> SchemaExtractor._infer_schema_from_value(["a", "b"])
            {'type': 'array', 'items': {'type': 'string'}}
            >>>
            >>> # List of dicts
            >>> SchemaExtractor._infer_schema_from_value([
            ...     {"value": "test@example.com", "type": "home"}
            ... ])
            {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'value': {'type': 'string'},
                        'type': {'type': 'string'}
                    }
                }
            }
            >>>
            >>> # Nested structure
            >>> SchemaExtractor._infer_schema_from_value({
            ...     "contacts": [{"name": "John"}]
            ... })
            {
                'type': 'object',
                'properties': {
                    'contacts': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'name': {'type': 'string'}
                            }
                        }
                    }
                }
            }
        """
        # List → array
        if isinstance(value, list):
            if value:
                # Non-empty list - infer items schema from first item
                item_schema = SchemaExtractor._infer_schema_from_value(value[0])
                return {"type": "array", "items": item_schema}
            else:
                # Empty list - can't infer items schema
                return {"type": "array", "items": {}}

        # Dict → object
        elif isinstance(value, dict):
            # Build properties schema recursively
            properties = {}
            for key, val in value.items():
                properties[key] = SchemaExtractor._infer_schema_from_value(val)

            return {"type": "object", "properties": properties}

        # Primitive types
        elif isinstance(value, str):
            return {"type": "string"}

        elif isinstance(value, bool):
            # Note: Check bool before int (bool is subclass of int in Python)
            return {"type": "boolean"}

        elif isinstance(value, int | float):
            return {"type": "number"}

        elif value is None:
            return {"type": "null"}

        # Unknown type - fallback to string
        else:
            logger.debug(
                "unknown_type_inferred",
                value_type=type(value).__name__,
                message=f"Unknown type {type(value).__name__}, falling back to string",
            )
            return {"type": "string"}
