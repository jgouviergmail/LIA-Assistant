"""
Pydantic models for Google Contacts tools.

This module defines Input/Output models for all contacts tools:
- search_contacts_tool
- list_contacts_tool
- get_contact_details_tool

These models ensure:
- Input parameter validation
- JSON serialization/deserialization
- Consistency with catalogue manifests
- Validator and orchestrator support

Usage:
    from src.domains.agents.tools.contacts_models import (
        SearchContactsInput,
        SearchContactsOutput,
    )

    # In the tool
    async def search_contacts_tool(...) -> dict:
        # Validate input
        input_data = SearchContactsInput(
            query=query,
            max_results=max_results,
            ...
        )

        # Execute search
        contacts = await do_search(input_data)

        # Return validated output
        output = SearchContactsOutput(contacts=contacts)
        return create_success_response(
            data=output.model_dump(),
            metadata={"count": len(contacts)}
        )

Compliance: Pydantic v2, Google People API v1
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from src.core.field_names import FIELD_QUERY, FIELD_RESOURCE_NAME

# ============================================================================
# Common Contact Structures
# ============================================================================


class ContactName(BaseModel):
    """Google contact name."""

    display: str | None = Field(None, description="Full display name")
    given_name: str | None = Field(None, description="First name")
    family_name: str | None = Field(None, description="Last name")
    middle_name: str | None = Field(None, description="Middle name")
    prefix: str | None = Field(None, description="Prefix (Dr., Mr., etc.)")
    suffix: str | None = Field(None, description="Suffix (Jr., Sr., etc.)")


class ContactEmail(BaseModel):
    """Contact email."""

    value: str = Field(..., description="Email address")
    type: str | None = Field(None, description="Type (work, home, other)")
    formatted_type: str | None = Field(None, description="Formatted type")


class ContactPhone(BaseModel):
    """Contact phone number."""

    value: str = Field(..., description="Phone number")
    type: str | None = Field(None, description="Type (mobile, work, home, other)")
    formatted_type: str | None = Field(None, description="Formatted type")


class ContactAddress(BaseModel):
    """Contact postal address."""

    formatted_value: str | None = Field(None, description="Full formatted address")
    type: str | None = Field(None, description="Type (home, work, other)")
    street_address: str | None = Field(None, description="Street and number")
    city: str | None = Field(None, description="City")
    region: str | None = Field(None, description="Region/State")
    postal_code: str | None = Field(None, description="Postal code")
    country: str | None = Field(None, description="Country")


class ContactBasic(BaseModel):
    """
    Contact with basic information.

    Used by search_contacts_tool and list_contacts_tool.

    Note: addresses and birthdays are optional and can be requested
    via the fields parameter ['names', 'emailAddresses', 'phoneNumbers', 'addresses', 'birthdays']
    """

    resource_name: str = Field(..., description="Google identifier (format: people/cXXXXXXXXXX)")
    name: ContactName | None = Field(None, description="Contact name")
    emails: list[ContactEmail] = Field(default_factory=list, description="Email addresses")
    phones: list[ContactPhone] = Field(default_factory=list, description="Phone numbers")
    addresses: list[ContactAddress] = Field(
        default_factory=list,
        description="Postal addresses (optional, requested via fields=['addresses'])",
    )
    birthdays: list[str] = Field(
        default_factory=list,
        description="Formatted birth dates (optional, requested via fields=['birthdays'])",
    )

    @field_validator(FIELD_RESOURCE_NAME)
    @classmethod
    def validate_resource_name_format(cls, v: str) -> str:
        """Validate resource_name format."""
        if not v.startswith("people/"):
            raise ValueError(f"{FIELD_RESOURCE_NAME} must start with 'people/'")
        return v


class ContactDetailed(ContactBasic):
    """
    Contact with detailed information.

    Used by get_contact_details_tool.
    Inherits from ContactBasic and adds additional fields.
    """

    addresses: list[ContactAddress] = Field(default_factory=list, description="Postal addresses")
    organizations: list[dict] = Field(default_factory=list, description="Organizations/companies")
    biographies: list[dict] = Field(default_factory=list, description="Biographies")
    birthdays: list[dict] = Field(default_factory=list, description="Birth dates")
    urls: list[dict] = Field(default_factory=list, description="URLs/websites")
    relations: list[dict] = Field(default_factory=list, description="Relations (family, etc.)")
    metadata: dict = Field(default_factory=dict, description="Google metadata")


# ============================================================================
# search_contacts_tool Models
# ============================================================================


class SearchContactsInput(BaseModel):
    """
    Input parameters for search_contacts_tool.

    Attributes:
        query: Search text (name, email, phone)
        max_results: Maximum number of results (1-50, default 10)
        fields: List of fields to include (performance optimization)
        force_refresh: Force cache refresh (bypass 5min cache)

    Examples:
        >>> input_data = SearchContactsInput(
        ...     query="jean",
        ...     max_results=20,
        ...     fields=["names", "emailAddresses"],
        ...     force_refresh=False
        ... )
    """

    query: str = Field(..., min_length=1, description="Name, email or phone to search")
    max_results: int = Field(10, ge=1, le=50, description="Maximum number of results (1-50)")
    fields: list[str] | None = Field(None, description="Fields to include in the response")
    force_refresh: bool = Field(False, description="Force cache refresh")

    @field_validator(FIELD_QUERY)
    @classmethod
    def validate_query_not_empty(cls, v: str) -> str:
        """Validate that query is not empty after strip."""
        if not v.strip():
            raise ValueError("query must not be empty")
        return v.strip()


class SearchContactsOutput(BaseModel):
    """
    Result of search_contacts_tool.

    Attributes:
        contacts: List of found contacts
        total_found: Total number of contacts found
        from_cache: True if result comes from cache

    Examples:
        >>> output = SearchContactsOutput(
        ...     contacts=[contact1, contact2],
        ...     total_found=2,
        ...     from_cache=True
        ... )
        >>> output.model_dump()
    """

    contacts: list[ContactBasic] = Field(default_factory=list, description="Found contacts")
    total_found: int = Field(0, ge=0, description="Total number of contacts found")
    from_cache: bool = Field(False, description="Result comes from cache")


# ============================================================================
# list_contacts_tool Models
# ============================================================================


class ListContactsInput(BaseModel):
    """
    Input parameters for list_contacts_tool.

    Attributes:
        limit: Number of contacts to return (1-100, default 10)
        fields: List of fields to include
        force_refresh: Force cache refresh

    Examples:
        >>> input_data = ListContactsInput(
        ...     limit=50,
        ...     fields=["names", "emailAddresses", "phoneNumbers"],
        ...     force_refresh=False
        ... )
    """

    limit: int = Field(10, ge=1, le=100, description="Number of contacts (1-100)")
    fields: list[str] | None = Field(None, description="Fields to include")
    force_refresh: bool = Field(False, description="Force cache refresh")


class ListContactsOutput(BaseModel):
    """
    Result of list_contacts_tool.

    Attributes:
        contacts: List of contacts
        total_returned: Number of contacts returned
        has_more: True if more contacts are available (pagination)
        from_cache: True if result comes from cache

    Examples:
        >>> output = ListContactsOutput(
        ...     contacts=[contact1, contact2, contact3],
        ...     total_returned=3,
        ...     has_more=True,
        ...     from_cache=False
        ... )
    """

    contacts: list[ContactBasic] = Field(default_factory=list, description="List of contacts")
    total_returned: int = Field(0, ge=0, description="Number of contacts returned")
    has_more: bool = Field(False, description="More contacts available (pagination)")
    from_cache: bool = Field(False, description="Result from cache")


# ============================================================================
# get_contact_details_tool Models
# ============================================================================


class GetContactDetailsInput(BaseModel):
    """
    Input parameters for get_contact_details_tool.

    Attributes:
        resource_name: Google contact identifier (format: people/cXXXXXXXXXX)
        force_refresh: Force cache refresh

    Examples:
        >>> input_data = GetContactDetailsInput(
        ...     resource_name="people/c1234567890",
        ...     force_refresh=False
        ... )
    """

    resource_name: str = Field(
        ...,
        pattern=r"^people/c\d+$",
        description="Google identifier (format: people/cXXXXXXXXXX)",
    )
    force_refresh: bool = Field(False, description="Force cache refresh")


class GetContactDetailsOutput(BaseModel):
    """
    Result of get_contact_details_tool.

    Attributes:
        contact: Contact with full details
        from_cache: True if result comes from cache

    Examples:
        >>> output = GetContactDetailsOutput(
        ...     contact=detailed_contact,
        ...     from_cache=True
        ... )
    """

    contact: ContactDetailed = Field(..., description="Contact with full details")
    from_cache: bool = Field(False, description="Result from cache")


__all__ = [
    # Common structures
    "ContactName",
    "ContactEmail",
    "ContactPhone",
    "ContactAddress",
    "ContactBasic",
    "ContactDetailed",
    # search_contacts_tool
    "SearchContactsInput",
    "SearchContactsOutput",
    # list_contacts_tool
    "ListContactsInput",
    "ListContactsOutput",
    # get_contact_details_tool
    "GetContactDetailsInput",
    "GetContactDetailsOutput",
]
