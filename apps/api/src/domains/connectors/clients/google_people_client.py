"""
Google People API client for Contacts operations.
Handles authentication, rate limiting, caching, and pagination.

Inherits from BaseGoogleClient for common functionality.
"""

import base64
import hashlib
from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import (
    GOOGLE_CONTACT_GROUP_MAX_MEMBERS,
    GOOGLE_OTHER_CONTACTS_FIELDS,
    GOOGLE_OTHER_CONTACTS_SEARCH_MAX,
    GOOGLE_PEOPLE_CONNECTIONS_PAGE_SIZE_MAX,
)
from src.core.content_source import content_source_binding
from src.core.field_names import FIELD_CACHED_AT, FIELD_QUERY
from src.domains.connectors.clients import contact_photos
from src.domains.connectors.clients.base_google_client import (
    BaseGoogleClient,
    apply_max_items_limit,
)
from src.domains.connectors.clients.cache_mixin import CacheableMixin
from src.domains.connectors.clients.contact_details import NO_YEAR, ContactDetails
from src.domains.connectors.clients.contact_directory import (
    CONTACTS_DIRECTORY_FIELDS,
    ContactDirectory,
    cached_directory,
)
from src.domains.connectors.clients.contact_photos import ContactPhoto
from src.domains.connectors.clients.google_contact_groups_mixin import GoogleContactGroupsMixin
from src.domains.connectors.clients.normalizers.contact_values import (
    TypedAddress,
    TypedValue,
    addresses_read,
    desired_addresses,
    desired_values,
    kept_or_built,
    same_kind,
    values_read,
)
from src.domains.connectors.clients.people_names import (
    GROUP_NAME,
    OTHER_CONTACT_NAME,
    named_path,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials
from src.infrastructure.cache import ContactsCache

logger = structlog.get_logger(__name__)


class GooglePeopleClient(GoogleContactGroupsMixin, CacheableMixin[ContactsCache], BaseGoogleClient):
    """
    Google People API client with OAuth, rate limiting, caching, and error handling.

    Inherits common functionality from BaseGoogleClient:
    - Automatic token refresh with Redis lock
    - Rate limiting (configurable, default 10 req/s)
    - HTTP client with connection pooling
    - Retry logic with exponential backoff

    Adds domain-specific features:
    - Redis caching (5 min TTL for lists, 3 min for searches)
    - Pagination support for contacts

    Example:
        >>> client = GooglePeopleClient(user_id, credentials, connector_service)
        >>> results = await client.search_contacts("John Doe", max_results=25)
        >>> # results = {"connections": [...], "totalItems": 5}
    """

    # Required by BaseGoogleClient
    connector_type = ConnectorType.GOOGLE_CONTACTS
    api_base_url = "https://people.googleapis.com/v1"

    # Required by CacheableMixin
    _cache_class = ContactsCache

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,  # ConnectorService
    ) -> None:
        """
        Initialize Google People client.

        Args:
            user_id: User UUID.
            credentials: OAuth credentials (access_token, refresh_token).
            connector_service: ConnectorService instance for token refresh.
        """
        # Initialize base class with default rate limiting
        super().__init__(user_id, credentials, connector_service)

    async def _get_cache(self) -> ContactsCache:
        """Every record read uses the credentials' source, including cache hits."""
        return (await super()._get_cache()).for_source(content_source_binding(self))

    async def search_contacts(
        self,
        query: str,
        max_results: int = settings.contacts_tool_default_max_results,
        use_cache: bool = True,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Search contacts by name, email, or phone.

        Args:
            query: Search query string.
            max_results: Maximum number of results (default 25, max 50 per API).
            use_cache: Whether to use Redis cache (default True).
            fields: List of field names to fetch. If None, uses default fields.
                   Available: names, emailAddresses, phoneNumbers, addresses,
                             organizations, birthdays, photos.
                   Example: ["names", "phoneNumbers"] for name + phone only.

        Returns:
            Dictionary with 'results' list and 'totalItems' count.

        Example:
            >>> # Basic search (default fields)
            >>> results = await client.search_contacts("John Doe")

            >>> # Optimized search (phone numbers only)
            >>> results = await client.search_contacts("John", fields=["names", "phoneNumbers"])
        """
        from src.core.constants import GOOGLE_CONTACTS_SEARCH_FIELDS

        cache = await self._get_cache()

        # Cache key includes fields to prevent collisions
        # FIX #2025-11-14: Normalize fields=None to actual default fields for cache consistency
        # When fields=None, we use SEARCH_FIELDS by default (see line 418)
        # Cache key should reflect actual fields fetched, not "default" string
        if fields is None:
            # Use actual default fields for search operation
            fields_key = ",".join(sorted(GOOGLE_CONTACTS_SEARCH_FIELDS))
        else:
            fields_key = ",".join(sorted(fields))
        cache_key = f"{query}:{fields_key}"

        # Check cache first (V2: returns tuple with metadata)
        from_cache = False
        cached_at = None
        cache_age_seconds = None

        if use_cache:
            cached_data, from_cache, cached_at, cache_age_seconds = await cache.get_search(
                self.user_id, cache_key
            )
            if from_cache and cached_data:
                logger.info(
                    "contacts_search_cache_hit",
                    user_id=str(self.user_id),
                    query_length=len(query),
                    fields_used=fields_key,
                    cache_age_seconds=cache_age_seconds,
                )
                # Enrich cached data with freshness metadata
                cached_data["from_cache"] = True
                cached_data[FIELD_CACHED_AT] = cached_at
                return cached_data

        # Build dynamic readMask (default: SEARCH_FIELDS for optimal token efficiency)
        read_mask = ",".join(fields) if fields else ",".join(GOOGLE_CONTACTS_SEARCH_FIELDS)

        # Apply security limit
        effective_max_results = apply_max_items_limit(max_results)

        # Make API request
        params = {
            FIELD_QUERY: query,
            "readMask": read_mask,
            "pageSize": effective_max_results,
        }

        logger.debug(
            "google_search_contacts_api_call",
            user_id=str(self.user_id),
            query=query,
            read_mask=read_mask,
            page_size=params["pageSize"],
        )

        response = await self._make_request("GET", "/people:searchContacts", params=params)

        # Format results with freshness metadata
        results = {
            "results": response.get("results", []),
            "totalItems": len(response.get("results", [])),
            "from_cache": False,  # Fresh from API
            FIELD_CACHED_AT: None,
        }

        # Cache results with fields-specific key (configurable TTL, default: 3 min)
        if use_cache and results["totalItems"] > 0:
            await cache.set_search(
                self.user_id,
                cache_key,
                results,
                ttl_seconds=settings.get_connector_cache_ttl("google_contacts_search"),
            )

        logger.info(
            "contacts_search_success",
            user_id=str(self.user_id),
            query_length=len(query),
            total_results=results["totalItems"],
            fields_used=fields_key,
        )

        return results

    async def list_connections(
        self,
        page_size: int = 100,
        page_token: str | None = None,
        use_cache: bool = True,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        List all contacts (connections) with pagination.

        Args:
            page_size: Number of contacts per page (default 100, max 1000).
            page_token: Pagination token from previous request.
            use_cache: Whether to use Redis cache (default True, only for first page).
            fields: List of field names to fetch. If None, uses default fields.

        Returns:
            Dictionary with 'connections', 'totalItems', 'nextPageToken'.

        Example:
            >>> page1 = await client.list_connections(page_size=100)
            >>> # {"connections": [...], "totalItems": 150, "nextPageToken": "abc123"}
            >>> page2 = await client.list_connections(page_token=page1["nextPageToken"])
        """
        from src.core.constants import GOOGLE_CONTACTS_LIST_FIELDS

        cache = await self._get_cache()

        # Only cache first page (no page_token) - V2: returns tuple with metadata
        from_cache = False
        cached_at = None
        cache_age_seconds = None

        if use_cache and not page_token:
            cached_data, from_cache, cached_at, cache_age_seconds = await cache.get_list(
                self.user_id
            )
            if from_cache and cached_data:
                logger.info(
                    "contacts_list_cache_hit",
                    user_id=str(self.user_id),
                    cache_age_seconds=cache_age_seconds,
                )
                # Enrich cached data with freshness metadata
                cached_data["from_cache"] = True
                cached_data[FIELD_CACHED_AT] = cached_at
                return cached_data

        # Build dynamic personFields (default: LIST_FIELDS for minimal token usage in listings)
        person_fields = ",".join(fields) if fields else ",".join(GOOGLE_CONTACTS_LIST_FIELDS)

        # Apply security limit: min of requested, global limit, and API max
        effective_page_size = min(page_size, settings.api_max_items_per_request)

        logger.info(
            "contacts_list_security_limit",
            user_id=str(self.user_id),
            requested_page_size=page_size,
            api_max_items=settings.api_max_items_per_request,
            effective_page_size=effective_page_size,
        )

        # Make API request
        params = {
            "resourceName": "people/me",
            "personFields": person_fields,
            "pageSize": effective_page_size,
            # Family then given name (owner request 2026-10-31): Google pages the
            # listing, so Google sorts it — its default order is the last change.
            "sortOrder": "LAST_NAME_ASCENDING",
        }

        if page_token:
            params["pageToken"] = page_token

        response = await self._make_request("GET", "/people/me/connections", params=params)

        # Format results with freshness metadata
        results = {
            "connections": response.get("connections", []),
            "totalItems": response.get("totalItems", len(response.get("connections", []))),
            "nextPageToken": response.get("nextPageToken"),
            "from_cache": False,  # Fresh from API
            FIELD_CACHED_AT: None,
        }

        # Cache first page only (configurable TTL, default: 5 min)
        if use_cache and not page_token:
            ttl = settings.get_connector_cache_ttl("google_contacts")
            await cache.set_list(
                self.user_id,
                results,
                ttl_seconds=ttl,
            )
            logger.info(
                "contacts_list_cached",
                user_id=str(self.user_id),
                connections_count=len(results["connections"]),
                ttl_seconds=ttl,
            )

        logger.info(
            "contacts_list_success",
            user_id=str(self.user_id),
            page_size=page_size,
            has_more=bool(results["nextPageToken"]),
            connections_count=len(results["connections"]),
        )

        return results

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
        """Read the connections page by page, most recently modified first.

        Google requires every parameter but the token to repeat across pages,
        so the page size is fixed for the whole read and the result is cut.
        """
        params: dict[str, Any] = {
            "resourceName": "people/me",
            "personFields": ",".join(CONTACTS_DIRECTORY_FIELDS),
            "pageSize": min(GOOGLE_PEOPLE_CONNECTIONS_PAGE_SIZE_MAX, max_contacts),
            "sortOrder": "LAST_MODIFIED_DESCENDING",
        }
        persons: list[dict[str, Any]] = []
        while True:
            response = await self._make_request("GET", "/people/me/connections", params=params)
            persons.extend(response.get("connections") or [])
            token = response.get("nextPageToken")
            if len(persons) > max_contacts or (token and len(persons) >= max_contacts):
                return persons[:max_contacts], True
            if not token:
                return persons, False
            params = {**params, "pageToken": token}

    async def get_person(
        self,
        resource_name: str,
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Get detailed information about a specific contact.

        Args:
            resource_name: Google resource name (e.g., "people/c1234567890").
            fields: List of field names to fetch. If None, fetches ALL fields
                   (default for detail view).
            use_cache: Whether to use Redis cache (default True).

        Returns:
            Dictionary with person details.

        Example:
            >>> # Full details (all fields)
            >>> person = await client.get_person("people/c123")

            >>> # Minimal details (name + email only)
            >>> person = await client.get_person("people/c123", fields=["names", "emailAddresses"])

            >>> # Force refresh (bypass cache)
            >>> person = await client.get_person("people/c123", use_cache=False)
        """
        from src.core.constants import GOOGLE_CONTACTS_ALL_FIELDS

        cache = await self._get_cache()

        # Build cache key including fields to prevent collisions between different field sets
        # FIX #2025-11-14: When fields=None, normalize to sorted ALL_FIELDS for cache consistency
        # This ensures that get_person(fields=None) and get_person(fields=ALL_FIELDS) share cache
        # Problem: Planner sometimes specifies explicit fields, sometimes None (both fetch ALL_FIELDS)
        # Without normalization, they create different cache keys for identical data
        #
        # Example cache keys:
        # - fields=None → "people/c123:default" (fetches ALL_FIELDS from API)
        # - fields=["names",...all 19...] → "people/c123:addresses,biographies,..." (fetches same data)
        # These should share cache! Solution: Normalize None to sorted ALL_FIELDS string
        if fields is None:
            # None means ALL_FIELDS - use sorted field names for consistent cache key
            fields_key = ",".join(sorted(GOOGLE_CONTACTS_ALL_FIELDS))
        else:
            fields_key = ",".join(sorted(fields))
        cache_key = f"{resource_name}:{fields_key}"

        # Check cache - V2: returns tuple with metadata
        if use_cache:
            cached_data, from_cache, cached_at, cache_age_seconds = await cache.get_details(
                self.user_id, cache_key
            )
            if from_cache and cached_data:
                logger.info(
                    "contacts_details_cache_hit",
                    user_id=str(self.user_id),
                    resource_name=resource_name,
                    fields_used=fields_key,
                    cache_age_seconds=cache_age_seconds,
                )
                # Enrich cached data with freshness metadata
                cached_data["from_cache"] = True
                cached_data[FIELD_CACHED_AT] = cached_at
                return cached_data

        # Build dynamic personFields (default = ALL fields for detail view)
        person_fields = ",".join(fields) if fields else ",".join(GOOGLE_CONTACTS_ALL_FIELDS)

        # Make API request
        params = {
            "personFields": person_fields,
        }

        response = await self._make_request("GET", named_path(resource_name), params=params)

        # Add freshness metadata before caching
        response["from_cache"] = False
        response[FIELD_CACHED_AT] = None

        # Cache details (configurable TTL, default: 10 min for detailed contact info)
        # Use same cache_key with fields to maintain consistency with cache lookup
        await cache.set_details(
            self.user_id,
            cache_key,
            response,
            ttl_seconds=settings.get_connector_cache_ttl("google_contacts_details"),
        )

        logger.info(
            "contacts_details_success",
            user_id=str(self.user_id),
            resource_name=resource_name,
            fields_used=fields_key,
        )

        return response

    # =========================================================================
    # WRITE OPERATIONS (LOT 5.4)
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
        Create a new contact in Google Contacts.

        LOT 5.4: Write operation with HITL integration.
        This method is called after user confirms the draft via HITL.

        Args:
            name: Contact full name (required)
            email: Contact email address (optional)
            phone: Contact phone number (optional)
            organization: Company/organization name (optional)
            notes: Additional notes (optional)
            emails: Every e-mail, typed (optional; not with ``email``)
            phones: Every phone, typed (optional; not with ``phone``)
            addresses: Every postal address, typed (optional)
            details: Its name's parts, job title, website and birthday (optional)

        Returns:
            Created contact data with resourceName

        Example:
            >>> result = await client.create_contact(
            ...     name="John Doe",
            ...     email="john@example.com",
            ...     phone="+33612345678",
            ... )
            >>> print(result["resourceName"])  # "people/c123..."
        """
        # Build contact body per Google People API spec
        # https://developers.google.com/people/api/rest/v1/people/createContact
        contact_body: dict[str, Any] = {
            "names": [_name_entry({}, name, details)],
        }

        new_lists = _people_lists({}, email=email, phone=phone, emails=emails, phones=phones)
        contact_body.update({field: entries for field, entries in new_lists.items() if entries})
        if addresses:
            contact_body["addresses"] = [_address_entry(a, None) for a in addresses]

        if organization:
            contact_body["organizations"] = [{"name": organization}]
        contact_body.update(_detail_fields({**contact_body}, details))

        if notes:
            contact_body["biographies"] = [{"value": notes, "contentType": "TEXT_PLAIN"}]

        # Make API request to create contact
        # POST /v1/people:createContact
        response = await self._make_request(
            "POST",
            "/people:createContact",
            json_data=contact_body,
        )

        logger.info(
            "contacts_create_success",
            user_id=str(self.user_id),
            resource_name=response.get("resourceName"),
        )

        # Invalidate cache after write operation
        cache = await self._get_cache()
        await cache.invalidate_user(self.user_id)

        return response

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
        Update an existing contact in Google Contacts.

        A single e-mail, phone or address replaces the contact's PRIMARY one and
        keeps the others; a list replaces that list. ``updatePersonFields`` names
        exactly the lists written, each sent whole with what did not change
        echoed as read, under the etag read just before (ADR-369, D4).

        LOT 5.4: Write operation with HITL integration.
        This method is called after user confirms the draft via HITL.

        Args:
            resource_name: Contact resource name (e.g., "people/c1234567890")
            name: New contact full name (optional)
            email: New contact email address (optional)
            phone: New contact phone number (optional)
            organization: New company/organization name (optional)
            notes: New additional notes (optional)
            address: New formatted address (optional, e.g., "123 Main St, Paris 75001")
            emails: Every e-mail, typed (optional)
            phones: Every phone, typed (optional)
            addresses: Every postal address, typed (optional)
            details: What changes of its name's parts, job, website and birthday (optional)

        Returns:
            Updated contact data

        Raises:
            ValueError: A single value and its list given together, or no etag.

        Example:
            >>> result = await client.update_contact(
            ...     resource_name="people/c123...",
            ...     email="newemail@example.com",
            ...     address="15 rue de la Paix, Paris 75001",
            ... )
        """
        # First, get the current contact to get etag and existing data
        current_contact = await self.get_person(resource_name, use_cache=False)
        etag = current_contact.get("etag")

        if not etag:
            raise ValueError(f"Could not get etag for contact {resource_name}")

        # Build update mask and person body
        update_fields = []
        person_body: dict[str, Any] = {
            "etag": etag,
            "resourceName": resource_name,
        }

        if name is not None or (details is not None and _named_parts(details)):
            first = (_entries(current_contact, "names") or [{}])[0]
            person_body["names"] = [_name_entry(first, name, details)]
            update_fields.append("names")

        if organization is not None:
            # One entry holds the company and the job: writing one keeps the other.
            first, *others = _entries(current_contact, "organizations") or [{}]
            person_body["organizations"] = [{**first, "name": organization}, *others]
            update_fields.append("organizations")

        changed = _detail_fields({**current_contact, **person_body}, details)
        person_body.update(changed)
        update_fields.extend(field for field in changed if field not in update_fields)

        if notes is not None:
            person_body["biographies"] = [{"value": notes, "contentType": "TEXT_PLAIN"}]
            update_fields.append("biographies")

        lists = _people_lists(
            current_contact, email=email, phone=phone, emails=emails, phones=phones
        )
        wanted_addresses = desired_addresses(
            address, addresses, addresses_read(current_contact.get("addresses"))
        )
        if wanted_addresses is not None:
            lists["addresses"] = kept_or_built(
                _entries(current_contact, "addresses"),
                wanted_addresses,
                same=_same_address,
                build=_address_entry,
            )
        person_body.update(lists)
        update_fields.extend(lists)

        if not update_fields:
            logger.warning(
                "contacts_update_no_fields",
                user_id=str(self.user_id),
                resource_name=resource_name,
            )
            return current_contact

        # Make API request to update contact
        # PATCH /v1/{resourceName}:updateContact
        params = {
            "updatePersonFields": ",".join(update_fields),
        }

        response = await self._make_request(
            "PATCH",
            f"{named_path(resource_name)}:updateContact",
            params=params,
            json_data=person_body,
        )

        logger.info(
            "contacts_update_success",
            user_id=str(self.user_id),
            resource_name=resource_name,
            updated_fields=update_fields,
        )

        # Invalidate cache after write operation
        cache = await self._get_cache()
        await cache.invalidate_user(self.user_id)

        return response

    async def delete_contact(self, resource_name: str) -> bool:
        """
        Delete a contact from Google Contacts.

        LOT 5.4: Write operation with HITL integration.
        This method is called after user confirms the draft via HITL.

        IMPORTANT: This is a destructive operation that cannot be undone.

        Args:
            resource_name: Contact resource name (e.g., "people/c1234567890")

        Returns:
            True if deletion was successful

        Example:
            >>> success = await client.delete_contact("people/c123...")
            >>> if success:
            ...     print("Contact deleted")
        """
        # Make API request to delete contact
        # DELETE /v1/{resourceName}:deleteContact
        await self._make_request(
            "DELETE",
            f"{named_path(resource_name)}:deleteContact",
        )

        logger.info(
            "contacts_delete_success",
            user_id=str(self.user_id),
            resource_name=resource_name,
        )

        # Invalidate cache after write operation
        cache = await self._get_cache()
        await cache.invalidate_user(self.user_id)

        return True

    # =========================================================================
    # OTHER CONTACTS & CONTACT GROUPS (lot C, 2026-08)
    # =========================================================================

    async def get_contact_photo(self, resource_name: str) -> ContactPhoto | None:
        """The photo Google holds of a contact; its own silhouette is none (ADR-369, lot 9)."""
        person = await self.get_person(resource_name, fields=["photos"], use_cache=False)
        for entry in _entries(person, "photos"):
            if entry.get("url") and not entry.get("default"):
                return await contact_photos.fetch_photo(str(entry["url"]))
        return None

    async def set_contact_photo(self, resource_name: str, photo: ContactPhoto) -> None:
        """Replace a contact's photo."""
        await self._make_request(
            "PATCH",
            f"{named_path(resource_name)}:updateContactPhoto",
            json_data={"photoBytes": base64.b64encode(photo.data).decode("ascii")},
        )
        await self._forget_people()

    async def remove_contact_photo(self, resource_name: str) -> None:
        """Take a contact's photo off."""
        await self._make_request("DELETE", f"{named_path(resource_name)}:deleteContactPhoto")
        await self._forget_people()

    async def _forget_people(self) -> None:
        cache = await self._get_cache()
        await cache.invalidate_user(self.user_id)

    async def save_other_contact(self, resource_name: str) -> dict[str, Any]:
        """Copy a contact met in mail into the person's contacts (ADR-369, lot 9).

        Args:
            resource_name: Its name, ``otherContacts/...``.

        Returns:
            The saved contact, under a ``people/...`` name of its own.
        """
        path = named_path(resource_name, OTHER_CONTACT_NAME)
        response = await self._make_request(
            "POST",
            f"{path}:copyOtherContactToMyContactsGroup",
            json_data={"copyMask": ",".join(GOOGLE_OTHER_CONTACTS_FIELDS)},
        )
        await self._forget_people()
        logger.info("other_contact_saved", user_id=str(self.user_id))
        return response

    async def search_other_contacts(
        self,
        query: str,
        max_results: int = GOOGLE_OTHER_CONTACTS_SEARCH_MAX,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Search "other contacts" (interacted-with but never saved).

        Uses the ``contacts.other.readonly`` scope granted since the first
        OAuth version. Only names/emailAddresses/phoneNumbers exist on other
        contacts (API constraint).

        Args:
            query: Search query (name, email or phone prefix).
            max_results: Max results (hard API cap applied).
            use_cache: Whether to use Redis cache (default True).

        Returns:
            Dict with 'results' list (each item wraps a 'person').
        """
        cache = await self._get_cache()
        cache_key = f"other:{query}"

        if use_cache:
            cached_data, from_cache, cached_at, _age = await cache.get_search(
                self.user_id, cache_key
            )
            if from_cache and cached_data:
                cached_data["from_cache"] = True
                cached_data[FIELD_CACHED_AT] = cached_at
                return cached_data

        # Global volumetry cap first, then the endpoint's own hard limit.
        max_results = apply_max_items_limit(max_results)
        params = {
            FIELD_QUERY: query,
            "readMask": ",".join(GOOGLE_OTHER_CONTACTS_FIELDS),
            "pageSize": min(max_results, GOOGLE_OTHER_CONTACTS_SEARCH_MAX),
        }
        response = await self._make_request("GET", "/otherContacts:search", params=params)

        results = {
            "results": response.get("results", []),
            "totalItems": len(response.get("results", [])),
            "from_cache": False,
            FIELD_CACHED_AT: None,
        }
        if use_cache and results["totalItems"] > 0:
            await cache.set_search(
                self.user_id,
                cache_key,
                results,
                ttl_seconds=settings.get_connector_cache_ttl("google_contacts_search"),
            )

        logger.info(
            "other_contacts_search_success",
            user_id=str(self.user_id),
            total_results=results["totalItems"],
        )
        return results

    async def list_contact_groups(self) -> dict[str, Any]:
        """
        List the user's contact groups (system + user groups, raw API shape).

        Deliberately uncached: one small quota-free GET whose member counts
        must stay exact (a count shown to the user is a claim).

        Returns:
            Dict with 'contactGroups' list (resourceName, groupType, name,
            formattedName, memberCount).
        """
        response = await self._make_request("GET", "/contactGroups")
        logger.info(
            "contact_groups_listed",
            user_id=str(self.user_id),
            total=len(response.get("contactGroups", [])),
        )
        return response

    async def get_contact_group(
        self,
        resource_name: str,
        max_members: int = GOOGLE_CONTACT_GROUP_MAX_MEMBERS,
    ) -> dict[str, Any]:
        """
        Fetch one contact group including its member resource names.

        Args:
            resource_name: Group resource name (e.g. "contactGroups/abc").
            max_members: Max memberResourceNames returned.

        Returns:
            Group dict with 'memberResourceNames'.
        """
        return await self._make_request(
            "GET",
            named_path(resource_name, GROUP_NAME),
            params={"maxMembers": max_members},
        )

    async def get_people_batch(
        self,
        resource_names: list[str],
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Batch-fetch people by resource names (group member expansion).

        Args:
            resource_names: People resource names (e.g. ["people/1", ...]).
            fields: personFields to fetch (default: names + emailAddresses).

        Returns:
            Dict with 'responses' list (each item wraps a 'person').
        """
        if not resource_names:
            return {"responses": []}
        params = {
            "resourceNames": resource_names,
            "personFields": ",".join(fields or ["names", "emailAddresses"]),
        }
        return await self._make_request("GET", "/people:batchGet", params=params)

    def anonymize_connector_id(self, connector_id: UUID) -> str:
        """
        Hash connector_id for anonymized metrics.

        Args:
            connector_id: Connector UUID.

        Returns:
            8-character hash for metrics labeling.
        """
        return hashlib.sha256(str(connector_id).encode()).hexdigest()[:8]


#: What a person's name is made of on Google; everything else in its entry is derived.
_NAME_PARTS: Final = (
    "honorificPrefix",
    "givenName",
    "middleName",
    "familyName",
    "honorificSuffix",
)


def _name_entry(
    first: Mapping[str, Any], name: str | None, details: ContactDetails | None
) -> dict[str, Any]:
    """The name to write: its parts when the person named one, else the whole name.

    What Google derives from the parts (the display forms, the free-form name) never goes back:
    a stale free-form name beside a changed part is a contradiction left to Google to settle.
    Parts emptied beside a whole name leave the whole name, so the contact keeps one.
    """
    asked = {} if details is None else _named_parts(details)
    written = {key: first[key] for key in _NAME_PARTS if key in first} | asked
    holds_a_name = written.get("givenName") or written.get("familyName")
    return written if asked and (holds_a_name or name is None) else {"givenName": name}


def _named_parts(details: ContactDetails) -> dict[str, str]:
    """The parts of a name ``details`` names; an empty one empties that part."""
    parts = {"givenName": details.given_name, "familyName": details.family_name}
    return {key: value for key, value in parts.items() if value is not None}


def _detail_fields(person: Mapping[str, Any], details: ContactDetails | None) -> dict[str, Any]:
    """The People fields ``details`` changes on ``person``; none for what it leaves out."""
    if details is None:
        return {}
    fields: dict[str, Any] = {}
    if details.job_title is not None:
        first, *others = _entries(person, "organizations") or [{}]
        fields["organizations"] = [{**first, "title": details.job_title}, *others]
    if details.website is not None:
        first, *others = _entries(person, "urls") or [{}]
        fields["urls"] = (
            [{**first, "value": details.website}, *others] if details.website else others
        )
    if details.birthday is not None:
        day = details.birthday
        year = {} if day.year == NO_YEAR else {"year": day.year}
        fields["birthdays"] = [{"date": {**year, "month": day.month, "day": day.day}}]
    elif details.clear_birthday:
        fields["birthdays"] = []
    return fields


def _entries(person: Mapping[str, Any], field: str) -> list[dict[str, Any]]:
    """A person's stored entries of one list, as read."""
    entries = person.get(field)
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _people_lists(
    current: Mapping[str, Any],
    *,
    email: str | None,
    phone: str | None,
    emails: list[TypedValue] | None,
    phones: list[TypedValue] | None,
) -> dict[str, list[dict[str, Any]]]:
    """The e-mail and phone lists a write sends, each whole (``current`` is ``{}`` when new)."""
    lists: dict[str, list[dict[str, Any]]] = {}
    for field, single, given in (
        ("emailAddresses", email, emails),
        ("phoneNumbers", phone, phones),
    ):
        wanted = desired_values(single, given, values_read(current.get(field)))
        if wanted is not None:
            lists[field] = kept_or_built(
                _entries(current, field), wanted, same=_same_value, build=_value_entry
            )
    return lists


def _same_value(entry: Mapping[str, Any], wanted: TypedValue) -> bool:
    value = str(entry.get("value", ""))
    return value.casefold() == wanted["value"].casefold() and same_kind(
        entry.get("type"), wanted["type"]
    )


def _same_address(entry: Mapping[str, Any], wanted: TypedAddress) -> bool:
    return str(entry.get("formattedValue", "")) == wanted["formatted"] and same_kind(
        entry.get("type"), wanted["type"]
    )


def _kept_metadata(
    built: dict[str, Any], wanted_kind: str | None, replaced: object
) -> dict[str, Any]:
    """The replaced entry's source, so the primary keeps its place (never across kinds)."""
    if (
        isinstance(replaced, Mapping)
        and "metadata" in replaced
        and same_kind(replaced.get("type"), wanted_kind)
    ):
        built["metadata"] = replaced["metadata"]
    return built


def _value_entry(wanted: TypedValue, replaced: dict[str, Any] | None) -> dict[str, Any]:
    entry: dict[str, Any] = {"value": wanted["value"]}
    if wanted["type"]:
        entry["type"] = wanted["type"]
    return _kept_metadata(entry, wanted["type"], replaced)


def _address_entry(wanted: TypedAddress, replaced: dict[str, Any] | None) -> dict[str, Any]:
    """A changed address on one line — never the structured fields of the one it replaces."""
    entry: dict[str, Any] = {"formattedValue": wanted["formatted"]}
    if wanted["type"]:
        entry["type"] = wanted["type"]
    return _kept_metadata(entry, wanted["type"], replaced)
