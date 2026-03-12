"""
Base Google API client with common functionality.

Provides shared functionality for all Google API clients:
- OAuth token management with automatic refresh (via BaseOAuthClient)
- Rate limiting (configurable per client, via BaseOAuthClient)
- HTTP client with connection pooling (via BaseOAuthClient)
- Retry logic with exponential backoff (via BaseOAuthClient._make_request)
- Google-specific: paginated list retrieval, raw request for file downloads

Inherits from BaseOAuthClient (Sprint 14 - Gold-Grade Architecture).
Template Method: inherits _make_request() from BaseOAuthClient with default hooks
(no overrides needed — defaults match Google behavior).

Subclasses must implement:
- connector_type: ConnectorType for this client
- api_base_url: Base URL for the API
"""

import asyncio
from typing import Any
from uuid import UUID

import httpx
import structlog
from fastapi import HTTPException, status

from src.core.config import settings
from src.domains.connectors.clients.base_oauth_client import BaseOAuthClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

logger = structlog.get_logger(__name__)


def apply_max_items_limit(max_results: int) -> int:
    """
    Apply security limit to max_results parameter.

    Ensures API requests don't exceed the configured maximum items per request.
    This prevents abuse and ensures consistent pagination across all clients.

    Args:
        max_results: Requested maximum number of items.

    Returns:
        min(max_results, settings.api_max_items_per_request)

    Example:
        >>> page_size = apply_max_items_limit(500)  # Returns 100 if limit is 100
    """
    return min(max_results, settings.api_max_items_per_request)


class BaseGoogleClient(BaseOAuthClient[ConnectorType]):
    """
    Base class for Google API clients.

    Inherits _make_request(), _refresh_access_token(), and
    _invalidate_connector_on_auth_failure() from BaseOAuthClient.
    No hook overrides needed — BaseOAuthClient defaults match Google behavior.

    Adds Google-specific:
    - _get_paginated_list(): Google pageToken pagination
    - _make_raw_request(): Binary content for file downloads

    Example:
        class GooglePeopleClient(BaseGoogleClient):
            connector_type = ConnectorType.GOOGLE_CONTACTS
            api_base_url = "https://people.googleapis.com/v1"

            async def search_contacts(self, query: str) -> dict:
                return await self._make_request("GET", "/people:searchContacts", {"query": query})
    """

    # Must be defined by subclasses
    connector_type: ConnectorType
    api_base_url: str

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,  # ConnectorService
        rate_limit_per_second: int | None = None,
    ) -> None:
        """
        Initialize Google API client.

        Args:
            user_id: User UUID.
            credentials: OAuth credentials (access_token, refresh_token).
            connector_service: ConnectorService instance for token refresh.
            rate_limit_per_second: Max requests per second (None = use settings).
        """
        effective_rate_limit = (
            rate_limit_per_second
            if rate_limit_per_second is not None
            else settings.client_rate_limit_google_per_second
        )
        super().__init__(user_id, credentials, connector_service, effective_rate_limit)

    # =========================================================================
    # PAGINATED LIST RETRIEVAL (Google-specific: pageToken pattern)
    # =========================================================================

    async def _get_paginated_list(
        self,
        endpoint: str,
        items_key: str,
        max_results: int,
        params: dict[str, Any] | None = None,
        page_token_key: str = "pageToken",
        next_page_token_key: str = "nextPageToken",
        page_size_key: str = "pageSize",
        transform_items: Any | None = None,
    ) -> dict[str, Any]:
        """
        Generic paginated list retrieval with automatic pageToken handling.

        Handles Google API pagination pattern consistently across all clients.
        Continues fetching pages until max_results is reached or no more pages.

        Args:
            endpoint: API endpoint path (e.g., "/files").
            items_key: Key in response containing items (e.g., "files", "items").
            max_results: Maximum total items to retrieve.
            params: Additional query parameters.
            page_token_key: Request param name for page token (default: "pageToken").
            next_page_token_key: Response key for next page token (default: "nextPageToken").
            page_size_key: Request param name for page size (default: "pageSize").
            transform_items: Optional callable to transform items list.

        Returns:
            Dict with items_key containing all collected items.

        Example:
            >>> result = await self._get_paginated_list(
            ...     endpoint="/files",
            ...     items_key="files",
            ...     max_results=50,
            ...     params={"q": "trashed=false"},
            ... )
            >>> print(f"Got {len(result['files'])} files")
        """
        # Apply security limit
        max_results = apply_max_items_limit(max_results)

        all_items: list[dict[str, Any]] = []
        page_token: str | None = None
        request_params = dict(params) if params else {}

        while len(all_items) < max_results:
            # Calculate page size for this request
            remaining = max_results - len(all_items)
            page_size = min(remaining, settings.api_max_items_per_request)
            request_params[page_size_key] = page_size

            if page_token:
                request_params[page_token_key] = page_token
            elif page_token_key in request_params:
                del request_params[page_token_key]

            # Make request
            response = await self._make_request("GET", endpoint, request_params)

            # Extract items
            items = response.get(items_key, [])
            if transform_items:
                items = transform_items(items)

            all_items.extend(items)

            # Check for next page
            page_token = response.get(next_page_token_key)
            if not page_token or not items:
                break

        # Truncate to max_results if we got more
        all_items = all_items[:max_results]

        logger.debug(
            "paginated_list_completed",
            connector_type=self.connector_type.value,
            endpoint=endpoint,
            total_items=len(all_items),
            max_results=max_results,
        )

        return {items_key: all_items}

    # =========================================================================
    # RAW REQUEST (for file downloads/exports — Google-specific)
    # =========================================================================

    async def _make_raw_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> bytes:
        """
        Make authenticated request to Google API returning raw bytes.

        Used for file downloads and exports where binary content is needed
        instead of JSON. Includes the same retry logic as _make_request().

        Args:
            method: HTTP method (GET, POST).
            endpoint: API endpoint path.
            params: Query parameters.
            max_retries: Max retry attempts for 429/5xx errors.

        Returns:
            Raw bytes from response.

        Raises:
            HTTPException: On errors or max retries exceeded.

        Example:
            >>> content = await self._make_raw_request(
            ...     "GET",
            ...     f"/files/{file_id}",
            ...     {"alt": "media"},
            ... )
        """
        await self._rate_limit()
        access_token = await self._ensure_valid_token()

        url = f"{self.api_base_url}{endpoint}"
        headers = {"Authorization": f"Bearer {access_token}"}

        client = await self._get_client()

        for attempt in range(max_retries):
            try:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                )

                # Success
                if response.status_code < 400:
                    return response.content

                # Rate limited - retry with backoff
                if response.status_code == 429:
                    wait_time = self._calculate_backoff(attempt)
                    logger.warning(
                        "api_rate_limited_raw_request",
                        user_id=str(self.user_id),
                        connector_type=self.connector_type.value,
                        attempt=attempt + 1,
                        wait_time=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Server error - retry with backoff
                if response.status_code >= 500:
                    wait_time = self._calculate_backoff(attempt)
                    logger.warning(
                        "api_server_error_raw_request",
                        user_id=str(self.user_id),
                        connector_type=self.connector_type.value,
                        status_code=response.status_code,
                        attempt=attempt + 1,
                        wait_time=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                # Client errors - don't retry
                error_detail = response.text
                logger.error(
                    "api_raw_request_error",
                    user_id=str(self.user_id),
                    connector_type=self.connector_type.value,
                    status_code=response.status_code,
                    error=error_detail[:200],
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"{self.connector_type.value} API error: {error_detail}",
                )

            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    wait_time = self._calculate_backoff(attempt)
                    logger.warning(
                        "api_raw_request_network_error",
                        user_id=str(self.user_id),
                        connector_type=self.connector_type.value,
                        error=str(e),
                        attempt=attempt + 1,
                        wait_time=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"{self.connector_type.value} API unavailable: {e!s}",
                ) from e

        # Max retries exceeded
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{self.connector_type.value} API: max retries exceeded",
        )
