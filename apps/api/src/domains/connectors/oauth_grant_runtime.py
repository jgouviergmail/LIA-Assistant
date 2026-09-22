"""One refresh owner for all services using a provider account grant."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.core.constants import OAUTH_TOKEN_REFRESH_MARGIN_SECONDS
from src.core.exceptions import ConnectorTokenExpiredError, raise_invalid_input
from src.core.i18n_api_messages import APIMessages
from src.core.security import decrypt_data, encrypt_data
from src.domains.connectors.models import Connector, ConnectorStatus, OAuthGrant
from src.domains.connectors.oauth_bulk import scopes_cover_connector
from src.domains.connectors.schemas import ConnectorCredentials
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)


async def invalidate_oauth_connector_cache(user_id: UUID) -> None:
    """Invalidate settings after a durable OAuth transition, without masking it on Redis outage."""
    try:
        cache = await get_redis_cache()
        await cache.delete(f"user_connectors:{user_id}")
    except Exception as error:
        logger.warning(
            "oauth_connector_cache_invalidation_failed",
            user_id=str(user_id),
            error_type=type(error).__name__,
        )


def _refresh_config(provider: str) -> tuple[str, str, str]:
    if provider == "google":
        return (
            "https://oauth2.googleapis.com/token",
            settings.google_client_id,
            settings.google_client_secret,
        )
    if provider == "microsoft":
        from src.core.constants import MICROSOFT_OAUTH_TOKEN_ENDPOINT

        return (
            MICROSOFT_OAUTH_TOKEN_ENDPOINT.format(tenant=settings.microsoft_tenant_id),
            settings.microsoft_client_id,
            settings.microsoft_client_secret,
        )
    raise ValueError("Unsupported OAuth grant provider")


@retry(
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def _post_refresh(url: str, data: dict[str, str]) -> httpx.Response:
    async with httpx.AsyncClient(
        timeout=settings.http_timeout_oauth, follow_redirects=False
    ) as client:
        response = await client.post(url, data=data)
        if response.status_code == 429 or response.status_code >= 500:
            response.raise_for_status()
        return response


class OAuthGrantRuntime:
    """Read or refresh a grant under a database row lock when necessary."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def credentials_for(
        self, connector: Connector, *, force: bool = False, refresh_before: datetime | None = None
    ) -> ConnectorCredentials:
        if connector.oauth_grant_id is None:
            raise ValueError("Connector has no shared OAuth grant")
        query = select(OAuthGrant).where(
            OAuthGrant.id == connector.oauth_grant_id,
            OAuthGrant.user_id == connector.user_id,
        )
        grant = await self.db.scalar(query)
        if grant is None or not self._same_provider(connector, grant):
            raise ValueError("Connector OAuth grant is missing or belongs to another account")
        credentials = self._decrypt(grant)
        if not force and not self._needs_refresh(credentials, refresh_before):
            return credentials
        previous_ciphertext = grant.credentials_encrypted

        # populate_existing is essential: a concurrent worker may have rotated
        # the token while this transaction waited on the row lock.
        grant = await self.db.scalar(
            query.with_for_update().execution_options(populate_existing=True)
        )
        if grant is None:
            raise ValueError("OAuth grant disappeared during refresh")
        credentials = self._decrypt(grant)
        if force and grant.credentials_encrypted != previous_ciphertext:
            return credentials
        if not force and not self._needs_refresh(credentials, refresh_before):
            return credentials
        return await self._refresh(grant, credentials)

    @staticmethod
    def _same_provider(connector: Connector, grant: OAuthGrant) -> bool:
        return (grant.provider == "google" and connector.connector_type.is_google) or (
            grant.provider == "microsoft" and connector.connector_type.is_microsoft
        )

    @staticmethod
    def _decrypt(grant: OAuthGrant) -> ConnectorCredentials:
        return ConnectorCredentials.model_validate_json(decrypt_data(grant.credentials_encrypted))

    @staticmethod
    def _needs_refresh(
        credentials: ConnectorCredentials, refresh_before: datetime | None = None
    ) -> bool:
        if credentials.expires_at is None:
            return False
        threshold = refresh_before or datetime.now(UTC) + timedelta(
            seconds=OAUTH_TOKEN_REFRESH_MARGIN_SECONDS
        )
        return credentials.expires_at < threshold

    async def _refresh(
        self, grant: OAuthGrant, credentials: ConnectorCredentials
    ) -> ConnectorCredentials:
        if not credentials.refresh_token:
            await self._mark_grant_error(grant)
            raise ConnectorTokenExpiredError(
                APIMessages.no_refresh_token_available(),
                connector_type=grant.provider,
                connector_id=str(grant.id),
            )
        url, configured_client_id, client_secret = _refresh_config(grant.provider)
        if grant.client_id != configured_client_id:
            raise ValueError("OAuth client changed; interactive reconnection required")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": credentials.refresh_token,
            "client_id": grant.client_id,
            "client_secret": client_secret,
        }
        if grant.provider == "microsoft":
            # Microsoft requires the Graph scopes again; OIDC-only scopes are
            # absent from an access token's scope response.
            data["scope"] = " ".join(grant.scopes)
        try:
            response = await _post_refresh(url, data)
        except httpx.RequestError, httpx.HTTPStatusError:
            # Temporary outages and rate limits must not become "reconnect".
            raise_invalid_input(APIMessages.oauth_token_refresh_failed(), grant_id=str(grant.id))
        if response.status_code != 200:
            error_code = self._error_code(response)
            if error_code in {"invalid_grant", "interaction_required"}:
                await self._mark_grant_error(grant)
                raise ConnectorTokenExpiredError(
                    APIMessages.refresh_token_revoked(),
                    connector_type=grant.provider,
                    connector_id=str(grant.id),
                    response_status_code=response.status_code,
                )
            raise_invalid_input(APIMessages.oauth_token_refresh_failed(), grant_id=str(grant.id))

        try:
            payload = response.json()
        except ValueError:
            raise_invalid_input(APIMessages.oauth_token_refresh_failed(), grant_id=str(grant.id))
        if not isinstance(payload, dict):
            raise_invalid_input(APIMessages.oauth_token_refresh_failed(), grant_id=str(grant.id))
        reported_scope = payload.get("scope", "")
        if not isinstance(reported_scope, str):
            raise_invalid_input(APIMessages.oauth_token_refresh_failed(), grant_id=str(grant.id))
        new_credentials = self._parse_success(payload, credentials)
        actual_scopes = set(reported_scope.split()) or set(grant.scopes)
        encrypted = encrypt_data(new_credentials.model_dump_json())
        grant.credentials_encrypted = encrypted
        grant.scopes = sorted(actual_scopes)
        linked = await self._linked(grant)
        for connector in linked:
            connector.credentials_encrypted = encrypted
            if connector.status == ConnectorStatus.ACTIVE and not scopes_cover_connector(
                connector.connector_type, actual_scopes
            ):
                connector.status = ConnectorStatus.ERROR
        await self.db.commit()
        await invalidate_oauth_connector_cache(grant.user_id)
        logger.info("oauth_grant_refreshed", grant_id=str(grant.id), provider=grant.provider)
        return new_credentials

    @staticmethod
    def _error_code(response: httpx.Response) -> str:
        try:
            payload: Any = response.json()
            return str(payload.get("error", "")) if isinstance(payload, dict) else ""
        except ValueError:
            return ""

    @staticmethod
    def _parse_success(
        payload: dict[str, Any], current: ConnectorCredentials
    ) -> ConnectorCredentials:
        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in", 3599)
        if (
            not isinstance(access_token, str)
            or not access_token
            or type(expires_in) is not int
            or expires_in <= 0
        ):
            raise_invalid_input(APIMessages.oauth_token_refresh_failed())
        refresh_token = payload.get("refresh_token") or current.refresh_token
        if not isinstance(refresh_token, str) or not refresh_token:
            raise_invalid_input(APIMessages.oauth_token_refresh_failed())
        return ConnectorCredentials(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        )

    async def _linked(self, grant: OAuthGrant) -> list[Connector]:
        return list(
            (
                await self.db.scalars(
                    select(Connector).where(Connector.oauth_grant_id == grant.id).with_for_update()
                )
            ).all()
        )

    async def _mark_grant_error(self, grant: OAuthGrant) -> None:
        for connector in await self._linked(grant):
            if connector.status == ConnectorStatus.ACTIVE:
                connector.status = ConnectorStatus.ERROR
        await self.db.commit()
        await invalidate_oauth_connector_cache(grant.user_id)
