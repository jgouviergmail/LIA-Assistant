"""
Template for creating a new API client for external services.

This template provides the standard structure for API clients following
LIA architecture patterns (ADR-009: Config Module Split, Phase 2.4: Rate Limiting).

Copy this file to: apps/api/src/domains/connectors/clients/{service}_client.py

Example: Google Gmail API client
    File: apps/api/src/domains/connectors/clients/google_gmail_client.py
    Domain: emails (ADR-010 - generic multi-provider naming)
"""

from typing import Any
from uuid import UUID

import httpx
import structlog

from src.domains.connectors.clients.base_google_client import BaseGoogleClient
from src.domains.connectors.service import ConnectorService
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter
from src.core.config import settings

logger = structlog.get_logger(__name__)


class YourServiceClient(BaseGoogleClient):  # TODO: Rename class (e.g., GoogleGmailClient)
    """
    API client for [Your Service Name].

    TODO: Add description of the service and API documentation link.

    Example for Gmail:
        API client for Gmail API.
        Docs: https://developers.google.com/gmail/api/reference/rest

    Handles:
    - OAuth2 authentication with automatic token refresh (BaseGoogleClient)
    - Distributed rate limiting with Redis (Phase 2.4)
    - Error handling and logging with PII filtering
    - Response parsing and normalization

    Architecture:
    - Inherits from BaseGoogleClient for OAuth management
    - Uses RedisRateLimiter for distributed rate limiting
    - Configuration from src/core/config/ (modular - ADR-009)

    Attributes:
        user_id: User UUID
        credentials: OAuth credentials dict
        connector_service: ConnectorService instance for token refresh
        rate_limiter: RedisRateLimiter instance for distributed rate limiting
    """

    # TODO: Set API base URL
    BASE_URL = "https://your-api-base-url.com/v1"  # Update to your API base URL

    def __init__(
        self,
        user_id: UUID,
        credentials: dict[str, Any],
        connector_service: ConnectorService,
        rate_limiter: RedisRateLimiter,  # NEW: Rate limiter injection
    ):
        """
        Initialize client with OAuth credentials and rate limiter.

        Args:
            user_id: User UUID
            credentials: OAuth credentials dict (access_token, refresh_token, etc.)
            connector_service: ConnectorService for token refresh
            rate_limiter: RedisRateLimiter for distributed rate limiting

        Example:
            >>> from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter
            >>> rate_limiter = RedisRateLimiter(redis_client)
            >>> client = YourServiceClient(
            ...     user_id=user.id,
            ...     credentials=connector.credentials,
            ...     connector_service=connector_service,
            ...     rate_limiter=rate_limiter
            ... )
        """
        super().__init__(user_id, credentials, connector_service)
        self.user_id = user_id
        self.credentials = credentials
        self.connector_service = connector_service

    async def _get_headers(self) -> dict[str, str]:
        """
        Get HTTP headers with OAuth token.

        Handles automatic token refresh if needed.

        Returns:
            Dict of HTTP headers including Authorization
        """
        access_token = await self._get_access_token()

        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            # TODO: Add other required headers (e.g., API version, User-Agent)
        }

    async def _get_access_token(self) -> str:
        """
        Get access token, refreshing if expired.

        Returns:
            Valid access token string
        """
        # Check if token needs refresh
        if self._is_token_expired():
            await self._refresh_token()

        return self.credentials["access_token"]

    def _is_token_expired(self) -> bool:
        """
        Check if access token is expired.

        TODO: Implement expiration check logic based on your API.

        Returns:
            True if token is expired, False otherwise
        """
        # TODO: Implement token expiration check
        # Example:
        # import time
        # expires_at = self.credentials.get("expires_at", 0)
        # return time.time() >= expires_at - 60  # 60s buffer
        return False

    async def _refresh_token(self) -> None:
        """
        Refresh OAuth access token using refresh token.

        Updates self.credentials with new access token.
        """
        # TODO: Implement token refresh logic
        # Usually delegated to connector_service
        logger.info(
            "refreshing_access_token",
            user_id=str(self.user_id),
        )

        # Example:
        # new_credentials = await self.connector_service.refresh_oauth_token(
        #     self.user_id,
        #     ConnectorType.YOUR_SERVICE,
        # )
        # self.credentials = new_credentials

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Make HTTP request to API with error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path (without base URL)
            **kwargs: Additional httpx request arguments (json, params, etc.)

        Returns:
            Parsed JSON response

        Raises:
            httpx.HTTPStatusError: On HTTP errors
            httpx.RequestError: On network errors
        """
        url = f"{self.BASE_URL}{endpoint}"
        headers = await self._get_headers()

        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=30.0,  # TODO: Adjust timeout as needed
                    **kwargs,
                )

                response.raise_for_status()

                logger.debug(
                    "api_request_success",
                    user_id=str(self.user_id),
                    method=method,
                    endpoint=endpoint,
                    status_code=response.status_code,
                )

                return response.json()

            except httpx.HTTPStatusError as e:
                logger.error(
                    "api_request_http_error",
                    user_id=str(self.user_id),
                    method=method,
                    endpoint=endpoint,
                    status_code=e.response.status_code,
                    error=str(e),
                )
                raise

            except httpx.RequestError as e:
                logger.error(
                    "api_request_network_error",
                    user_id=str(self.user_id),
                    method=method,
                    endpoint=endpoint,
                    error=str(e),
                )
                raise

    # ========================================================================
    # PUBLIC API METHODS
    # ========================================================================

    async def your_method(
        self,
        param1: str,
        param2: int | None = None,
    ) -> dict[str, Any]:
        """
        TODO: Implement your API method.

        Description of what this method does.

        Args:
            param1: Description of param1
            param2: Description of param2 (optional)

        Returns:
            Dict with API response

        Raises:
            httpx.HTTPStatusError: On HTTP errors
            ValueError: On invalid parameters

        Example:
            >>> client = YourServiceClient(user_id, credentials, connector_service)
            >>> result = await client.your_method("value", 42)
            >>> print(result["field"])
        """
        # TODO: Implement your API call
        # Example:
        # response = await self._make_request(
        #     method="GET",
        #     endpoint="/your/endpoint",
        #     params={"param1": param1, "param2": param2},
        # )
        # return response

        logger.info(
            "your_method_called",
            user_id=str(self.user_id),
            param1=param1,
            param2=param2,
        )

        # Placeholder return
        return {"result": "TODO: Implement API call"}


# ============================================================================
# EXAMPLE USAGE (for reference)
# ============================================================================

"""
Example: Gmail send_email method

class GmailClient(BaseOAuthClient):
    BASE_URL = "https://gmail.googleapis.com/gmail/v1"

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
    ) -> dict[str, Any]:
        # Build email message
        message = {
            "raw": self._create_mime_message(to, subject, body, cc, bcc)
        }

        # Send via Gmail API
        response = await self._make_request(
            method="POST",
            endpoint="/users/me/messages/send",
            json=message,
        )

        return {
            "id": response["id"],
            "thread_id": response["threadId"],
            "label_ids": response.get("labelIds", []),
        }

    def _create_mime_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
    ) -> str:
        # Create MIME message
        import base64
        from email.mime.text import MIMEText

        message = MIMEText(body, "plain", "utf-8")
        message["To"] = to
        message["Subject"] = subject
        if cc:
            message["Cc"] = cc
        if bcc:
            message["Bcc"] = bcc

        # Encode to base64url
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        return raw
"""
