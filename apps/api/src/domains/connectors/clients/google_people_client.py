"""
Google People API client for Contacts operations.
Handles authentication, rate limiting, caching, and pagination.

Inherits from BaseGoogleClient for common functionality.
"""

import hashlib
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.field_names import FIELD_CACHED_AT, FIELD_QUERY
from src.domains.connectors.clients.base_google_client import (
    BaseGoogleClient,
    apply_max_items_limit,
)
from src.domains.connectors.clients.cache_mixin import CacheableMixin
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials
from src.infrastructure.cache import ContactsCache

logger = structlog.get_logger(__name__)


class GooglePeopleClient(CacheableMixin[ContactsCache], BaseGoogleClient):
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
                    query_preview=query[:20],
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
            query_preview=query[:20],
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

        response = await self._make_request("GET", f"/{resource_name}", params=params)

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
            "names": [{"givenName": name}],
        }

        if email:
            contact_body["emailAddresses"] = [{"value": email}]

        if phone:
            contact_body["phoneNumbers"] = [{"value": phone}]

        if organization:
            contact_body["organizations"] = [{"name": organization}]

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
            name=name,
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
    ) -> dict[str, Any]:
        """
        Update an existing contact in Google Contacts.

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

        Returns:
            Updated contact data

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

        if name is not None:
            person_body["names"] = [{"givenName": name}]
            update_fields.append("names")

        if email is not None:
            person_body["emailAddresses"] = [{"value": email}]
            update_fields.append("emailAddresses")

        if phone is not None:
            person_body["phoneNumbers"] = [{"value": phone}]
            update_fields.append("phoneNumbers")

        if organization is not None:
            person_body["organizations"] = [{"name": organization}]
            update_fields.append("organizations")

        if notes is not None:
            person_body["biographies"] = [{"value": notes, "contentType": "TEXT_PLAIN"}]
            update_fields.append("biographies")

        if address is not None:
            person_body["addresses"] = [{"formattedValue": address, "type": "home"}]
            update_fields.append("addresses")

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
            f"/{resource_name}:updateContact",
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
            f"/{resource_name}:deleteContact",
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

    def anonymize_connector_id(self, connector_id: UUID) -> str:
        """
        Hash connector_id for anonymized metrics.

        Args:
            connector_id: Connector UUID.

        Returns:
            8-character hash for metrics labeling.
        """
        return hashlib.sha256(str(connector_id).encode()).hexdigest()[:8]
