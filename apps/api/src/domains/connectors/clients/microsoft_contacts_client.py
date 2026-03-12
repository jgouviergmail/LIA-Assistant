"""
Microsoft Contacts (Graph API) client for contact operations.

Provides contact search, list, CRUD operations via Microsoft Graph API v1.0.
Implements the same interface as GooglePeopleClient for transparent
provider switching.

API Reference:
- https://learn.microsoft.com/en-us/graph/api/resources/contact

Scopes required:
- Contacts.Read, Contacts.ReadWrite
"""

from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.base_microsoft_client import BaseMicrosoftClient
from src.domains.connectors.clients.normalizers.microsoft_contacts_normalizer import (
    build_contact_body,
    build_contact_update_body,
    normalize_graph_contact,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

logger = structlog.get_logger(__name__)

# Default fields for contact queries
_CONTACT_SELECT_FIELDS = (
    "id,displayName,givenName,surname,middleName,emailAddresses,"
    "homePhones,businessPhones,mobilePhone,companyName,jobTitle,"
    "department,homeAddress,businessAddress,otherAddress,"
    "birthday,personalNotes,photo"
)


class MicrosoftContactsClient(BaseMicrosoftClient):
    """
    Microsoft Contacts client via Graph API.

    Implements ContactsClientProtocol (structural typing) for transparent
    provider switching with GooglePeopleClient and AppleContactsClient.

    Example:
        >>> client = MicrosoftContactsClient(user_id, credentials, connector_service)
        >>> results = await client.search_contacts("John")
        >>> for contact in results["results"]:
        ...     print(contact["names"][0]["displayName"])
    """

    connector_type = ConnectorType.MICROSOFT_CONTACTS

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,
    ) -> None:
        """Initialize Microsoft Contacts client."""
        super().__init__(user_id, credentials, connector_service)

    # =========================================================================
    # SEARCH & RETRIEVAL
    # =========================================================================

    async def search_contacts(
        self,
        query: str,
        max_results: int = settings.contacts_tool_default_max_results,
        use_cache: bool = True,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Search contacts using Microsoft Graph $search.

        Args:
            query: Search query string.
            max_results: Maximum results.
            use_cache: Whether to use cache (unused, kept for interface compatibility).
            fields: Field projection (unused, kept for interface compatibility).

        Returns:
            Dict with 'results' list in Google People API format.
        """
        max_results = apply_max_items_limit(max_results)

        params: dict[str, Any] = {
            "$top": max_results,
            "$select": _CONTACT_SELECT_FIELDS,
            "$search": f'"{query}"',
        }

        response = await self._make_request("GET", "/me/contacts", params)

        # Wrap in {"person": ...} to match Google People API format
        # (tools expect results[i]["person"] to extract contact data)
        results = [
            {"person": normalize_graph_contact(contact)} for contact in response.get("value", [])
        ]

        logger.info(
            "microsoft_contacts_searched",
            user_id=str(self.user_id),
            query=query,
            results_count=len(results),
        )

        return {
            "results": results,
            "totalItems": len(results),
        }

    async def list_connections(
        self,
        page_size: int = 100,
        page_token: str | None = None,
        use_cache: bool = True,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        List all contacts with pagination.

        Args:
            page_size: Number of contacts per page.
            page_token: Pagination token (unused, Graph uses @odata.nextLink).
            use_cache: Whether to use cache (unused, kept for interface compatibility).
            fields: Field projection (unused, kept for interface compatibility).

        Returns:
            Dict with 'connections' list in Google People API format.
        """
        page_size = apply_max_items_limit(page_size)

        result = await self._get_paginated_odata(
            endpoint="/me/contacts",
            items_key="value",
            max_results=page_size,
            params={"$select": _CONTACT_SELECT_FIELDS, "$orderby": "displayName"},
            transform_items=lambda items: [normalize_graph_contact(c) for c in items],
        )

        connections = result.get("value", [])

        logger.info(
            "microsoft_contacts_listed",
            user_id=str(self.user_id),
            count=len(connections),
        )

        return {
            "connections": connections,
            "totalItems": len(connections),
        }

    async def get_person(
        self,
        resource_name: str,
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Get a specific contact by resource name.

        Args:
            resource_name: Resource name in format "people/{contact_id}".
            fields: Field projection (unused, kept for interface compatibility).
            use_cache: Whether to use cache (unused, kept for interface compatibility).

        Returns:
            Dict in Google People API person format.
        """
        # Extract contact ID from resource_name format "people/{id}"
        contact_id = resource_name.replace("people/", "")

        params: dict[str, Any] = {"$select": _CONTACT_SELECT_FIELDS}

        response = await self._make_request("GET", f"/me/contacts/{contact_id}", params)

        logger.info(
            "microsoft_contact_retrieved",
            user_id=str(self.user_id),
            contact_id=contact_id,
        )

        return normalize_graph_contact(response)

    # =========================================================================
    # WRITE OPERATIONS
    # =========================================================================

    async def create_contact(
        self,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        organization: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new contact.

        Args:
            name: Contact display name.
            email: Email address.
            phone: Phone number.
            organization: Company name.
            notes: Personal notes.

        Returns:
            Created contact in Google People API format.
        """
        body = build_contact_body(name, email, phone, organization, notes)

        response = await self._make_request("POST", "/me/contacts", json_data=body)

        logger.info(
            "microsoft_contact_created",
            user_id=str(self.user_id),
            contact_id=response.get("id"),
            name=name,
        )

        return normalize_graph_contact(response)

    async def update_contact(
        self,
        resource_name: str,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        organization: str | None = None,
        notes: str | None = None,
        address: str | None = None,
    ) -> dict[str, Any]:
        """
        Update an existing contact.

        Args:
            resource_name: Resource name in format "people/{contact_id}".
            name: New display name.
            email: New email address.
            phone: New phone number.
            organization: New company name.
            notes: New personal notes.
            address: New address.

        Returns:
            Updated contact in Google People API format.
        """
        contact_id = resource_name.replace("people/", "")
        body = build_contact_update_body(name, email, phone, organization, notes, address)

        response = await self._make_request("PATCH", f"/me/contacts/{contact_id}", json_data=body)

        logger.info(
            "microsoft_contact_updated",
            user_id=str(self.user_id),
            contact_id=contact_id,
        )

        return normalize_graph_contact(response)

    async def delete_contact(self, resource_name: str) -> bool:
        """
        Delete a contact.

        Args:
            resource_name: Resource name in format "people/{contact_id}".

        Returns:
            True if successful.
        """
        contact_id = resource_name.replace("people/", "")

        await self._make_request("DELETE", f"/me/contacts/{contact_id}")

        logger.info(
            "microsoft_contact_deleted",
            user_id=str(self.user_id),
            contact_id=contact_id,
        )

        return True
