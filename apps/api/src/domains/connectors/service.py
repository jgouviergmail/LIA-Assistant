"""
Connectors service containing business logic for external service connections.
Handles OAuth flows, token encryption, and connector management.

Refactored (v0.4.0): OAuth flows migrated to src.core.oauth module
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.core.config import settings
from src.core.exceptions import (
    raise_configuration_missing,
    raise_invalid_input,
    raise_oauth_flow_failed,
    raise_oauth_state_mismatch,
    raise_permission_denied,
)
from src.core.field_names import FIELD_CONNECTOR_TYPE, FIELD_STATUS, FIELD_USER_ID
from src.core.i18n_api_messages import APIMessages
from src.core.security import (
    # OAuth helpers moved to src.core.oauth module (v0.4.0 refactoring)
    decrypt_data,
    encrypt_data,
)
from src.core.security.authorization import check_resource_ownership_by_user_id
from src.domains.connectors.models import (
    Connector,
    ConnectorGlobalConfig,
    ConnectorStatus,
    ConnectorType,
    get_conflicting_connector_types,
)
from src.domains.connectors.repository import ConnectorRepository
from src.domains.connectors.schemas import (
    GOOGLE_CONTACTS_SCOPES,
    APIKeyCredentials,
    AppleActivationResponse,
    AppleCredentials,
    ConnectorCredentials,
    ConnectorGlobalConfigResponse,
    ConnectorGlobalConfigUpdate,
    ConnectorHealthResponse,
    ConnectorListResponse,
    ConnectorOAuthInitiate,
    ConnectorResponse,
    ConnectorUpdate,
    HueBridgeCredentials,
    HueConnectionMode,
)
from src.infrastructure.cache.redis import SessionService, get_redis_session
from src.infrastructure.email import get_email_service
from src.infrastructure.resilience import get_circuit_breaker

logger = structlog.get_logger(__name__)


class ConnectorService:
    """Service for connector management business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = ConnectorRepository(db)

    async def get_user_connectors(self, user_id: UUID) -> ConnectorListResponse:
        """
        Get all connectors for a user (with 5min cache).

        Optimization: Caches connector list to reduce database load.
        Cache is invalidated on: create, update, delete, OAuth callback.

        Args:
            user_id: User UUID

        Returns:
            ConnectorListResponse with all user connectors
        """
        from src.infrastructure.cache.redis import get_redis_cache

        cache_key = f"user_connectors:{user_id}"
        redis = await get_redis_cache()

        # Try cache first
        cached = await redis.get(cache_key)
        if cached:
            logger.debug("user_connectors_cache_hit", user_id=str(user_id))
            return ConnectorListResponse.model_validate_json(cached)

        # Cache miss - query DB
        connectors = await self.repository.get_all_by_user(user_id)

        logger.info("user_connectors_fetched", user_id=str(user_id), count=len(connectors))

        response = ConnectorListResponse(
            connectors=[ConnectorResponse.model_validate(c) for c in connectors],
            total=len(connectors),
        )

        # Cache for 5 minutes
        await redis.setex(cache_key, 300, response.model_dump_json())

        return response

    async def check_connector_health(self, user_id: UUID) -> "ConnectorHealthResponse":
        """
        Check the health of all connectors (OAuth + Apple) for a user.

        Determines health status based on:
        - Token expiration time for OAuth (healthy, expiring_soon, expired)
        - Connector status (ERROR status = critical)
        - Apple connectors: HEALTHY if ACTIVE, ERROR if in ERROR state

        This is used by:
        - GET /connectors/health endpoint (frontend polling)
        - OAuth health check scheduler job (proactive notifications)

        Args:
            user_id: User UUID

        Returns:
            ConnectorHealthResponse with health status for each connector
        """
        from src.domains.connectors.models import (
            get_connector_authorize_path,
            get_connector_display_name,
        )
        from src.domains.connectors.schemas import (
            ConnectorHealthItem,
            ConnectorHealthResponse,
            ConnectorHealthSeverity,
            ConnectorHealthStatus,
        )

        connectors = await self.repository.get_all_by_user(user_id)

        health_items: list[ConnectorHealthItem] = []
        critical_count = 0
        warning_count = 0
        now = datetime.now(UTC)

        for connector in connectors:
            ct = connector.connector_type

            # Skip non-OAuth, non-Apple connectors (API key connectors handled elsewhere)
            if not ct.is_oauth and not ct.is_apple:
                continue

            health_status = ConnectorHealthStatus.HEALTHY
            severity = ConnectorHealthSeverity.INFO
            expires_in_minutes: int | None = None
            reconnect_type = "apple_credentials" if ct.is_apple else "oauth"

            if connector.status == ConnectorStatus.ERROR:
                health_status = ConnectorHealthStatus.ERROR
                severity = ConnectorHealthSeverity.CRITICAL
                critical_count += 1
            elif connector.status == ConnectorStatus.ACTIVE:
                if ct.is_oauth:
                    # OAuth: check token expiration for info
                    try:
                        credentials_json = decrypt_data(connector.credentials_encrypted)
                        credentials = ConnectorCredentials.model_validate_json(credentials_json)
                        if credentials.expires_at:
                            expires_in_minutes = int(
                                (credentials.expires_at - now).total_seconds() / 60
                            )
                    except Exception as e:
                        logger.warning(
                            "connector_health_check_decrypt_failed",
                            connector_id=str(connector.id),
                            user_id=str(user_id),
                            error=str(e),
                        )
                        health_status = ConnectorHealthStatus.ERROR
                        severity = ConnectorHealthSeverity.CRITICAL
                        critical_count += 1
                # Apple ACTIVE: HEALTHY (no token expiration, static credentials)
            else:
                # INACTIVE or REVOKED - skip
                continue

            authorize_path = get_connector_authorize_path(ct)
            authorize_url = f"/connectors{authorize_path}" if authorize_path else ""

            health_items.append(
                ConnectorHealthItem(
                    id=connector.id,
                    connector_type=ct,
                    display_name=get_connector_display_name(ct),
                    health_status=health_status,
                    severity=severity,
                    expires_in_minutes=expires_in_minutes,
                    authorize_url=authorize_url,
                    reconnect_type=reconnect_type,
                )
            )

        return ConnectorHealthResponse(
            connectors=health_items,
            has_issues=critical_count > 0 or warning_count > 0,
            critical_count=critical_count,
            warning_count=warning_count,
            checked_at=now,
        )

    async def _invalidate_user_connectors_cache(self, user_id: UUID) -> None:
        """
        Invalidate user connectors cache.

        Called after: create, update, delete, OAuth callback.
        """
        from src.infrastructure.cache.redis import get_redis_cache

        cache_key = f"user_connectors:{user_id}"
        redis = await get_redis_cache()
        await redis.delete(cache_key)
        logger.debug("user_connectors_cache_invalidated", user_id=str(user_id))

    async def get_connector_by_id(self, user_id: UUID, connector_id: UUID) -> ConnectorResponse:
        """
        Get connector by ID (ensures it belongs to the user).

        Args:
            user_id: User UUID
            connector_id: Connector UUID

        Returns:
            ConnectorResponse

        Raises:
            HTTPException 404: If connector not found or doesn't belong to user
        """
        connector = await self.repository.get_by_id(connector_id)
        check_resource_ownership_by_user_id(connector, user_id, "connector")

        return ConnectorResponse.model_validate(connector)

    async def update_connector(
        self, user_id: UUID, connector_id: UUID, update_data: "ConnectorUpdate"
    ) -> "ConnectorResponse":
        """
        Update a connector's status or metadata.

        Args:
            user_id: User ID
            connector_id: Connector ID
            update_data: Data to update

        Returns:
            ConnectorResponse

        Raises:
            HTTPException: If connector not found or doesn't belong to user
        """
        from src.domains.connectors.schemas import ConnectorResponse

        connector = await self.repository.get_by_id(connector_id)
        check_resource_ownership_by_user_id(connector, user_id, "connector")
        assert connector is not None  # check_resource_ownership_by_user_id raises if None

        # Update fields
        update_dict: dict[str, Any] = {}
        if update_data.status is not None:
            update_dict[FIELD_STATUS] = update_data.status

        if update_data.metadata is not None:
            # Note: Model attribute is "connector_metadata" (DB column is "metadata")
            update_dict["connector_metadata"] = update_data.metadata

        if update_dict:
            connector = await self.repository.update(connector, update_dict)
            await self.db.commit()
            await self.db.refresh(connector)

        logger.info(
            "connector_updated",
            user_id=str(user_id),
            connector_id=str(connector_id),
            status=update_dict.get(FIELD_STATUS),
        )

        # Invalidate cache
        await self._invalidate_user_connectors_cache(user_id)

        return ConnectorResponse.model_validate(connector)

    async def refresh_connector_credentials(
        self, user_id: UUID, connector_id: UUID
    ) -> "ConnectorResponse":
        """
        Refresh OAuth credentials for a connector using refresh token.

        Args:
            user_id: User ID
            connector_id: Connector ID

        Returns:
            ConnectorResponse with updated credentials

        Raises:
            HTTPException: If connector not found, doesn't belong to user, or refresh fails
        """
        from src.domains.connectors.schemas import ConnectorResponse

        connector = await self.repository.get_by_id(connector_id)
        check_resource_ownership_by_user_id(connector, user_id, "connector")
        assert connector is not None  # check_resource_ownership_by_user_id raises if None

        # Apple connectors use static app-specific passwords, no token refresh
        if connector.connector_type.is_apple:
            raise_invalid_input(
                "Apple connectors do not support token refresh. "
                "Re-enter your app-specific password to update credentials.",
                connector_type=connector.connector_type.value,
            )

        # Decrypt credentials, refresh, then re-encrypt
        from src.core.security import decrypt_data, encrypt_data
        from src.domains.connectors.schemas import ConnectorCredentials

        credentials_json = decrypt_data(connector.credentials_encrypted)
        credentials = ConnectorCredentials.model_validate_json(credentials_json)

        # Refresh the OAuth token
        refreshed_credentials = await self._refresh_oauth_token(connector, credentials)

        # Re-encrypt and store
        connector.credentials_encrypted = encrypt_data(refreshed_credentials.model_dump_json())
        await self.db.flush()
        await self.db.refresh(connector)

        logger.info(
            "connector_credentials_refreshed",
            user_id=str(user_id),
            connector_id=str(connector_id),
            connector_type=connector.connector_type,
        )

        return ConnectorResponse.model_validate(connector)

    async def delete_connector(self, user_id: UUID, connector_id: UUID) -> None:
        """
        Delete a connector.

        Args:
            user_id: User UUID
            connector_id: Connector UUID

        Raises:
            HTTPException: If connector not found or doesn't belong to user
        """
        connector = await self.repository.get_by_id(connector_id)
        check_resource_ownership_by_user_id(connector, user_id, "connector")
        assert connector is not None  # check_resource_ownership_by_user_id raises if None

        # Optionally revoke OAuth token at provider (for Gmail, etc.)
        await self._revoke_oauth_token(connector)

        # Delete from database
        await self.repository.delete(connector)
        await self.db.commit()

        logger.info(
            "connector_deleted",
            user_id=str(user_id),
            connector_id=str(connector_id),
            connector_type=connector.connector_type,
        )

        # Invalidate cache after deletion
        await self._invalidate_user_connectors_cache(user_id)

    # Gmail connector OAuth flow

    async def initiate_gmail_oauth(self, user_id: UUID) -> ConnectorOAuthInitiate:
        """
        Initiate Gmail OAuth flow with PKCE.

        Security Update (v0.4.0):
        - Now uses PKCE (Proof Key for Code Exchange) per OAuth 2.1 spec
        - Existing connectors will need re-authorization for security upgrade

        Args:
            user_id: User UUID

        Returns:
            ConnectorOAuthInitiate with authorization URL and state
        """
        # Use generic OAuth flow handler with PKCE
        redis = await get_redis_session()
        session_service = SessionService(redis)

        from src.core.oauth import GoogleOAuthProvider, OAuthFlowHandler

        provider = GoogleOAuthProvider.for_gmail(settings)
        flow_handler = OAuthFlowHandler(provider, session_service)

        # Initiate flow with Gmail-specific params and metadata
        auth_url, state = await flow_handler.initiate_flow(
            additional_params={
                "access_type": "offline",  # Get refresh token
                "prompt": "consent",  # Force re-consent to get refresh token
            },
            metadata={
                FIELD_USER_ID: str(user_id),
                FIELD_CONNECTOR_TYPE: ConnectorType.GOOGLE_GMAIL.value,  # FIX: Use GOOGLE_GMAIL
            },
        )

        logger.info("gmail_oauth_initiated", user_id=str(user_id), state=state, pkce=True)

        return ConnectorOAuthInitiate(
            authorization_url=auth_url,
            state=state,
        )

    async def _handle_oauth_connector_callback(
        self,
        user_id: UUID,
        code: str,
        state: str,
        connector_type: ConnectorType,
        provider_factory_method: Callable[..., Any],
        default_scopes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        user_email: str | None = None,
    ) -> ConnectorResponse:
        """
        Generic OAuth callback handler for connectors (DRY principle).

        Handles the complete OAuth flow:
        1. Token exchange with PKCE validation
        2. State validation
        3. Credential encryption
        4. Connector creation/update

        Args:
            user_id: User UUID
            code: Authorization code from OAuth provider
            state: CSRF state token
            connector_type: Type of connector (e.g., GMAIL, GOOGLE_CONTACTS)
            provider_factory_method: Factory method to create OAuth provider
                (e.g., GoogleOAuthProvider.for_gmail)
            default_scopes: Default scopes if not returned by provider
            metadata: Additional metadata to store with connector
            user_email: User email address (used to initialize default preferences
                for Google Calendar connector)

        Returns:
            ConnectorResponse

        Raises:
            HTTPException: If OAuth flow fails or state validation fails
        """
        # Initialize OAuth flow handler
        redis = await get_redis_session()
        session_service = SessionService(redis)

        from src.core.oauth import OAuthFlowHandler

        provider = provider_factory_method(settings)
        flow_handler = OAuthFlowHandler(provider, session_service)

        # Exchange code for tokens (PKCE validation handled automatically)
        try:
            token_response, stored_state = await flow_handler.handle_callback(code, state)
        except Exception as e:
            logger.error(
                f"{connector_type.value}_oauth_callback_failed",
                error=str(e),
                exc_info=True,
            )
            raise_oauth_flow_failed(connector_type.value, str(e))

        # Validate stored state metadata
        stored_user_id = stored_state.get(FIELD_USER_ID)
        stored_connector_type = stored_state.get(FIELD_CONNECTOR_TYPE)

        if stored_user_id != str(user_id) or stored_connector_type != connector_type.value:
            raise_oauth_state_mismatch(user_id, connector_type.value)

        # Validate refresh_token presence (CRITICAL for long-term token management)
        # Google only returns refresh_token on first authorization or with prompt=consent
        if not token_response.refresh_token:
            logger.error(
                f"{connector_type.value}_oauth_missing_refresh_token",
                user_id=str(user_id),
                has_access_token=bool(token_response.access_token),
                scope=token_response.scope,
            )
            raise_oauth_flow_failed(
                connector_type.value,
                APIMessages.google_no_refresh_token_hint(),
            )

        # Extract and encrypt credentials
        scopes: list[str] = (
            token_response.scope.split() if token_response.scope else (default_scopes or [])
        )

        # Use Google standard token lifetime (3599s) as default, not 3600
        from src.core.constants import OAUTH_TOKEN_DEFAULT_LIFETIME_SECONDS

        expires_in = token_response.expires_in or OAUTH_TOKEN_DEFAULT_LIFETIME_SECONDS
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        credentials = ConnectorCredentials(
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            token_type=token_response.token_type,
            expires_at=expires_at,
        )
        encrypted_credentials = encrypt_data(credentials.model_dump_json())

        logger.info(
            f"{connector_type.value}_oauth_credentials_created",
            user_id=str(user_id),
            has_refresh_token=True,
            expires_in_seconds=expires_in,
            scopes_count=len(scopes),
        )

        # Create or update connector
        existing_connector = await self.repository.get_by_user_and_type(user_id, connector_type)

        update_data: dict[str, Any] = {
            FIELD_STATUS: ConnectorStatus.ACTIVE,
            "scopes": scopes,
            "credentials_encrypted": encrypted_credentials,
        }

        # Merge metadata if provided
        # Note: Model attribute is "connector_metadata" (DB column is "metadata")
        if metadata:
            update_data["connector_metadata"] = metadata
        elif "connector_metadata" not in update_data:
            update_data["connector_metadata"] = {}

        if existing_connector:
            # Update existing connector
            connector = await self.repository.update(existing_connector, update_data)
        else:
            # Create new connector
            connector_data = {
                FIELD_USER_ID: user_id,
                FIELD_CONNECTOR_TYPE: connector_type,
                **update_data,
            }

            # For Google Calendar: initialize default_calendar_name with user email
            # The default calendar cannot be empty - it must be the user's Gmail address
            if connector_type == ConnectorType.GOOGLE_CALENDAR and user_email:
                from src.domains.connectors.preferences.service import (
                    ConnectorPreferencesService,
                )

                success, encrypted_prefs, errors = ConnectorPreferencesService.validate_and_encrypt(
                    "google_calendar",
                    {"default_calendar_name": user_email},
                )
                if success and encrypted_prefs:
                    connector_data["preferences_encrypted"] = encrypted_prefs
                    logger.info(
                        "google_calendar_default_preferences_initialized",
                        user_id=str(user_id),
                        default_calendar=user_email,
                    )
                else:
                    logger.warning(
                        "google_calendar_default_preferences_failed",
                        user_id=str(user_id),
                        errors=errors,
                    )

            connector = await self.repository.create(connector_data)

        # Mutual exclusivity: deactivate ALL conflicting connectors (same transaction)
        conflicting_types = get_conflicting_connector_types(connector_type)
        deactivated_types: list[str] = []
        for conflicting_type in conflicting_types:
            conflicting = await self.repository.get_by_user_and_type(user_id, conflicting_type)
            if conflicting and conflicting.status == ConnectorStatus.ACTIVE:
                await self.repository.update(conflicting, {FIELD_STATUS: ConnectorStatus.INACTIVE})
                deactivated_types.append(conflicting_type.value)

        # Single atomic commit: connector activation + conflicting deactivation
        await self.db.commit()
        await self.db.refresh(connector)

        logger.info(
            f"{connector_type.value}_connector_activated",
            user_id=str(user_id),
            connector_id=str(connector.id),
        )

        if deactivated_types:
            logger.info(
                "oauth_mutual_exclusivity_deactivated",
                user_id=str(user_id),
                deactivated_types=deactivated_types,
                activated_type=connector_type.value,
            )

        # Invalidate cache after OAuth connector creation/update
        await self._invalidate_user_connectors_cache(user_id)

        return ConnectorResponse.model_validate(connector)

    async def handle_gmail_callback_stateless(self, code: str, state: str) -> ConnectorResponse:
        """
        Handle Gmail OAuth callback WITHOUT session dependency (stateless).

        See handle_google_contacts_callback_stateless() for detailed documentation.
        This method uses the same stateless pattern.

        Args:
            code: Authorization code from Google
            state: CSRF state token

        Returns:
            ConnectorResponse with created/updated connector

        Raises:
            HTTPException: Various HTTP exceptions (see docstring above)
        """
        from src.core.oauth import GoogleOAuthProvider

        # Delegate to generic stateless handler
        return await self._handle_oauth_connector_callback_stateless(
            code=code,
            state=state,
            connector_type=ConnectorType.GOOGLE_GMAIL,  # FIX: Use GOOGLE_GMAIL (not deprecated GMAIL)
            provider_factory_method=GoogleOAuthProvider.for_gmail,
            default_scopes=None,  # Gmail scopes returned by provider
            metadata={"last_synced": None, "created_via": "oauth_flow_stateless"},
        )

    async def get_connector_credentials(
        self, user_id: UUID, connector_type: ConnectorType
    ) -> ConnectorCredentials | None:
        """
        Get decrypted credentials for a connector.

        Args:
            user_id: User UUID
            connector_type: Type of connector

        Returns:
            ConnectorCredentials or None if not found/inactive

        Raises:
            HTTPException: If connector is revoked or has errors
        """
        connector = await self.repository.get_by_user_and_type(user_id, connector_type)

        if not connector:
            return None

        if connector.status == ConnectorStatus.REVOKED:
            raise_permission_denied(
                action="use",
                resource_type="connector",
                user_id=user_id,
            )

        if connector.status != ConnectorStatus.ACTIVE:
            logger.warning(
                "connector_not_active",
                user_id=str(user_id),
                connector_type=connector_type,
                status=connector.status,
            )
            return None

        # Decrypt credentials
        try:
            decrypted_json = decrypt_data(connector.credentials_encrypted)
            credentials = ConnectorCredentials.model_validate_json(decrypted_json)

            # Check if token is expired or expiring soon (within safety margin)
            # Use same margin as base_google_client to prevent race conditions
            if credentials.expires_at:
                from src.core.constants import OAUTH_TOKEN_REFRESH_MARGIN_SECONDS

                refresh_threshold = datetime.now(UTC) + timedelta(
                    seconds=OAUTH_TOKEN_REFRESH_MARGIN_SECONDS
                )
                if credentials.expires_at < refresh_threshold:
                    credentials = await self._refresh_oauth_token(connector, credentials)

            return credentials

        except Exception as e:
            logger.error(
                "connector_credentials_decryption_failed",
                connector_id=str(connector.id),
                error=str(e),
            )
            raise_invalid_input(
                "Failed to decrypt connector credentials",
                connector_id=str(connector.id),
            )

    # =========================================================================
    # APPLE iCLOUD METHODS
    # =========================================================================

    async def get_apple_credentials(
        self, user_id: UUID, connector_type: ConnectorType
    ) -> AppleCredentials | None:
        """
        Get decrypted Apple credentials for a connector.

        Apple credentials are static (no token refresh needed).

        Args:
            user_id: User UUID.
            connector_type: Apple connector type.

        Returns:
            AppleCredentials or None if not found/inactive.
        """
        connector = await self.repository.get_by_user_and_type(user_id, connector_type)

        if not connector:
            return None

        if connector.status != ConnectorStatus.ACTIVE:
            logger.warning(
                "apple_connector_not_active",
                user_id=str(user_id),
                connector_type=connector_type.value,
                status=connector.status.value if connector.status else "unknown",
            )
            return None

        try:
            decrypted_json = decrypt_data(connector.credentials_encrypted)
            return AppleCredentials.model_validate_json(decrypted_json)
        except Exception as e:
            logger.error(
                "apple_credentials_decryption_failed",
                connector_id=str(connector.id),
                error=str(e),
            )
            return None

    # =========================================================================
    # PHILIPS HUE (Smart Home)
    # =========================================================================

    async def get_hue_credentials(
        self,
        user_id: UUID,
    ) -> HueBridgeCredentials | None:
        """
        Get decrypted Hue Bridge credentials for a user.

        Args:
            user_id: User UUID.

        Returns:
            HueBridgeCredentials or None if not found/inactive.
        """
        connector = await self.repository.get_by_user_and_type(user_id, ConnectorType.PHILIPS_HUE)

        if not connector:
            return None

        if connector.status != ConnectorStatus.ACTIVE:
            logger.warning(
                "hue_connector_not_active",
                user_id=str(user_id),
                status=connector.status.value if connector.status else "unknown",
            )
            return None

        try:
            decrypted_json = decrypt_data(connector.credentials_encrypted)
            return HueBridgeCredentials.model_validate_json(decrypted_json)
        except Exception as e:
            logger.error(
                "hue_credentials_decryption_failed",
                connector_id=str(connector.id),
                error=str(e),
            )
            return None

    async def activate_hue_local(
        self,
        user_id: UUID,
        bridge_ip: str,
        application_key: str,
        client_key: str | None = None,
        bridge_id: str | None = None,
    ) -> ConnectorResponse:
        """
        Activate Philips Hue connector in local mode after press-link pairing.

        Args:
            user_id: User UUID.
            bridge_ip: Bridge internal IP address.
            application_key: Application key from press-link pairing.
            client_key: Entertainment API client key (optional).
            bridge_id: Bridge unique identifier (optional).

        Returns:
            ConnectorResponse with activated connector.

        Raises:
            ExternalServiceConnectionError: If bridge is unreachable.
        """
        from src.core.exceptions import raise_external_service_connection_error

        # 1. Build credentials
        credentials = HueBridgeCredentials(
            connection_mode=HueConnectionMode.LOCAL,
            api_key=application_key,
            bridge_ip=bridge_ip,
            bridge_id=bridge_id,
            client_key=client_key,
        )

        # 2. Validate connectivity
        from src.domains.connectors.clients.philips_hue_client import PhilipsHueClient

        test_client = PhilipsHueClient(user_id, credentials, self)
        try:
            await test_client.test_connection()
        except Exception as e:
            raise_external_service_connection_error(
                service_name="Philips Hue Bridge",
                detail=f"Cannot reach bridge at {bridge_ip}: {e}",
            )

        # 3. Encrypt credentials
        encrypted_credentials = encrypt_data(credentials.model_dump_json())

        # 4. Create or update connector
        existing = await self.repository.get_by_user_and_type(user_id, ConnectorType.PHILIPS_HUE)

        connector_metadata: dict[str, Any] = {
            "auth_type": "press_link",
            "connection_mode": "local",
            "bridge_ip": bridge_ip,
            "bridge_id": bridge_id,
        }

        if existing:
            existing.credentials_encrypted = encrypted_credentials
            existing.status = ConnectorStatus.ACTIVE
            existing.connector_metadata = connector_metadata
            await self.db.flush()
            await self.db.refresh(existing)
            connector = existing
        else:
            connector = Connector(
                user_id=user_id,
                connector_type=ConnectorType.PHILIPS_HUE,
                status=ConnectorStatus.ACTIVE,
                scopes=[],
                credentials_encrypted=encrypted_credentials,
                connector_metadata=connector_metadata,
            )
            self.db.add(connector)
            await self.db.flush()
            await self.db.refresh(connector)

        await self.db.commit()
        await self._invalidate_user_connectors_cache(user_id)

        logger.info(
            "hue_connector_activated_local",
            user_id=str(user_id),
            bridge_ip=bridge_ip,
            bridge_id=bridge_id,
        )

        return ConnectorResponse.model_validate(connector)

    async def initiate_hue_oauth(self, user_id: UUID) -> ConnectorOAuthInitiate:
        """
        Generate OAuth2 authorization URL for Hue Remote API.

        Args:
            user_id: User UUID.

        Returns:
            ConnectorOAuthInitiate with authorization URL and state token.
        """
        redis = await get_redis_session()
        session_service = SessionService(redis)

        from src.core.oauth import OAuthFlowHandler
        from src.core.oauth.providers.hue import HueOAuthProvider

        provider = HueOAuthProvider.for_remote_control(settings)
        flow_handler = OAuthFlowHandler(provider, session_service)
        auth_url, state = await flow_handler.initiate_flow(
            additional_params={"appid": provider.app_id, "deviceid": "lia-server"},
            metadata={
                FIELD_USER_ID: str(user_id),
                FIELD_CONNECTOR_TYPE: ConnectorType.PHILIPS_HUE.value,
            },
        )

        logger.info(
            "hue_oauth_initiated",
            user_id=str(user_id),
        )

        return ConnectorOAuthInitiate(authorization_url=auth_url, state=state)

    async def handle_hue_oauth_callback(
        self,
        code: str,
        state: str,
    ) -> Connector:
        """
        Handle Hue Remote API OAuth2 callback.

        Exchanges authorization code for tokens, creates a whitelist entry
        on the bridge via the remote API, and activates the connector.

        Args:
            code: Authorization code from Hue.
            state: CSRF state token.

        Returns:
            Activated Connector.

        Raises:
            OAuthFlowError: If state validation or token exchange fails.
        """
        from src.core.constants import (
            HTTP_TIMEOUT_HUE_API,
            HUE_PAIRING_DEVICE_TYPE,
            HUE_REMOTE_API_BASE_URL,
        )
        from src.core.oauth import OAuthFlowHandler
        from src.core.oauth.providers.hue import HueOAuthProvider

        # 1. Validate state + exchange code → tokens
        redis = await get_redis_session()
        session_service = SessionService(redis)
        provider = HueOAuthProvider.for_remote_control(settings)
        flow_handler = OAuthFlowHandler(provider, session_service)
        token_response, stored_state = await flow_handler.handle_callback(code, state)

        user_id = UUID(stored_state[FIELD_USER_ID])

        # 2. Create whitelist entry via remote API
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_HUE_API) as client:
            # Enable link button remotely
            await client.put(
                f"{HUE_REMOTE_API_BASE_URL}/bridge/0/config",
                headers={"Authorization": f"Bearer {token_response.access_token}"},
                json={"linkbutton": True},
            )
            # Create username
            resp = await client.post(
                f"{HUE_REMOTE_API_BASE_URL}/bridge",
                headers={"Authorization": f"Bearer {token_response.access_token}"},
                json={"devicetype": HUE_PAIRING_DEVICE_TYPE},
            )
            whitelist_result = resp.json()
            remote_username = whitelist_result[0]["success"]["username"]

        # 3. Build & store credentials
        credentials = HueBridgeCredentials(
            connection_mode=HueConnectionMode.REMOTE,
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(seconds=token_response.expires_in),
            remote_username=remote_username,
        )
        encrypted = encrypt_data(credentials.model_dump_json())

        # 4. Create or update connector
        existing = await self.repository.get_by_user_and_type(user_id, ConnectorType.PHILIPS_HUE)

        connector_metadata: dict[str, Any] = {
            "auth_type": "oauth2",
            "connection_mode": "remote",
            "remote_username": remote_username,
        }

        if existing:
            existing.credentials_encrypted = encrypted
            existing.status = ConnectorStatus.ACTIVE
            existing.connector_metadata = connector_metadata
            await self.db.flush()
            await self.db.refresh(existing)
            connector = existing
        else:
            connector = Connector(
                user_id=user_id,
                connector_type=ConnectorType.PHILIPS_HUE,
                status=ConnectorStatus.ACTIVE,
                scopes=[],
                credentials_encrypted=encrypted,
                connector_metadata=connector_metadata,
            )
            self.db.add(connector)
            await self.db.flush()
            await self.db.refresh(connector)

        await self.db.commit()
        await self._invalidate_user_connectors_cache(user_id)

        logger.info(
            "hue_connector_activated_remote",
            user_id=str(user_id),
            remote_username=remote_username,
        )

        return connector

    async def activate_apple_connectors(
        self,
        user_id: UUID,
        apple_id: str,
        app_password: str,
        services: list[ConnectorType],
    ) -> AppleActivationResponse:
        """
        Activate Apple iCloud connectors for a user.

        Tests connection once, then activates requested services with
        mutual exclusivity enforcement (deactivates conflicting Google connectors).

        Args:
            user_id: User UUID.
            apple_id: Apple ID (email).
            app_password: App-specific password.
            services: List of Apple ConnectorTypes to activate.

        Returns:
            AppleActivationResponse with activated and deactivated connectors.

        Raises:
            HTTPException: If connection test fails or services invalid.
        """
        # Validate all services are Apple types
        for svc in services:
            if not svc.is_apple:
                raise_invalid_input(
                    f"{svc.value} is not an Apple connector type",
                    connector_type=svc.value,
                )

        # Check global config enabled for each service
        for svc in services:
            await self._check_connector_enabled(svc)

        # Test connection once
        success, message = await self.test_apple_connection(apple_id, app_password, services)
        if not success:
            raise_invalid_input(message)

        # Encrypt credentials
        credentials = AppleCredentials(apple_id=apple_id, app_password=app_password)
        encrypted_credentials = encrypt_data(credentials.model_dump_json())

        activated_connectors: list[Connector] = []
        deactivated_connectors: list[Connector] = []

        for svc in services:
            # Mutual exclusivity: deactivate ALL conflicting connectors
            conflicting_types = get_conflicting_connector_types(svc)
            for conflicting_type in conflicting_types:
                conflicting = await self.repository.get_by_user_and_type(user_id, conflicting_type)
                if conflicting and conflicting.status == ConnectorStatus.ACTIVE:
                    await self.repository.update(
                        conflicting, {FIELD_STATUS: ConnectorStatus.INACTIVE}
                    )
                    deactivated_connectors.append(conflicting)
                    logger.info(
                        "apple_mutual_exclusivity_deactivated",
                        user_id=str(user_id),
                        deactivated_type=conflicting_type.value,
                        activated_type=svc.value,
                    )

            # Create or update Apple connector
            existing = await self.repository.get_by_user_and_type(user_id, svc)
            connector_data: dict[str, Any] = {
                FIELD_STATUS: ConnectorStatus.ACTIVE,
                "scopes": [],
                "credentials_encrypted": encrypted_credentials,
                "connector_metadata": {
                    "auth_type": "app_password",
                    "apple_id": apple_id,
                },
            }

            if existing:
                connector = await self.repository.update(existing, connector_data)
            else:
                connector = await self.repository.create(
                    {
                        FIELD_USER_ID: user_id,
                        FIELD_CONNECTOR_TYPE: svc,
                        **connector_data,
                    }
                )

            activated_connectors.append(connector)

        await self.db.commit()

        # Refresh all connectors to get post-commit state
        for connector in activated_connectors + deactivated_connectors:
            await self.db.refresh(connector)

        # Build responses AFTER commit+refresh for accurate data
        activated = [ConnectorResponse.model_validate(c) for c in activated_connectors]
        deactivated = [ConnectorResponse.model_validate(c) for c in deactivated_connectors]

        logger.info(
            "apple_connectors_activated",
            user_id=str(user_id),
            activated=[s.value for s in services],
            deactivated=[d.connector_type.value for d in deactivated],
        )

        # Invalidate cache
        await self._invalidate_user_connectors_cache(user_id)

        # Reset circuit breakers for activated services (may be stuck open)
        for svc in services:
            cb = get_circuit_breaker(svc.value)
            await cb.reset()

        return AppleActivationResponse(
            activated=activated,
            deactivated=deactivated,
        )

    async def test_apple_connection(
        self,
        apple_id: str,
        app_password: str,
        services: list[ConnectorType],
    ) -> tuple[bool, str]:
        """
        Test Apple iCloud credentials by connecting to relevant services.

        Tests only the first available protocol to minimize connection overhead.

        Args:
            apple_id: Apple ID.
            app_password: App-specific password.
            services: Services to test.

        Returns:
            Tuple (success, message).
        """
        import asyncio

        # Test IMAP if email service requested
        if ConnectorType.APPLE_EMAIL in services:
            try:

                def _test_imap() -> None:
                    from imap_tools import MailBox

                    with MailBox(settings.apple_imap_host, settings.apple_imap_port).login(
                        apple_id, app_password
                    ) as _mb:
                        pass  # Login successful if no exception

                await asyncio.to_thread(_test_imap)
                return True, "IMAP connection successful"
            except Exception as e:
                logger.warning(
                    "apple_imap_test_failed",
                    apple_id=apple_id,
                    error=str(e),
                )
                return False, f"IMAP connection failed: {e}"

        # Test CalDAV if calendar service requested
        if ConnectorType.APPLE_CALENDAR in services:
            try:

                def _test_caldav() -> None:
                    import caldav

                    client = caldav.DAVClient(
                        url=settings.apple_caldav_url,
                        username=apple_id,
                        password=app_password,
                    )
                    principal = client.principal()
                    _ = principal.calendars()  # Validates access

                await asyncio.to_thread(_test_caldav)
                return True, "CalDAV connection successful"
            except Exception as e:
                logger.warning(
                    "apple_caldav_test_failed",
                    apple_id=apple_id,
                    error=str(e),
                )
                return False, f"CalDAV connection failed: {e}"

        # Test CardDAV if contacts service requested
        if ConnectorType.APPLE_CONTACTS in services:
            try:
                async with httpx.AsyncClient(
                    auth=(apple_id, app_password),
                    timeout=settings.apple_connection_timeout,
                ) as client:
                    response = await client.request(
                        "PROPFIND",
                        settings.apple_carddav_url,
                        headers={"Depth": "0", "Content-Type": "application/xml"},
                        content=(
                            '<?xml version="1.0" encoding="UTF-8"?>'
                            '<d:propfind xmlns:d="DAV:">'
                            "<d:prop><d:current-user-principal/></d:prop>"
                            "</d:propfind>"
                        ),
                    )
                    if response.status_code in (207, 200):
                        return True, "CardDAV connection successful"
                    if response.status_code in (401, 403):
                        return False, "Invalid credentials"
                    return False, f"Unexpected response: HTTP {response.status_code}"
            except Exception as e:
                logger.warning(
                    "apple_carddav_test_failed",
                    apple_id=apple_id,
                    error=str(e),
                )
                return False, f"CardDAV connection failed: {e}"

        return False, "No Apple service selected"

    # Private helper methods

    def _get_oauth_refresh_config(self, connector_type: ConnectorType) -> dict[str, Any]:
        """
        Get provider-specific OAuth token refresh configuration.

        Data-driven approach (no if/else chain) for Open/Closed principle.

        Args:
            connector_type: The connector type to get config for.

        Returns:
            Dict with token_url, client_id, client_secret, include_scope.
        """
        if connector_type.is_google:
            return {
                "token_url": "https://oauth2.googleapis.com/token",
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "include_scope": False,
            }
        if connector_type.is_microsoft:
            from src.core.constants import MICROSOFT_OAUTH_TOKEN_ENDPOINT

            return {
                "token_url": MICROSOFT_OAUTH_TOKEN_ENDPOINT.format(
                    tenant=settings.microsoft_tenant_id
                ),
                "client_id": settings.microsoft_client_id,
                "client_secret": settings.microsoft_client_secret,
                "include_scope": True,  # Microsoft REQUIRES scope in refresh
            }
        raise ValueError(f"Unknown OAuth provider for {connector_type.value}")

    async def _refresh_oauth_token(
        self, connector: Connector, credentials: ConnectorCredentials
    ) -> ConnectorCredentials:
        """
        Refresh OAuth access token using refresh token.

        Provider-aware: supports Google and Microsoft token endpoints
        with provider-specific configuration.

        Args:
            connector: Connector model instance
            credentials: Current credentials with refresh_token

        Returns:
            Updated ConnectorCredentials with new access_token

        Raises:
            HTTPException: If refresh fails after retries
        """
        if not credentials.refresh_token:
            logger.error(
                "oauth_refresh_missing_refresh_token",
                connector_id=str(connector.id),
                connector_type=connector.connector_type.value,
                user_id=str(connector.user_id),
                expires_at=credentials.expires_at.isoformat() if credentials.expires_at else None,
            )
            raise_invalid_input(
                APIMessages.no_refresh_token_available(),
                connector_id=str(connector.id),
            )

        # Get provider-specific refresh configuration
        refresh_config = self._get_oauth_refresh_config(connector.connector_type)

        # Build refresh request data
        refresh_data: dict[str, str] = {
            "refresh_token": credentials.refresh_token,
            "client_id": refresh_config["client_id"],
            "client_secret": refresh_config["client_secret"],
            "grant_type": "refresh_token",
        }

        # Microsoft REQUIRES scope parameter in refresh token request
        if refresh_config["include_scope"] and connector.scopes:
            refresh_data["scope"] = " ".join(connector.scopes)

        token_url = refresh_config["token_url"]

        @retry(
            retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            reraise=True,
        )
        async def _refresh_token_with_retry() -> httpx.Response:
            """Refresh OAuth token with retry logic for network resilience."""
            async with httpx.AsyncClient(follow_redirects=False) as client:
                return await client.post(token_url, data=refresh_data)

        try:
            logger.debug(
                "oauth_token_refresh_starting",
                connector_id=str(connector.id),
                connector_type=connector.connector_type.value,
            )
            token_response = await _refresh_token_with_retry()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error(
                "oauth_token_refresh_network_failure",
                connector_id=str(connector.id),
                connector_type=connector.connector_type.value,
                user_id=str(connector.user_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            await self.repository.update(connector, {FIELD_STATUS: ConnectorStatus.ERROR})
            await self.db.commit()
            raise_invalid_input(
                APIMessages.oauth_token_refresh_failed(),
                connector_id=str(connector.id),
            )

        if token_response.status_code != 200:
            # Parse error response for better diagnostics
            error_body = token_response.text
            try:
                error_json = token_response.json()
                error_code = error_json.get("error", "unknown")
                error_description = error_json.get("error_description", error_body)
            except Exception:
                error_code = "parse_error"
                error_description = error_body

            logger.error(
                "oauth_token_refresh_rejected",
                connector_id=str(connector.id),
                connector_type=connector.connector_type.value,
                user_id=str(connector.user_id),
                status_code=token_response.status_code,
                error_code=error_code,
                error_description=error_description[:200] if error_description else None,
            )

            # Mark connector as error status
            await self.repository.update(connector, {FIELD_STATUS: ConnectorStatus.ERROR})
            await self.db.commit()

            # Provide user-friendly message based on error type
            if error_code == "invalid_grant":
                user_message = APIMessages.refresh_token_revoked()
            else:
                user_message = APIMessages.oauth_token_refresh_failed()

            raise_invalid_input(
                user_message,
                connector_id=str(connector.id),
                response_status_code=token_response.status_code,
            )

        token_data = token_response.json()

        # Update credentials
        new_access_token = token_data.get("access_token")

        # Use Google standard token lifetime (3599s) as default
        from src.core.constants import OAUTH_TOKEN_DEFAULT_LIFETIME_SECONDS

        expires_in = token_data.get("expires_in", OAUTH_TOKEN_DEFAULT_LIFETIME_SECONDS)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        # IMPORTANT: Update refresh_token if Google returns a new one
        # Google may return a new refresh_token in some cases (e.g., token rotation)
        # Always prefer the new token if provided, otherwise keep the existing one
        new_refresh_token = token_data.get("refresh_token")
        if new_refresh_token and new_refresh_token != credentials.refresh_token:
            logger.info(
                "oauth_refresh_token_rotated",
                connector_id=str(connector.id),
                old_token_prefix=(
                    credentials.refresh_token[:10] + "..." if credentials.refresh_token else None
                ),
                new_token_prefix=new_refresh_token[:10] + "...",
            )
        refresh_token_to_use = new_refresh_token or credentials.refresh_token

        new_credentials = ConnectorCredentials(
            access_token=new_access_token,
            refresh_token=refresh_token_to_use,
            token_type="Bearer",
            expires_at=expires_at,
        )

        # Encrypt and store new credentials
        encrypted_credentials = encrypt_data(new_credentials.model_dump_json())
        await self.repository.update_credentials(connector, encrypted_credentials)
        await self.db.commit()

        logger.info(
            "oauth_token_refreshed",
            connector_id=str(connector.id),
            expires_in_seconds=expires_in,
            refresh_token_updated=bool(new_refresh_token),
        )

        return new_credentials

    async def _revoke_oauth_token(self, connector: Connector) -> None:
        """Revoke OAuth token at provider (best effort). Skips non-OAuth connectors.

        Provider-isolated: counts only same-family connectors to decide revocation.
        - Microsoft has NO revocation endpoint → always skip.
        - Google: only revoke when this is the LAST active Google connector
          (all Google connectors share the same client_id / grant).
        """
        if not connector.connector_type.is_oauth:
            return  # Apple/API-key connectors don't have OAuth tokens

        # Microsoft has no revocation endpoint
        if connector.connector_type.is_microsoft:
            logger.info(
                "microsoft_token_revoke_skipped",
                connector_id=str(connector.id),
                connector_type=connector.connector_type.value,
                reason="no_revocation_endpoint",
            )
            return

        # Google: count only other Google OAuth connectors (not Microsoft)
        other_active_same_provider = 0
        for ct in ConnectorType.get_google_types():
            if ct == connector.connector_type:
                continue
            other = await self.repository.get_by_user_and_type(connector.user_id, ct)
            if other and other.status == ConnectorStatus.ACTIVE:
                other_active_same_provider += 1

        if other_active_same_provider > 0:
            logger.info(
                "oauth_token_revoke_skipped",
                connector_id=str(connector.id),
                connector_type=connector.connector_type.value,
                remaining_same_provider=other_active_same_provider,
                reason="other_google_connectors_still_active",
            )
            return  # Don't revoke — would invalidate other connectors' tokens

        try:
            # Last Google connector — safe to revoke the grant at Google
            decrypted_json = decrypt_data(connector.credentials_encrypted)
            credentials = ConnectorCredentials.model_validate_json(decrypted_json)

            async with httpx.AsyncClient(follow_redirects=False) as client:
                await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": credentials.access_token},
                )

            logger.info(
                "oauth_token_revoked",
                connector_id=str(connector.id),
                reason="last_google_connector",
            )

        except Exception as e:
            logger.warning(
                "oauth_token_revoke_failed",
                connector_id=str(connector.id),
                error=str(e),
            )
            # Continue anyway - local deletion is more important

    # ========== GOOGLE CONTACTS CONNECTOR ==========

    async def initiate_google_contacts_oauth(self, user_id: UUID) -> ConnectorOAuthInitiate:
        """
        Initiate Google Contacts OAuth flow with PKCE.

        Refactored (v0.4.0): Uses generic OAuthFlowHandler

        Args:
            user_id: User UUID

        Returns:
            ConnectorOAuthInitiate with authorization URL

        Raises:
            HTTPException: If Google Contacts connector is globally disabled
        """
        # Check if Google Contacts is globally enabled
        await self._check_connector_enabled(ConnectorType.GOOGLE_CONTACTS)

        # Use generic OAuth flow handler with PKCE
        redis = await get_redis_session()
        session_service = SessionService(redis)

        from src.core.oauth import GoogleOAuthProvider, OAuthFlowHandler

        provider = GoogleOAuthProvider.for_contacts(settings)
        flow_handler = OAuthFlowHandler(provider, session_service)

        # Initiate flow with Contacts-specific params and metadata
        auth_url, state = await flow_handler.initiate_flow(
            additional_params={
                "access_type": "offline",  # Get refresh token
                "prompt": "consent",  # Force re-consent to get refresh token
            },
            metadata={
                FIELD_USER_ID: str(user_id),
                FIELD_CONNECTOR_TYPE: ConnectorType.GOOGLE_CONTACTS.value,
            },
        )

        logger.info(
            "google_contacts_oauth_initiated",
            user_id=str(user_id),
            state=state,
            pkce=True,
        )

        return ConnectorOAuthInitiate(
            authorization_url=auth_url,
            state=state,
        )

    async def _handle_oauth_connector_callback_stateless(
        self,
        code: str,
        state: str,
        connector_type: ConnectorType,
        provider_factory_method: Callable[..., Any],
        default_scopes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConnectorResponse:
        """
        Generic OAuth callback handler WITHOUT session dependency (stateless).

        This is the foundational method for stateless OAuth callbacks.
        All connector-specific stateless handlers delegate to this method.

        Security Model:
        - Extracts user_id from OAuth state metadata (stored during initiation)
        - Validates state token (CSRF protection, single-use, 5min TTL)
        - Validates user exists and is active in database
        - OAuth state provides secure user identity without requiring session cookies

        Flow:
        1. Peek at OAuth state to extract user_id from metadata
        2. Verify user exists and is active (database lookup)
        3. Delegate to _handle_oauth_connector_callback with extracted user_id
        4. Generic handler validates user_id matches state (double validation)

        Args:
            code: Authorization code from OAuth provider
            state: CSRF state token
            connector_type: Type of connector (e.g., GMAIL, GOOGLE_CONTACTS)
            provider_factory_method: Factory method to create OAuth provider
            default_scopes: Default scopes if not returned by provider
            metadata: Additional metadata to store with connector

        Returns:
            ConnectorResponse with created/updated connector

        Raises:
            HTTPException 400: If state invalid, expired, or missing user_id
            HTTPException 404: If user not found
            HTTPException 403: If user is inactive
            HTTPException 400: If OAuth flow fails

        Architecture Notes:
        - Generic pattern applicable to ALL connector types
        - Follows same pattern as /auth/google/callback (no session dependency)
        - State-based user validation (OAuth 2.1 best practice)
        - Single-use state token prevents replay attacks
        - DRY principle: eliminates code duplication across connectors
        """
        from src.core.exceptions import raise_user_not_found

        # Step 1: Peek at state to extract user_id (without consuming state)
        redis = await get_redis_session()

        # Peek at state to get user_id
        state_key = f"oauth:state:{state}"
        state_data_raw = await redis.get(state_key)

        if not state_data_raw:
            logger.warning(
                f"{connector_type.value}_callback_invalid_state",
                state=state,
                reason="state_not_found_or_expired",
            )
            raise_oauth_flow_failed(
                connector_type.value,
                "Invalid or expired OAuth state. Please try connecting again.",
            )

        # Parse state data
        import json

        state_data = json.loads(state_data_raw)
        user_id_str = state_data.get(FIELD_USER_ID)

        if not user_id_str:
            logger.error(
                f"{connector_type.value}_callback_missing_user_id",
                state=state,
                state_data_keys=list(state_data.keys()),
            )
            raise_oauth_flow_failed(
                connector_type.value,
                "OAuth state missing user_id. This is a configuration error.",
            )

        # Convert to UUID
        try:
            user_id = UUID(user_id_str)
        except ValueError as e:
            logger.error(
                f"{connector_type.value}_callback_invalid_user_id_format",
                user_id_str=user_id_str,
                error=str(e),
            )
            raise_oauth_flow_failed(
                connector_type.value,
                "Invalid user_id format in OAuth state.",
            )

        # Step 2: Verify user exists and is active BEFORE processing OAuth
        from src.domains.users.repository import UserRepository

        user_repo = UserRepository(self.db)
        user = await user_repo.get_by_id(user_id)

        if not user:
            logger.warning(
                f"{connector_type.value}_callback_user_not_found",
                user_id=str(user_id),
                state=state,
            )
            raise_user_not_found(user_id)

        if not user.is_active:
            logger.warning(
                f"{connector_type.value}_callback_user_inactive",
                user_id=str(user_id),
                state=state,
            )
            from src.core.exceptions import raise_user_inactive

            raise_user_inactive(user_id)

        # Step 3: Delegate to generic handler (validates user_id again)
        logger.info(
            f"{connector_type.value}_callback_user_validated",
            user_id=str(user_id),
            email=user.email,
            state=state,
        )

        return await self._handle_oauth_connector_callback(
            user_id=user_id,
            code=code,
            state=state,
            connector_type=connector_type,
            provider_factory_method=provider_factory_method,
            default_scopes=default_scopes,
            metadata=metadata,
            user_email=user.email,
        )

    async def handle_google_contacts_callback_stateless(
        self, code: str, state: str
    ) -> ConnectorResponse:
        """
        Handle Google Contacts OAuth callback WITHOUT session dependency (stateless).

        See _handle_oauth_connector_callback_stateless() for detailed documentation.
        This method uses the generic stateless pattern.

        Args:
            code: Authorization code from Google
            state: CSRF state token

        Returns:
            ConnectorResponse with created/updated connector

        Raises:
            HTTPException: Various HTTP exceptions (see generic method docstring)
        """
        from src.core.oauth import GoogleOAuthProvider

        # Delegate to generic stateless handler
        return await self._handle_oauth_connector_callback_stateless(
            code=code,
            state=state,
            connector_type=ConnectorType.GOOGLE_CONTACTS,
            provider_factory_method=GoogleOAuthProvider.for_contacts,
            default_scopes=GOOGLE_CONTACTS_SCOPES,
            metadata={"created_via": "oauth_flow_stateless"},
        )

    # ========== GOOGLE CALENDAR CONNECTOR ==========

    async def initiate_google_calendar_oauth(self, user_id: UUID) -> ConnectorOAuthInitiate:
        """
        Initiate Google Calendar OAuth flow with PKCE.

        Args:
            user_id: User UUID

        Returns:
            ConnectorOAuthInitiate with authorization URL
        """
        # Check if Google Calendar is globally enabled
        await self._check_connector_enabled(ConnectorType.GOOGLE_CALENDAR)

        # Use generic OAuth flow handler with PKCE
        redis = await get_redis_session()
        session_service = SessionService(redis)

        from src.core.oauth import GoogleOAuthProvider, OAuthFlowHandler

        provider = GoogleOAuthProvider.for_calendar(settings)
        flow_handler = OAuthFlowHandler(provider, session_service)

        # Initiate flow with Calendar-specific params and metadata
        auth_url, state = await flow_handler.initiate_flow(
            additional_params={
                "access_type": "offline",
                "prompt": "consent",
            },
            metadata={
                FIELD_USER_ID: str(user_id),
                FIELD_CONNECTOR_TYPE: ConnectorType.GOOGLE_CALENDAR.value,
            },
        )

        logger.info(
            "google_calendar_oauth_initiated",
            user_id=str(user_id),
            state=state,
            pkce=True,
        )

        return ConnectorOAuthInitiate(
            authorization_url=auth_url,
            state=state,
        )

    async def handle_google_calendar_callback_stateless(
        self, code: str, state: str
    ) -> ConnectorResponse:
        """
        Handle Google Calendar OAuth callback WITHOUT session dependency (stateless).

        Args:
            code: Authorization code from Google
            state: CSRF state token

        Returns:
            ConnectorResponse with created/updated connector
        """
        from src.core.oauth import GoogleOAuthProvider
        from src.core.oauth.providers.google import GOOGLE_CALENDAR_SCOPES

        return await self._handle_oauth_connector_callback_stateless(
            code=code,
            state=state,
            connector_type=ConnectorType.GOOGLE_CALENDAR,
            provider_factory_method=GoogleOAuthProvider.for_calendar,
            default_scopes=GOOGLE_CALENDAR_SCOPES,
            metadata={"created_via": "oauth_flow_stateless"},
        )

    # ========== GOOGLE DRIVE CONNECTOR ==========

    async def initiate_google_drive_oauth(self, user_id: UUID) -> ConnectorOAuthInitiate:
        """
        Initiate Google Drive OAuth flow with PKCE.

        Args:
            user_id: User UUID

        Returns:
            ConnectorOAuthInitiate with authorization URL
        """
        # Check if Google Drive is globally enabled
        await self._check_connector_enabled(ConnectorType.GOOGLE_DRIVE)

        # Use generic OAuth flow handler with PKCE
        redis = await get_redis_session()
        session_service = SessionService(redis)

        from src.core.oauth import GoogleOAuthProvider, OAuthFlowHandler

        provider = GoogleOAuthProvider.for_drive(settings)
        flow_handler = OAuthFlowHandler(provider, session_service)

        # Initiate flow with Drive-specific params and metadata
        auth_url, state = await flow_handler.initiate_flow(
            additional_params={
                "access_type": "offline",
                "prompt": "consent",
            },
            metadata={
                FIELD_USER_ID: str(user_id),
                FIELD_CONNECTOR_TYPE: ConnectorType.GOOGLE_DRIVE.value,
            },
        )

        logger.info(
            "google_drive_oauth_initiated",
            user_id=str(user_id),
            state=state,
            pkce=True,
        )

        return ConnectorOAuthInitiate(
            authorization_url=auth_url,
            state=state,
        )

    async def handle_google_drive_callback_stateless(
        self, code: str, state: str
    ) -> ConnectorResponse:
        """
        Handle Google Drive OAuth callback WITHOUT session dependency (stateless).

        Args:
            code: Authorization code from Google
            state: CSRF state token

        Returns:
            ConnectorResponse with created/updated connector
        """
        from src.core.oauth import GoogleOAuthProvider
        from src.core.oauth.providers.google import GOOGLE_DRIVE_SCOPES

        return await self._handle_oauth_connector_callback_stateless(
            code=code,
            state=state,
            connector_type=ConnectorType.GOOGLE_DRIVE,
            provider_factory_method=GoogleOAuthProvider.for_drive,
            default_scopes=GOOGLE_DRIVE_SCOPES,
            metadata={"created_via": "oauth_flow_stateless"},
        )

    # ========== GOOGLE TASKS CONNECTOR ==========

    async def initiate_google_tasks_oauth(self, user_id: UUID) -> ConnectorOAuthInitiate:
        """
        Initiate Google Tasks OAuth flow with PKCE.

        Args:
            user_id: User UUID

        Returns:
            ConnectorOAuthInitiate with authorization URL
        """
        # Check if Google Tasks is globally enabled
        await self._check_connector_enabled(ConnectorType.GOOGLE_TASKS)

        # Use generic OAuth flow handler with PKCE
        redis = await get_redis_session()
        session_service = SessionService(redis)

        from src.core.oauth import GoogleOAuthProvider, OAuthFlowHandler

        provider = GoogleOAuthProvider.for_tasks(settings)
        flow_handler = OAuthFlowHandler(provider, session_service)

        # Initiate flow with Tasks-specific params and metadata
        auth_url, state = await flow_handler.initiate_flow(
            additional_params={
                "access_type": "offline",
                "prompt": "consent",
            },
            metadata={
                FIELD_USER_ID: str(user_id),
                FIELD_CONNECTOR_TYPE: ConnectorType.GOOGLE_TASKS.value,
            },
        )

        logger.info(
            "google_tasks_oauth_initiated",
            user_id=str(user_id),
            state=state,
            pkce=True,
        )

        return ConnectorOAuthInitiate(
            authorization_url=auth_url,
            state=state,
        )

    async def handle_google_tasks_callback_stateless(
        self, code: str, state: str
    ) -> ConnectorResponse:
        """
        Handle Google Tasks OAuth callback WITHOUT session dependency (stateless).

        Args:
            code: Authorization code from Google
            state: CSRF state token

        Returns:
            ConnectorResponse with created/updated connector
        """
        from src.core.oauth import GoogleOAuthProvider
        from src.core.oauth.providers.google import GOOGLE_TASKS_SCOPES

        return await self._handle_oauth_connector_callback_stateless(
            code=code,
            state=state,
            connector_type=ConnectorType.GOOGLE_TASKS,
            provider_factory_method=GoogleOAuthProvider.for_tasks,
            default_scopes=GOOGLE_TASKS_SCOPES,
            metadata={"created_via": "oauth_flow_stateless"},
        )

    # ========== MICROSOFT 365 CONNECTORS (OAuth) ==========

    async def _initiate_microsoft_oauth(
        self, user_id: UUID, connector_type: ConnectorType, provider_method_name: str
    ) -> ConnectorOAuthInitiate:
        """
        Generic Microsoft OAuth initiation (DRY for all 4 Microsoft connectors).

        Args:
            user_id: User UUID.
            connector_type: Microsoft connector type.
            provider_method_name: Factory method name on MicrosoftOAuthProvider.

        Returns:
            ConnectorOAuthInitiate with authorization URL.
        """
        await self._check_connector_enabled(connector_type)

        redis = await get_redis_session()
        session_service = SessionService(redis)

        from src.core.oauth import OAuthFlowHandler
        from src.core.oauth.providers.microsoft import MicrosoftOAuthProvider

        provider_factory = getattr(MicrosoftOAuthProvider, provider_method_name)
        provider = provider_factory(settings)
        flow_handler = OAuthFlowHandler(provider, session_service)

        auth_url, state = await flow_handler.initiate_flow(
            additional_params={"prompt": "consent"},  # Guarantees refresh_token on reconnect
            metadata={
                FIELD_USER_ID: str(user_id),
                FIELD_CONNECTOR_TYPE: connector_type.value,
            },
        )

        logger.info(
            f"{connector_type.value}_oauth_initiated",
            user_id=str(user_id),
            state=state,
            pkce=True,
        )

        return ConnectorOAuthInitiate(authorization_url=auth_url, state=state)

    async def initiate_microsoft_outlook_oauth(self, user_id: UUID) -> ConnectorOAuthInitiate:
        """Initiate Microsoft Outlook OAuth flow."""
        return await self._initiate_microsoft_oauth(
            user_id, ConnectorType.MICROSOFT_OUTLOOK, "for_outlook"
        )

    async def initiate_microsoft_calendar_oauth(self, user_id: UUID) -> ConnectorOAuthInitiate:
        """Initiate Microsoft Calendar OAuth flow."""
        return await self._initiate_microsoft_oauth(
            user_id, ConnectorType.MICROSOFT_CALENDAR, "for_calendar"
        )

    async def initiate_microsoft_contacts_oauth(self, user_id: UUID) -> ConnectorOAuthInitiate:
        """Initiate Microsoft Contacts OAuth flow."""
        return await self._initiate_microsoft_oauth(
            user_id, ConnectorType.MICROSOFT_CONTACTS, "for_contacts"
        )

    async def initiate_microsoft_tasks_oauth(self, user_id: UUID) -> ConnectorOAuthInitiate:
        """Initiate Microsoft To Do OAuth flow."""
        return await self._initiate_microsoft_oauth(
            user_id, ConnectorType.MICROSOFT_TASKS, "for_tasks"
        )

    async def handle_microsoft_outlook_callback_stateless(
        self, code: str, state: str
    ) -> ConnectorResponse:
        """Handle Microsoft Outlook OAuth callback (stateless)."""
        from src.core.constants import MICROSOFT_OUTLOOK_SCOPES
        from src.core.oauth.providers.microsoft import MicrosoftOAuthProvider

        return await self._handle_oauth_connector_callback_stateless(
            code=code,
            state=state,
            connector_type=ConnectorType.MICROSOFT_OUTLOOK,
            provider_factory_method=MicrosoftOAuthProvider.for_outlook,
            default_scopes=MICROSOFT_OUTLOOK_SCOPES,
            metadata={"created_via": "oauth_flow_stateless"},
        )

    async def handle_microsoft_calendar_callback_stateless(
        self, code: str, state: str
    ) -> ConnectorResponse:
        """Handle Microsoft Calendar OAuth callback (stateless)."""
        from src.core.constants import MICROSOFT_CALENDAR_SCOPES
        from src.core.oauth.providers.microsoft import MicrosoftOAuthProvider

        return await self._handle_oauth_connector_callback_stateless(
            code=code,
            state=state,
            connector_type=ConnectorType.MICROSOFT_CALENDAR,
            provider_factory_method=MicrosoftOAuthProvider.for_calendar,
            default_scopes=MICROSOFT_CALENDAR_SCOPES,
            metadata={"created_via": "oauth_flow_stateless"},
        )

    async def handle_microsoft_contacts_callback_stateless(
        self, code: str, state: str
    ) -> ConnectorResponse:
        """Handle Microsoft Contacts OAuth callback (stateless)."""
        from src.core.constants import MICROSOFT_CONTACTS_SCOPES
        from src.core.oauth.providers.microsoft import MicrosoftOAuthProvider

        return await self._handle_oauth_connector_callback_stateless(
            code=code,
            state=state,
            connector_type=ConnectorType.MICROSOFT_CONTACTS,
            provider_factory_method=MicrosoftOAuthProvider.for_contacts,
            default_scopes=MICROSOFT_CONTACTS_SCOPES,
            metadata={"created_via": "oauth_flow_stateless"},
        )

    async def handle_microsoft_tasks_callback_stateless(
        self, code: str, state: str
    ) -> ConnectorResponse:
        """Handle Microsoft To Do OAuth callback (stateless)."""
        from src.core.constants import MICROSOFT_TASKS_SCOPES
        from src.core.oauth.providers.microsoft import MicrosoftOAuthProvider

        return await self._handle_oauth_connector_callback_stateless(
            code=code,
            state=state,
            connector_type=ConnectorType.MICROSOFT_TASKS,
            provider_factory_method=MicrosoftOAuthProvider.for_tasks,
            default_scopes=MICROSOFT_TASKS_SCOPES,
            metadata={"created_via": "oauth_flow_stateless"},
        )

    # ========== GOOGLE PLACES CONNECTOR (API Key based) ==========

    async def activate_places_connector(self, user_id: UUID) -> ConnectorResponse:
        """
        Activate Google Places connector (simple toggle, uses global API key).

        Google Places now uses the global GOOGLE_API_KEY instead of per-user OAuth.
        This method creates/reactivates a connector record to mark it as "enabled".

        Args:
            user_id: User UUID

        Returns:
            ConnectorResponse with created/updated connector
        """
        # Check if Google Places is globally enabled
        await self._check_connector_enabled(ConnectorType.GOOGLE_PLACES)

        # Verify global API key is configured
        if not settings.google_api_key:
            raise_configuration_missing("google_places", "GOOGLE_API_KEY")

        # Check if connector exists
        existing = await self.repository.get_by_user_and_type(user_id, ConnectorType.GOOGLE_PLACES)

        if existing:
            # Reactivate if not already active
            if existing.status != ConnectorStatus.ACTIVE:
                existing.status = ConnectorStatus.ACTIVE
                existing.credentials_encrypted = "{}"
                existing.connector_metadata = {"auth_type": "global_api_key"}
                await self.db.commit()
                await self.db.refresh(existing)
                await self._invalidate_user_connectors_cache(user_id)

                logger.info(
                    "google_places_connector_reactivated",
                    user_id=str(user_id),
                    connector_id=str(existing.id),
                )
            return ConnectorResponse.model_validate(existing)

        # Create new connector (no credentials needed - uses global API key)
        connector = Connector(
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_PLACES,
            status=ConnectorStatus.ACTIVE,
            scopes=[],  # No OAuth scopes
            credentials_encrypted="{}",  # Empty - uses global API key
            connector_metadata={"auth_type": "global_api_key"},
        )
        self.db.add(connector)
        await self.db.commit()
        await self.db.refresh(connector)

        logger.info(
            "google_places_connector_activated",
            user_id=str(user_id),
            connector_id=str(connector.id),
        )

        await self._invalidate_user_connectors_cache(user_id)
        return ConnectorResponse.model_validate(connector)

    async def is_connector_active(self, user_id: UUID, connector_type: ConnectorType) -> bool:
        """
        Check if user has a specific connector enabled and active.

        Generic method for checking connector status, used by tools with
        uses_global_api_key=True and other connector checks.

        Args:
            user_id: User UUID
            connector_type: Type of connector to check

        Returns:
            True if connector exists and is active, False otherwise
        """
        connector = await self.repository.get_by_user_and_type(user_id, connector_type)
        return connector is not None and connector.status == ConnectorStatus.ACTIVE

    async def is_places_enabled(self, user_id: UUID) -> bool:
        """
        Check if user has Google Places connector enabled.

        Convenience method for Places-specific checks.

        Args:
            user_id: User UUID

        Returns:
            True if connector exists and is active, False otherwise
        """
        return await self.is_connector_active(user_id, ConnectorType.GOOGLE_PLACES)

    # ========== ADMIN - GLOBAL CONFIG ==========

    async def get_global_config_all(self) -> list[ConnectorGlobalConfigResponse]:
        """
        Get all connector global configurations (admin only).

        Returns:
            List of all ConnectorGlobalConfig records
        """
        configs = await self.repository.get_all_global_configs()
        return [ConnectorGlobalConfigResponse.model_validate(c) for c in configs]

    async def get_global_config(
        self, connector_type: ConnectorType
    ) -> ConnectorGlobalConfig | None:
        """
        Get global config for specific connector type.

        Args:
            connector_type: Type of connector

        Returns:
            ConnectorGlobalConfig if exists, None otherwise
        """
        config = await self.repository.get_global_config_by_type(connector_type)
        return config

    async def update_global_config(
        self,
        connector_type: ConnectorType,
        update_data: ConnectorGlobalConfigUpdate,
        admin_user_id: UUID,
    ) -> ConnectorGlobalConfigResponse:
        """
        Update or create global config for connector type (admin only).

        If disabling a connector type, also revokes all active connectors of that type.

        Args:
            connector_type: Type of connector
            update_data: Update data (is_enabled, disabled_reason)
            admin_user_id: ID of admin performing action

        Returns:
            Updated or created ConnectorGlobalConfig
        """
        # Check if config exists
        existing_config = await self.repository.get_global_config_by_type(connector_type)

        if existing_config:
            # Update existing
            config = await self.repository.update_global_config(
                connector_type=connector_type,
                is_enabled=update_data.is_enabled,
                disabled_reason=update_data.disabled_reason,
            )
        else:
            # Create new
            config = await self.repository.create_global_config(
                connector_type=connector_type,
                is_enabled=update_data.is_enabled,
                disabled_reason=update_data.disabled_reason,
            )

        # If disabling, revoke all active connectors of this type
        if not update_data.is_enabled:
            await self._revoke_all_connectors_by_type(connector_type)

        await self.db.commit()
        await self.db.refresh(config)

        logger.info(
            "connector_global_config_updated",
            connector_type=connector_type.value,
            is_enabled=update_data.is_enabled,
            disabled_reason=update_data.disabled_reason,
            admin_user_id=str(admin_user_id),
        )

        return ConnectorGlobalConfigResponse.model_validate(config)

    async def _check_connector_enabled(self, connector_type: ConnectorType) -> None:
        """
        Check if connector type is globally enabled.

        Raises:
            HTTPException: If connector is disabled
        """
        config = await self.get_global_config(connector_type)

        # If no config exists, assume enabled (default behavior)
        if config and not config.is_enabled:
            raise_permission_denied(
                action="use",
                resource_type=f"{connector_type.value} connector",
            )

    async def _revoke_all_connectors_by_type(self, connector_type: ConnectorType) -> None:
        """
        Revoke all active connectors of a specific type (when admin disables globally).
        Sends email notification to affected users.

        Args:
            connector_type: Type of connector to revoke
        """
        # Get all active connectors of this type (with user relationship loaded)
        connectors = await self.repository.get_all_connectors_by_type(
            connector_type, status=ConnectorStatus.ACTIVE
        )

        if not connectors:
            logger.info(
                "no_connectors_to_revoke",
                connector_type=connector_type.value,
            )
            return

        # Group connectors by user to send 1 email per user
        users_affected = {}
        revoked_count = 0

        for connector in connectors:
            # Revoke OAuth token at provider (best effort)
            await self._revoke_oauth_token(connector)

            # Update status to REVOKED
            await self.repository.update(connector, {FIELD_STATUS: ConnectorStatus.REVOKED})
            revoked_count += 1

            # Track affected users (avoid duplicate emails)
            user_id = str(connector.user_id)
            if user_id not in users_affected:
                users_affected[user_id] = connector.user

        await self.db.commit()

        # Send email notifications to affected users
        email_service = get_email_service()
        disabled_reason = None

        # Get the disabled_reason from global config
        config = await self.repository.get_global_config_by_type(connector_type)
        if config:
            disabled_reason = config.disabled_reason or APIMessages.reason_not_specified()

        email_sent_count = 0
        for user in users_affected.values():
            success = await email_service.send_connector_disabled_notification(
                user_email=user.email,
                user_name=user.full_name,
                connector_type=connector_type.value,
                reason=disabled_reason or APIMessages.reason_not_specified(),
            )
            if success:
                email_sent_count += 1

        logger.info(
            "connectors_revoked_by_type",
            connector_type=connector_type.value,
            revoked_count=revoked_count,
            users_notified=len(users_affected),
            emails_sent=email_sent_count,
        )

    # ========== API KEY CONNECTOR METHODS ==========

    async def activate_api_key_connector(
        self,
        user_id: UUID,
        connector_type: ConnectorType,
        api_key: str,
        api_secret: str | None = None,
        key_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConnectorResponse:
        """
        Activate a connector with API key authentication.

        Unlike OAuth connectors, API key connectors don't require a flow.
        The user provides the key directly and it's encrypted for storage.

        Args:
            user_id: User UUID
            connector_type: Type of connector
            api_key: API key for authentication
            api_secret: Optional API secret
            key_name: Optional user-defined name for the key
            metadata: Optional additional metadata

        Returns:
            ConnectorResponse with created/updated connector

        Raises:
            HTTPException: If connector type disabled or key validation fails
        """
        from src.domains.connectors.schemas import APIKeyCredentials

        # Check if connector type is globally enabled
        global_config = await self.repository.get_global_config_by_type(connector_type)
        if global_config and not global_config.is_enabled:
            raise_permission_denied(
                action="activate",
                resource_type="connector",
                user_id=user_id,
            )

        # Create credentials object
        credentials = APIKeyCredentials(
            api_key=api_key,
            api_secret=api_secret,
            key_name=key_name,
            expires_at=None,
        )

        # Encrypt credentials
        encrypted_credentials = encrypt_data(credentials.model_dump_json())

        # Build metadata
        connector_metadata = metadata or {}
        connector_metadata["auth_type"] = "api_key"
        connector_metadata["key_name"] = key_name
        connector_metadata["has_secret"] = bool(api_secret)
        connector_metadata["activated_at"] = datetime.now(UTC).isoformat()

        # Check if connector already exists
        existing = await self.repository.get_by_user_and_type(user_id, connector_type)

        if existing:
            # Update existing connector
            existing.credentials_encrypted = encrypted_credentials
            existing.status = ConnectorStatus.ACTIVE
            existing.connector_metadata = connector_metadata
            await self.db.flush()
            await self.db.refresh(existing)
            connector = existing

            logger.info(
                "api_key_connector_updated",
                user_id=str(user_id),
                connector_type=connector_type.value,
                connector_id=str(connector.id),
            )
        else:
            # Create new connector
            connector = Connector(
                user_id=user_id,
                connector_type=connector_type,
                status=ConnectorStatus.ACTIVE,
                scopes=[],  # API key connectors don't use scopes
                credentials_encrypted=encrypted_credentials,
                connector_metadata=connector_metadata,
            )
            self.db.add(connector)
            await self.db.flush()
            await self.db.refresh(connector)

            logger.info(
                "api_key_connector_created",
                user_id=str(user_id),
                connector_type=connector_type.value,
                connector_id=str(connector.id),
            )

        await self.db.commit()

        # Invalidate cache
        await self._invalidate_user_connectors_cache(user_id)

        return ConnectorResponse.model_validate(connector)

    async def validate_api_key(
        self,
        connector_type: ConnectorType,
        api_key: str,
        api_secret: str | None = None,
    ) -> tuple[bool, str]:
        """
        Validate an API key before activation.

        This method can be overridden by service-specific validators.
        Default implementation just checks key format.

        Args:
            connector_type: Type of connector
            api_key: API key to validate
            api_secret: Optional API secret

        Returns:
            Tuple of (is_valid, message)
        """
        # Basic validation
        if not api_key or len(api_key) < 8:
            return False, "API key must be at least 8 characters"

        # Check for placeholder values
        placeholder_patterns = ["your_", "api_key_here", "xxx", "placeholder"]
        if any(pattern in api_key.lower() for pattern in placeholder_patterns):
            return False, "Please enter a valid API key"

        # TODO: Add service-specific validation (e.g., make test API call)
        # This would be implemented per connector type

        return True, "API key format is valid"

    async def get_api_key_credentials(
        self, user_id: UUID, connector_type: ConnectorType
    ) -> APIKeyCredentials | None:
        """
        Get decrypted API key credentials for a connector.

        Args:
            user_id: User UUID
            connector_type: Type of connector

        Returns:
            APIKeyCredentials or None if not found/inactive
        """
        from src.domains.connectors.schemas import APIKeyCredentials

        connector = await self.repository.get_by_user_and_type(user_id, connector_type)

        if not connector:
            return None

        if connector.status == ConnectorStatus.REVOKED:
            raise_permission_denied(
                action="use",
                resource_type="connector",
                user_id=user_id,
            )

        if connector.status != ConnectorStatus.ACTIVE:
            logger.warning(
                "api_key_connector_not_active",
                user_id=str(user_id),
                connector_type=connector_type.value,
                status=connector.status,
            )
            return None

        # Decrypt credentials
        try:
            decrypted_json = decrypt_data(connector.credentials_encrypted)
            credentials = APIKeyCredentials.model_validate_json(decrypted_json)

            # Update last used timestamp in metadata
            if connector.connector_metadata:
                connector.connector_metadata["last_used_at"] = datetime.now(UTC).isoformat()
                await self.db.flush()

            return credentials

        except Exception as e:
            logger.error(
                "api_key_credentials_decryption_failed",
                connector_id=str(connector.id),
                error=str(e),
            )
            raise_invalid_input(
                "Failed to decrypt API key credentials",
                connector_id=str(connector.id),
            )

    # NOTE (PHASE 1.4): _mask_api_key() removed - duplicate of BaseAPIKeyClient._mask_api_key()
    # If needed elsewhere, use the version in base_api_key_client.py (line 178)
