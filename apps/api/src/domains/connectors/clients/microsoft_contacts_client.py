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

import httpx
import structlog
from fastapi import status

from src.core.config import settings
from src.core.constants import MICROSOFT_CONTACTS_DIRECTORY_PAGE_SIZE
from src.core.exceptions import ConnectorAPIError
from src.core.field_names import FIELD_CACHED_AT
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.base_microsoft_client import BaseMicrosoftClient
from src.domains.connectors.clients.contact_details import ContactDetails
from src.domains.connectors.clients.contact_directory import (
    ContactDirectory,
    cached_directory,
    invalidate_contacts_cache,
)
from src.domains.connectors.clients.contact_photos import ContactPhoto, photo_of
from src.domains.connectors.clients.microsoft_contact_groups_mixin import (
    MicrosoftContactGroupsMixin,
    contact_path,
)
from src.domains.connectors.clients.normalizers.contact_values import TypedAddress, TypedValue
from src.domains.connectors.clients.normalizers.graph_paging import (
    graph_page_params,
    graph_page_token,
)
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
    "homePhones,businessPhones,mobilePhone,companyName,jobTitle,businessHomePage,"
    "department,homeAddress,businessAddress,otherAddress,"
    "birthday,personalNotes,photo"
)


#: What a directory entry needs of a Graph contact (``clients/contact_directory``).
_DIRECTORY_SELECT_FIELDS = (
    "id,displayName,givenName,surname,emailAddresses,homePhones,businessPhones,mobilePhone,birthday"
)


class MicrosoftContactsClient(MicrosoftContactGroupsMixin, BaseMicrosoftClient):
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

    _people_select = _CONTACT_SELECT_FIELDS

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
            query_length=len(query),
            results_count=len(results),
        )

        # Graph reads are always live: the freshness metadata is stated
        # explicitly so every contacts provider answers the same contract
        # (see GooglePeopleClient / AppleContactsClient).
        return {
            "results": results,
            "totalItems": len(results),
            "from_cache": False,
            FIELD_CACHED_AT: None,
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
            page_token: The ``next_page_token`` of the previous page (ADR-369): the
                skip value of Graph's ``@odata.nextLink``, never the link itself.
            use_cache: Whether to use cache (unused, kept for interface compatibility).
            fields: Field projection (unused, kept for interface compatibility).

        Returns:
            Dict with 'connections' list in Google People API format, and
            ``next_page_token`` (None on the last page).

        Raises:
            ValueError: ``page_token`` is not one this listing produced.
        """
        page_size = apply_max_items_limit(page_size)
        params = {
            "$select": _CONTACT_SELECT_FIELDS,
            # Family then given name (owner request 2026-10-31): Graph pages the
            # listing, so Graph sorts it.
            "$orderby": "surname,givenName",
            "$top": page_size,
            **graph_page_params(page_token),
        }
        response = await self._make_request("GET", "/me/contacts", params)
        connections = [normalize_graph_contact(c) for c in response.get("value", [])]

        logger.info(
            "microsoft_contacts_listed",
            user_id=str(self.user_id),
            count=len(connections),
        )

        return {
            "connections": connections,
            "totalItems": len(connections),
            "next_page_token": graph_page_token(response.get("@odata.nextLink")),
            "from_cache": False,
            FIELD_CACHED_AT: None,
        }

    async def list_email_directory(
        self, max_contacts: int, *, cache_scope: str | None = None
    ) -> ContactDirectory:
        """The whole address book, up to ``max_contacts`` (``clients/contact_directory``).

        Args:
            max_contacts: The caller's published cap.
            cache_scope: An account and snapshot identity isolating this directory in
                the shared cache from other accounts and older in-flight refreshes
                (``cached_directory``); None for the shared entry.

        Returns:
            The persons (names, addresses, numbers, birthdays), and whether the book was cut.
        """
        return await cached_directory(
            self.user_id,
            self.connector_type.value,
            max_contacts,
            self._read_directory,
            cache_scope=cache_scope,
        )

    async def _read_directory(self, max_contacts: int) -> tuple[list[dict[str, Any]], bool]:
        """Read ``/me/contacts`` following ``@odata.nextLink``, then cut at the cap."""
        response = await self._make_request(
            "GET",
            "/me/contacts",
            {
                "$select": _DIRECTORY_SELECT_FIELDS,
                "$top": min(MICROSOFT_CONTACTS_DIRECTORY_PAGE_SIZE, max_contacts),
            },
        )
        persons = [normalize_graph_contact(contact) for contact in response.get("value", [])]
        next_link = response.get("@odata.nextLink")
        while next_link and len(persons) < max_contacts:
            response = await self._make_request_full_url("GET", next_link)
            persons.extend(
                normalize_graph_contact(contact) for contact in response.get("value", [])
            )
            next_link = response.get("@odata.nextLink")
        truncated = len(persons) > max_contacts or (
            bool(next_link) and len(persons) >= max_contacts
        )
        return persons[:max_contacts], truncated

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
        contact_id = resource_name.removeprefix("people/")

        params: dict[str, Any] = {"$select": _CONTACT_SELECT_FIELDS}

        response = await self._make_request("GET", contact_path(contact_id), params)

        logger.info(
            "microsoft_contact_retrieved",
            user_id=str(self.user_id),
            contact_id=contact_id,
        )

        return {
            **normalize_graph_contact(response),
            "from_cache": False,
            FIELD_CACHED_AT: None,
        }

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
        *,
        emails: list[TypedValue] | None = None,
        phones: list[TypedValue] | None = None,
        addresses: list[TypedAddress] | None = None,
        details: ContactDetails | None = None,
    ) -> dict[str, Any]:
        """
        Create a new contact.

        Args:
            name: Contact display name.
            email: Email address.
            phone: Phone number.
            organization: Company name.
            notes: Personal notes.
            emails: Every e-mail (not with ``email``).
            phones: Every phone (not with ``phone``).
            addresses: Every address.
            details: Its name's parts, job title, website and birthday.

        Returns:
            Created contact in Google People API format.

        Raises:
            ContactValuesRefused: A list Exchange cannot hold (nothing is written).
        """
        body = build_contact_body(
            name,
            email,
            phone,
            organization,
            notes,
            emails=emails,
            phones=phones,
            addresses=addresses,
            details=details,
        )

        response = await self._make_request("POST", "/me/contacts", json_data=body)
        # The directory the recipient suggestions read is cached (Google parity).
        await invalidate_contacts_cache(self.user_id)

        logger.info(
            "microsoft_contact_created",
            user_id=str(self.user_id),
            contact_id=response.get("id"),
        )

        return normalize_graph_contact(response)

    async def get_contact_photo(self, resource_name: str) -> ContactPhoto | None:
        """A contact's photo: Graph answers 404 where it holds none (measured)."""
        path = contact_path(resource_name.removeprefix("people/"))
        try:
            answer = await self._make_request("GET", f"{path}/photo/$value", answer=_raw_answer)
        except ConnectorAPIError as error:
            if error.upstream_status_code == status.HTTP_404_NOT_FOUND:
                return None
            raise
        return photo_of(answer["data"])

    async def set_contact_photo(self, resource_name: str, photo: ContactPhoto) -> None:
        """Replace a contact's photo: ``$value`` is written, as it is read."""
        path = contact_path(resource_name.removeprefix("people/"))
        await self._make_request(
            "PUT",
            f"{path}/photo/$value",
            content=photo.data,
            extra_headers={"Content-Type": photo.mime_type},
            answer=_raw_answer,
        )
        await invalidate_contacts_cache(self.user_id)

    async def remove_contact_photo(self, resource_name: str) -> None:
        """Take a contact's photo off: ``/photo`` deletes, ``$value`` answers 405 (measured)."""
        path = contact_path(resource_name.removeprefix("people/"))
        try:
            await self._make_request("DELETE", f"{path}/photo", answer=_raw_answer)
        except ConnectorAPIError as error:
            if error.upstream_status_code != status.HTTP_404_NOT_FOUND:
                raise
        await invalidate_contacts_cache(self.user_id)

    async def update_contact(
        self,
        resource_name: str,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        organization: str | None = None,
        notes: str | None = None,
        address: str | None = None,
        *,
        emails: list[TypedValue] | None = None,
        phones: list[TypedValue] | None = None,
        addresses: list[TypedAddress] | None = None,
        details: ContactDetails | None = None,
    ) -> dict[str, Any]:
        """
        Update an existing contact.

        A single e-mail, phone or address replaces the PRIMARY one and keeps the
        others; a list replaces that list. Either needs the stored contact, read
        first — Graph replaces a whole array it is sent.

        Args:
            resource_name: Resource name in format "people/{contact_id}".
            name: New display name.
            email: New primary email address.
            phone: New primary phone number.
            organization: New company name.
            notes: New personal notes.
            address: New primary address.
            emails: Every e-mail.
            phones: Every phone.
            addresses: Every address.
            details: What changes of its name's parts, job, website and birthday.

        Returns:
            Updated contact in Google People API format.

        Raises:
            ContactValuesRefused: A list Exchange cannot hold (nothing is written).
        """
        contact_id = resource_name.removeprefix("people/")
        asks_values = any(
            value is not None for value in (email, phone, address, emails, phones, addresses)
        )
        current = await self._make_request("GET", contact_path(contact_id)) if asks_values else {}
        body = build_contact_update_body(
            name,
            email,
            phone,
            organization,
            notes,
            address,
            current=current,
            emails=emails,
            phones=phones,
            addresses=addresses,
            details=details,
        )

        response = await self._make_request("PATCH", contact_path(contact_id), json_data=body)
        await invalidate_contacts_cache(self.user_id)

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
        contact_id = resource_name.removeprefix("people/")

        await self._make_request("DELETE", contact_path(contact_id))
        await invalidate_contacts_cache(self.user_id)

        logger.info(
            "microsoft_contact_deleted",
            user_id=str(self.user_id),
            contact_id=contact_id,
        )

        return True


def _raw_answer(response: httpx.Response) -> dict[str, Any]:
    """An answer that is no JSON: a photo, or nothing at all."""
    return {"data": response.content}
