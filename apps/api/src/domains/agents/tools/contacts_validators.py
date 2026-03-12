"""
Validators and Pydantic wrappers for Google Contacts tools.

This module provides validation functions that wrap existing tools
to ensure:
- Input validation with Pydantic models
- Output normalization to ToolResponse format
- Backward compatibility with existing implementation

Architecture:
- validate_and_call_X(): Wrappers that encapsulate existing tools
- parse_X_response(): Parsers that convert JSON to Pydantic models

Usage in future refactored tools:
    from src.domains.agents.tools.contacts_validators import (
        validate_search_contacts_input,
        parse_search_contacts_response,
    )

    async def search_contacts_tool_v2(...) -> dict:
        # Validate input
        input_data = validate_search_contacts_input(query, max_results, ...)

        # Execute
        result = await do_search(input_data)

        # Parse and validate output
        output = parse_search_contacts_response(result)

        # Return standardized
        return create_success_response(data=output.model_dump())

Compliance: Pydantic v2, backward compatible with existing tools
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.core.field_names import FIELD_METADATA, FIELD_RESOURCE_NAME

from .common import (
    ToolErrorCode,
    create_error_response,
    create_success_response,
    parse_list_field,
    safe_parse_json_strict,
    validate_tool_input,
)
from .contacts_models import (
    ContactAddress,
    ContactBasic,
    ContactDetailed,
    ContactEmail,
    ContactName,
    ContactPhone,
    GetContactDetailsInput,
    GetContactDetailsOutput,
    ListContactsInput,
    ListContactsOutput,
    SearchContactsInput,
    SearchContactsOutput,
)

# ============================================================================
# Input Validators
# ============================================================================


def validate_search_contacts_input(
    query: str,
    max_results: int | None = None,
    fields: list[str] | None = None,
    force_refresh: bool = False,
) -> SearchContactsInput:
    """
    Validate search_contacts_tool parameters.

    Args:
        query: Search term
        max_results: Maximum number of results (1-50)
        fields: Fields to include
        force_refresh: Force cache refresh

    Returns:
        Validated SearchContactsInput

    Raises:
        ValueError: If validation fails

    Examples:
        >>> input_data = validate_search_contacts_input("John", max_results=20)
        >>> input_data.query
        'John'
        >>> input_data.max_results
        20
    """
    return validate_tool_input(
        SearchContactsInput,
        {
            "query": query,
            "max_results": max_results or 10,
            "fields": fields,
            "force_refresh": force_refresh,
        },
    )


def validate_list_contacts_input(
    limit: int | None = None,
    fields: list[str] | None = None,
    force_refresh: bool = False,
) -> ListContactsInput:
    """
    Validate list_contacts_tool parameters.

    Args:
        limit: Number of contacts (1-100)
        fields: Fields to include
        force_refresh: Force cache refresh

    Returns:
        Validated ListContactsInput

    Raises:
        ValueError: If validation fails
    """
    return validate_tool_input(
        ListContactsInput,
        {
            "limit": limit or 10,
            "fields": fields,
            "force_refresh": force_refresh,
        },
    )


def validate_get_contact_details_input(
    resource_name: str,
    force_refresh: bool = False,
) -> GetContactDetailsInput:
    """
    Validate get_contact_details_tool parameters.

    Args:
        resource_name: Google identifier (people/cXXXXXXXXXX)
        force_refresh: Force cache refresh

    Returns:
        Validated GetContactDetailsInput

    Raises:
        ValueError: If validation fails (e.g., invalid resource_name format)
    """
    return validate_tool_input(
        GetContactDetailsInput,
        {
            FIELD_RESOURCE_NAME: resource_name,
            "force_refresh": force_refresh,
        },
    )


# ============================================================================
# Output Parsers & Validators
# ============================================================================


def _parse_contact_name(data: dict | None) -> ContactName | None:
    """Parse contact name from raw JSON."""
    if not data:
        return None
    return ContactName(
        display=data.get("display"),
        given_name=data.get("given_name"),
        family_name=data.get("family_name"),
        middle_name=data.get("middle_name"),
        prefix=data.get("prefix"),
        suffix=data.get("suffix"),
    )


def _parse_contact_emails(data: list | None) -> list[ContactEmail]:
    """Parse contact emails from raw JSON (uses parse_list_field factory)."""
    return parse_list_field(data, ContactEmail, required_key="value")


def _parse_contact_phones(data: list | None) -> list[ContactPhone]:
    """Parse contact phones from raw JSON (uses parse_list_field factory)."""
    return parse_list_field(data, ContactPhone, required_key="value")


def _parse_contact_addresses(data: list | None) -> list[ContactAddress]:
    """Parse contact addresses from raw JSON (uses parse_list_field factory)."""
    return parse_list_field(data, ContactAddress)


def _parse_contact_basic(data: dict) -> ContactBasic:
    """Parse basic contact from raw JSON."""
    return ContactBasic(
        resource_name=data[FIELD_RESOURCE_NAME],
        name=_parse_contact_name(data.get("name")),
        emails=_parse_contact_emails(data.get("emails")),
        phones=_parse_contact_phones(data.get("phones")),
    )


def _parse_contact_detailed(data: dict) -> ContactDetailed:
    """Parse detailed contact from raw JSON."""
    return ContactDetailed(
        resource_name=data[FIELD_RESOURCE_NAME],
        name=_parse_contact_name(data.get("name")),
        emails=_parse_contact_emails(data.get("emails")),
        phones=_parse_contact_phones(data.get("phones")),
        addresses=_parse_contact_addresses(data.get("addresses")),
        organizations=data.get("organizations", []),
        biographies=data.get("biographies", []),
        birthdays=data.get("birthdays", []),
        urls=data.get("urls", []),
        relations=data.get("relations", []),
        metadata=data.get(FIELD_METADATA, {}),
    )


def parse_search_contacts_response(json_response: str | dict) -> SearchContactsOutput:
    """
    Parse and validate the search_contacts_tool response.

    Args:
        json_response: JSON response (string or already parsed dict)

    Returns:
        Validated SearchContactsOutput

    Raises:
        ValueError: If parsing or validation fails

    Examples:
        >>> json_str = '{"contacts": [...], "from_cache": true}'
        >>> output = parse_search_contacts_response(json_str)
        >>> output.total_found
        5
    """
    try:
        data = safe_parse_json_strict(json_response, context="search_contacts response")
        contacts_data = data.get("contacts", [])
        contacts = [_parse_contact_basic(c) for c in contacts_data]

        return SearchContactsOutput(
            contacts=contacts,
            total_found=len(contacts),
            from_cache=data.get("from_cache", False),
        )
    except (ValueError, KeyError, ValidationError) as e:
        raise ValueError(f"Failed to parse search_contacts response: {e}") from e


def parse_list_contacts_response(json_response: str | dict) -> ListContactsOutput:
    """
    Parse and validate the list_contacts_tool response.

    Args:
        json_response: JSON response (string or dict)

    Returns:
        Validated ListContactsOutput

    Raises:
        ValueError: If parsing or validation fails
    """
    try:
        data = safe_parse_json_strict(json_response, context="list_contacts response")
        contacts_data = data.get("contacts", [])
        contacts = [_parse_contact_basic(c) for c in contacts_data]

        return ListContactsOutput(
            contacts=contacts,
            total_returned=len(contacts),
            has_more=data.get("has_more", False),
            from_cache=data.get("from_cache", False),
        )
    except (ValueError, KeyError, ValidationError) as e:
        raise ValueError(f"Failed to parse list_contacts response: {e}") from e


def parse_get_contact_details_response(json_response: str | dict) -> GetContactDetailsOutput:
    """
    Parse and validate the get_contact_details_tool response.

    Args:
        json_response: JSON response (string or dict)

    Returns:
        Validated GetContactDetailsOutput

    Raises:
        ValueError: If parsing or validation fails
    """
    try:
        data = safe_parse_json_strict(json_response, context="get_contact_details response")
        contact_data = data.get("contact")
        if not contact_data:
            raise ValueError("Missing 'contact' field in response")

        contact = _parse_contact_detailed(contact_data)

        return GetContactDetailsOutput(
            contact=contact,
            from_cache=data.get("from_cache", False),
        )
    except (ValueError, KeyError, ValidationError) as e:
        raise ValueError(f"Failed to parse get_contact_details response: {e}") from e


# ============================================================================
# High-level Validation Wrappers
# ============================================================================


def validate_and_normalize_search_response(
    json_response: str | dict,
) -> dict[str, Any]:
    """
    Validate and normalize the search_contacts response to ToolResponse.

    Args:
        json_response: Raw tool response

    Returns:
        Standardized ToolResponse dict

    Examples:
        >>> result = await search_contacts_tool(...)
        >>> normalized = validate_and_normalize_search_response(result)
        >>> normalized["success"]
        True
        >>> normalized["data"]["total_found"]
        5
    """
    try:
        # Parse with Pydantic validation
        output = parse_search_contacts_response(json_response)

        # Return standardized ToolResponse
        return create_success_response(
            data=output.model_dump(),
            metadata={
                "total_found": output.total_found,
                "from_cache": output.from_cache,
            },
        )
    except ValueError as e:
        return create_error_response(
            message=str(e),
            code=ToolErrorCode.INVALID_RESPONSE_FORMAT,
            context={"raw_response": str(json_response)[:500]},
        )


def validate_and_normalize_list_response(
    json_response: str | dict,
) -> dict[str, Any]:
    """Validate and normalize the list_contacts response to ToolResponse."""
    try:
        output = parse_list_contacts_response(json_response)
        return create_success_response(
            data=output.model_dump(),
            metadata={
                "total_returned": output.total_returned,
                "has_more": output.has_more,
                "from_cache": output.from_cache,
            },
        )
    except ValueError as e:
        return create_error_response(
            message=str(e),
            code=ToolErrorCode.INVALID_RESPONSE_FORMAT,
            context={"raw_response": str(json_response)[:500]},
        )


def validate_and_normalize_details_response(
    json_response: str | dict,
) -> dict[str, Any]:
    """Validate and normalize the get_contact_details response to ToolResponse."""
    try:
        output = parse_get_contact_details_response(json_response)
        return create_success_response(
            data=output.model_dump(),
            metadata={
                "from_cache": output.from_cache,
                FIELD_RESOURCE_NAME: output.contact.resource_name,
            },
        )
    except ValueError as e:
        return create_error_response(
            message=str(e),
            code=ToolErrorCode.INVALID_RESPONSE_FORMAT,
            context={"raw_response": str(json_response)[:500]},
        )


__all__ = [
    # Input validators
    "validate_search_contacts_input",
    "validate_list_contacts_input",
    "validate_get_contact_details_input",
    # Output parsers
    "parse_search_contacts_response",
    "parse_list_contacts_response",
    "parse_get_contact_details_response",
    # High-level wrappers
    "validate_and_normalize_search_response",
    "validate_and_normalize_list_response",
    "validate_and_normalize_details_response",
]
