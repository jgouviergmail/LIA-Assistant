"""
Base Microsoft Graph API client with common functionality.

Provides shared functionality for all Microsoft 365 API clients:
- OAuth token management with automatic refresh (via BaseOAuthClient)
- Rate limiting (configurable per client, via BaseOAuthClient)
- HTTP client with connection pooling (via BaseOAuthClient)
- Microsoft-specific: OData pagination, error parsing, Retry-After support

Inherits from BaseOAuthClient (Template Method pattern).
Overrides 3 hooks for Microsoft-specific behavior:
- _parse_error_detail(): Parse Microsoft Graph JSON error format
- _get_retry_delay(): Honor Retry-After header
- _enrich_request_params(): Default pass-through (safety net)

Subclasses must implement:
- connector_type: ConnectorType for this client
- api_base_url: Base URL (default: MICROSOFT_GRAPH_BASE_URL)
"""

from typing import Any
from uuid import UUID

import httpx
import structlog

from src.core.config import settings
from src.core.constants import MICROSOFT_GRAPH_BASE_URL
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.base_oauth_client import BaseOAuthClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

logger = structlog.get_logger(__name__)


class BaseMicrosoftClient(BaseOAuthClient[ConnectorType]):
    """
    Base class for Microsoft Graph API clients.

    Inherits _make_request(), _refresh_access_token(), and
    _invalidate_connector_on_auth_failure() from BaseOAuthClient.

    Overrides 3 hooks for Microsoft-specific behavior and adds
    _get_paginated_odata() for @odata.nextLink pagination.

    Example:
        class MicrosoftOutlookClient(BaseMicrosoftClient):
            connector_type = ConnectorType.MICROSOFT_OUTLOOK
            api_base_url = MICROSOFT_GRAPH_BASE_URL

            async def search_emails(self, query: str) -> dict:
                return await self._make_request(
                    "GET", "/me/messages", {"$search": f'"{query}"'}
                )
    """

    # Default for all Microsoft clients
    api_base_url: str = MICROSOFT_GRAPH_BASE_URL

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,  # ConnectorService
        rate_limit_per_second: int | None = None,
    ) -> None:
        """
        Initialize Microsoft Graph API client.

        Args:
            user_id: User UUID.
            credentials: OAuth credentials (access_token, refresh_token).
            connector_service: ConnectorService instance for token refresh.
            rate_limit_per_second: Max requests per second (None = use settings).
        """
        effective_rate_limit = (
            rate_limit_per_second
            if rate_limit_per_second is not None
            else settings.client_rate_limit_microsoft_per_second
        )
        super().__init__(user_id, credentials, connector_service, effective_rate_limit)

    # =========================================================================
    # HOOK OVERRIDES (3 points of variation from Google)
    # =========================================================================

    def _parse_error_detail(self, response: httpx.Response) -> str:
        """
        Parse Microsoft Graph error format: {"error": {"code": "...", "message": "..."}}.

        Returns "[ErrorCode] Error message" for structured errors,
        or raw text for non-JSON responses.
        """
        try:
            error = response.json().get("error", {})
            code = error.get("code", "Unknown")
            message = error.get("message", response.text)
            return f"[{code}] {message}"
        except Exception:
            return response.text

    def _get_retry_delay(self, response: httpx.Response, attempt: int) -> float:
        """
        Honor Microsoft Retry-After header (seconds).

        Microsoft Graph returns Retry-After header on 429 responses.
        Falls back to exponential backoff if header is missing.
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return self._calculate_backoff(attempt)

    # =========================================================================
    # OData PAGINATION (Microsoft-specific: @odata.nextLink)
    # =========================================================================

    async def _get_paginated_odata(
        self,
        endpoint: str,
        items_key: str = "value",
        max_results: int = 50,
        params: dict[str, Any] | None = None,
        transform_items: Any | None = None,
    ) -> dict[str, Any]:
        """
        Paginated retrieval using Microsoft OData @odata.nextLink pattern.

        Microsoft Graph uses @odata.nextLink (full URL) instead of pageToken.
        Continues fetching until max_results is reached or no more pages.

        Args:
            endpoint: API endpoint path (e.g., "/me/messages").
            items_key: Key in response containing items (default: "value").
            max_results: Maximum total items to retrieve.
            params: Additional query parameters (e.g., $filter, $select, $search).
            transform_items: Optional callable to transform items list.

        Returns:
            Dict with items_key containing all collected items.
        """
        max_results = apply_max_items_limit(max_results)

        all_items: list[dict[str, Any]] = []
        request_params = dict(params) if params else {}

        # Set initial $top (page size)
        remaining = max_results - len(all_items)
        page_size = min(remaining, settings.api_max_items_per_request)
        request_params["$top"] = page_size

        # First request uses endpoint
        response = await self._make_request("GET", endpoint, request_params)
        items = response.get(items_key, [])
        if transform_items:
            items = transform_items(items)
        all_items.extend(items)

        # Follow @odata.nextLink for subsequent pages
        next_link = response.get("@odata.nextLink")

        while next_link and len(all_items) < max_results:
            # @odata.nextLink is a full URL — make request directly
            response = await self._make_request_full_url("GET", next_link)
            items = response.get(items_key, [])
            if transform_items:
                items = transform_items(items)
            all_items.extend(items)
            next_link = response.get("@odata.nextLink")

            if not items:
                break

        all_items = all_items[:max_results]

        logger.debug(
            "odata_paginated_list_completed",
            connector_type=self.connector_type.value,
            endpoint=endpoint,
            total_items=len(all_items),
            max_results=max_results,
        )

        return {items_key: all_items}

    async def _make_request_full_url(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make request using a full URL (for @odata.nextLink).

        Unlike _make_request() which builds URL from api_base_url + endpoint,
        this uses the URL as-is (Microsoft provides full URLs in nextLink).
        """
        import asyncio

        from fastapi import HTTPException, status

        await self._rate_limit()

        client = await self._get_client()
        connector_type_value = self.connector_type.value

        for attempt in range(3):
            try:
                # Refresh token inside retry loop to handle expiry during Retry-After
                access_token = await self._ensure_valid_token()
                headers: dict[str, str] = {"Authorization": f"Bearer {access_token}"}

                response = await client.request(
                    method, url, headers=headers, params=params, json=json_data
                )

                if response.status_code < 400:
                    return response.json() if response.content else {}

                if response.status_code == 429:
                    wait_time = self._get_retry_delay(response, attempt)
                    logger.warning(
                        "api_rate_limited_retrying",
                        user_id=str(self.user_id),
                        connector_type=connector_type_value,
                        attempt=attempt + 1,
                        wait_time=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                if response.status_code >= 500:
                    wait_time = self._get_retry_delay(response, attempt)
                    await asyncio.sleep(wait_time)
                    continue

                if response.status_code == 401:
                    error_detail = self._parse_error_detail(response)
                    await self._invalidate_connector_on_auth_failure(error_detail)
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Authentification {connector_type_value} invalide.",
                        headers={"X-Requires-Reconnect": "true"},
                    )

                error_detail = self._parse_error_detail(response)
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"{connector_type_value} API error: {error_detail}",
                )

            except httpx.RequestError as e:
                if attempt < 2:
                    await asyncio.sleep(self._calculate_backoff(attempt))
                    continue
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"{connector_type_value} API unavailable: {e!s}",
                ) from e

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{connector_type_value} API: max retries exceeded",
        )
