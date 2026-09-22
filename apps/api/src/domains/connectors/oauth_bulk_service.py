"""Atomic activation of several logical connectors from one provider grant."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.oauth import GoogleOAuthProvider, MicrosoftOAuthProvider, OAuthFlowHandler
from src.core.oauth.flow_handler import OAuthTokenResponse
from src.core.security import encrypt_data
from src.domains.connectors.models import (
    Connector,
    ConnectorGlobalConfig,
    ConnectorStatus,
    ConnectorType,
    OAuthGrant,
)
from src.domains.connectors.oauth_bulk import (
    ReconnectionPlan,
    connectable_provider_types,
    plan_connection,
    plan_reconnection,
    scopes_cover_connector,
    scopes_for_connector,
)
from src.domains.connectors.oauth_identity import (
    ProviderIdentity,
    fetch_provider_keys,
    verify_provider_identity,
)
from src.domains.connectors.schemas import ConnectorCredentials, ConnectorOAuthInitiate
from src.domains.connectors.service import ConnectorService
from src.domains.users.models import User
from src.infrastructure.cache.redis import SessionService, get_redis_cache, get_redis_session

logger = structlog.get_logger(__name__)


class OAuthAccountMismatchError(ValueError):
    """The signed provider identity differs from the selected known account."""


def _bulk_provider(
    provider: str, scopes: tuple[str, ...]
) -> GoogleOAuthProvider | MicrosoftOAuthProvider:
    """Same registered OAuth client, with one callback for the grouped grant."""
    base: GoogleOAuthProvider | MicrosoftOAuthProvider
    if provider == "google":
        base = GoogleOAuthProvider.for_gmail(settings)
    elif provider == "microsoft":
        base = MicrosoftOAuthProvider.for_outlook(settings)
    else:
        raise ValueError("Unsupported OAuth provider")
    return replace(
        base,
        redirect_uri=f"{settings.api_url}{settings.api_prefix}/connectors/oauth-bulk/{provider}/callback",
        scopes=list(scopes),
    )


@dataclass(frozen=True)
class BulkReconnectResult:
    """Actual entitlements, never the scopes merely requested."""

    activated: tuple[ConnectorType, ...]
    denied: tuple[ConnectorType, ...]
    grant_id: UUID | None
    mode: str = "reconnect"


class BulkOAuthService:
    """Own the shared credential transition for Google and Microsoft services."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def initiate_reconnection(
        self, user_id: UUID, provider: str, selected: list[ConnectorType]
    ) -> ConnectorOAuthInitiate:
        """Issue one PKCE URL for explicitly selected broken services on one account."""
        rows = list(
            (await self.db.scalars(select(Connector).where(Connector.user_id == user_id))).all()
        )
        plan = plan_reconnection(provider, rows, selected)
        return await self._initiate(user_id, provider, plan, rows, mode="reconnect")

    async def initiate_connect_all(
        self, user_id: UUID, provider: str, grant_id: UUID | None = None
    ) -> ConnectorOAuthInitiate:
        """Authorize all absent and eligible services with one chosen account."""
        rows = list(
            (await self.db.scalars(select(Connector).where(Connector.user_id == user_id))).all()
        )
        disabled = {
            config.connector_type
            for config in (
                await self.db.scalars(
                    select(ConnectorGlobalConfig).where(ConnectorGlobalConfig.is_enabled.is_(False))
                )
            ).all()
        }
        selected = list(connectable_provider_types(provider, rows, disabled=disabled))
        plan = plan_connection(provider, rows, selected, expected_grant_id=grant_id)
        return await self._initiate(user_id, provider, plan, rows, mode="connect")

    async def _initiate(
        self,
        user_id: UUID,
        provider: str,
        plan: ReconnectionPlan,
        rows: list[Connector],
        *,
        mode: str,
    ) -> ConnectorOAuthInitiate:
        connector_service = ConnectorService(self.db)
        for connector_type in plan.connector_types:
            await connector_service._check_connector_enabled(connector_type)

        scopes, login_hint = await self._account_context(user_id, provider, plan, rows)

        nonce = token_urlsafe(24)
        prompt = "consent"
        if mode == "connect" and not plan.expected_grant_id:
            prompt = "select_account consent" if provider == "google" else "select_account"
        params = {"prompt": prompt, "nonce": nonce}
        if provider == "google":
            params["access_type"] = "offline"
        if login_hint:
            params["login_hint"] = login_hint
        oauth_provider = _bulk_provider(provider, tuple(dict.fromkeys(scopes)))
        redis = await get_redis_session()
        flow = OAuthFlowHandler(oauth_provider, SessionService(redis))
        url, state = await flow.initiate_flow(
            additional_params=params,
            metadata={
                "bulk_provider": provider,
                "user_id": str(user_id),
                "connector_types": ",".join(ct.value for ct in plan.connector_types),
                "expected_grant_id": str(plan.expected_grant_id or ""),
                "nonce": nonce,
                "bulk_mode": mode,
            },
        )
        return ConnectorOAuthInitiate(authorization_url=url, state=state)

    async def _account_context(
        self, user_id: UUID, provider: str, plan: ReconnectionPlan, rows: list[Connector]
    ) -> tuple[list[str], str | None]:
        """Preserve the selected account's active service scopes during incremental consent."""
        scopes = list(plan.scopes)
        if plan.expected_grant_id is None:
            return scopes, None
        grant = await self.db.scalar(
            select(OAuthGrant).where(
                OAuthGrant.id == plan.expected_grant_id,
                OAuthGrant.user_id == user_id,
                OAuthGrant.provider == provider,
            )
        )
        if grant is None or grant.client_id != _bulk_provider(provider, ()).client_id:
            raise ValueError("Selected account grant is missing")
        for row in rows:
            if row.oauth_grant_id == grant.id and row.status == ConnectorStatus.ACTIVE:
                scopes.extend(scopes_for_connector(row.connector_type))
        return scopes, grant.email

    async def complete_callback(self, provider: str, code: str, state: str) -> BulkReconnectResult:
        """Consume the one-time state and validate account/scopes before writing."""
        oauth_provider = _bulk_provider(provider, ())
        redis = await get_redis_session()
        flow = OAuthFlowHandler(oauth_provider, SessionService(redis))
        tokens, stored = await flow.handle_callback(code, state)
        if stored.get("bulk_provider") != provider:
            raise ValueError("OAuth state does not belong to this bulk flow")
        try:
            user_id = UUID(stored["user_id"])
            selected = [ConnectorType(value) for value in stored["connector_types"].split(",")]
            expected = stored["expected_grant_id"]
            nonce = stored["nonce"]
            mode = stored.get("bulk_mode", "reconnect")
            if mode not in {"connect", "reconnect"}:
                raise ValueError("Unknown OAuth bulk mode")
            expected_id = UUID(expected) if expected else None
        except (KeyError, ValueError) as error:
            raise ValueError("OAuth state is malformed") from error
        if not tokens.id_token:
            raise ValueError("Provider did not issue an identity token")
        account = verify_provider_identity(
            provider,
            tokens.id_token,
            await fetch_provider_keys(provider),
            client_id=oauth_provider.client_id,
            nonce=nonce,
            access_token=tokens.access_token,
        )
        rows = list(
            (await self.db.scalars(select(Connector).where(Connector.user_id == user_id))).all()
        )
        plan = (
            plan_connection(provider, rows, selected, expected_grant_id=expected_id)
            if mode == "connect"
            else plan_reconnection(provider, rows, selected)
        )
        if str(plan.expected_grant_id or "") != expected:
            raise OAuthAccountMismatchError("Selected account changed during authorization")
        result = await self.activate_from_tokens(
            user_id, provider, plan, account, tokens, oauth_provider.client_id, mode=mode
        )
        if result.activated:
            try:
                cache = await get_redis_cache()
                await cache.delete(f"user_connectors:{user_id}")
            except Exception as error:
                logger.warning(
                    "bulk_oauth_cache_invalidation_failed", error_type=type(error).__name__
                )
        return result

    async def activate_from_tokens(
        self,
        user_id: UUID,
        provider: str,
        plan: ReconnectionPlan,
        account: ProviderIdentity,
        tokens: OAuthTokenResponse,
        client_id: str,
        *,
        mode: str = "reconnect",
    ) -> BulkReconnectResult:
        """Validate the callback again under a user lock, then commit once."""
        if not tokens.refresh_token or not tokens.access_token:
            raise ValueError("Provider did not issue offline credentials")
        if not tokens.scope:
            raise ValueError("Provider did not disclose granted scopes")
        if provider not in {"google", "microsoft"}:
            raise ValueError("Unsupported OAuth provider")
        if mode not in {"connect", "reconnect"}:
            raise ValueError("Unsupported bulk OAuth mode")

        actual_scopes = set(tokens.scope.split())
        grant, rows = await self._lock_account_and_connectors(
            user_id, provider, plan, account, client_id, mode
        )
        connector_service = ConnectorService(self.db)
        for connector_type in plan.connector_types:
            await connector_service._check_connector_enabled(connector_type)

        activated = tuple(
            ct for ct in plan.connector_types if scopes_cover_connector(ct, actual_scopes)
        )
        denied = tuple(ct for ct in plan.connector_types if ct not in activated)
        if not activated:
            return BulkReconnectResult((), denied, None, mode)

        grant_id = await self._persist_activation(
            user_id, provider, account, tokens, client_id, actual_scopes, grant, rows, activated
        )
        return BulkReconnectResult(activated, denied, grant_id, mode)

    async def _persist_activation(
        self,
        user_id: UUID,
        provider: str,
        account: ProviderIdentity,
        tokens: OAuthTokenResponse,
        client_id: str,
        actual_scopes: set[str],
        grant: OAuthGrant | None,
        rows: list[Connector],
        activated: tuple[ConnectorType, ...],
    ) -> UUID:
        """Atomically replace one account grant and activate its approved services."""

        # Existing active services on this grant must remain usable. A partial
        # consent can deny a newly selected service, but never break siblings.
        siblings: list[Connector] = []
        if grant is not None:
            siblings = list(
                (
                    await self.db.scalars(
                        select(Connector)
                        .where(Connector.oauth_grant_id == grant.id)
                        .with_for_update()
                    )
                ).all()
            )
            if any(
                sibling.status == ConnectorStatus.ACTIVE
                and not scopes_cover_connector(sibling.connector_type, actual_scopes)
                for sibling in siblings
            ):
                raise ValueError("Consent would remove access from an active service")

        expires_at = datetime.now(UTC) + timedelta(seconds=tokens.expires_in or 3599)
        credentials = ConnectorCredentials(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_type=tokens.token_type,
            expires_at=expires_at,
        )
        encrypted = encrypt_data(credentials.model_dump_json())
        if grant is None:
            grant = OAuthGrant(
                user_id=user_id,
                provider=provider,
                client_id=client_id,
                subject=account.subject,
                email=account.email,
                scopes=sorted(actual_scopes),
                credentials_encrypted=encrypted,
            )
            self.db.add(grant)
            await self.db.flush()
        else:
            grant.email = account.email
            grant.scopes = sorted(actual_scopes)
            grant.credentials_encrypted = encrypted

        by_type = {row.connector_type: row for row in rows}
        for connector_type in activated:
            row = by_type.get(connector_type)
            if row is None:
                row = Connector(user_id=user_id, connector_type=connector_type)
                self.db.add(row)
            row.oauth_grant_id = grant.id
            row.status = ConnectorStatus.ACTIVE
            row.scopes = sorted(actual_scopes)
            # Legacy readers and reversible migration keep a synchronized copy.
            row.credentials_encrypted = encrypted
            row.connector_metadata = {
                **(row.connector_metadata or {}),
                "oauth_account_email": account.email,
            }
        for sibling in siblings:
            if sibling.connector_type not in activated:
                sibling.credentials_encrypted = encrypted
        await self.db.commit()
        return grant.id

    async def _lock_account_and_connectors(
        self,
        user_id: UUID,
        provider: str,
        plan: ReconnectionPlan,
        account: ProviderIdentity,
        client_id: str,
        mode: str,
    ) -> tuple[OAuthGrant | None, list[Connector]]:
        """Serialize callback against refresh and reject account changes."""
        user = await self.db.scalar(
            select(User).where(User.id == user_id, User.is_active.is_(True)).with_for_update()
        )
        if user is None:
            raise ValueError("OAuth account owner is inactive or missing")
        # Refresh and deletion lock the grant before its connector rows. Keep
        # the same order here so an in-flight refresh cannot deadlock a callback.
        grant = await self.db.scalar(
            select(OAuthGrant)
            .where(
                OAuthGrant.user_id == user_id,
                OAuthGrant.provider == provider,
                OAuthGrant.client_id == client_id,
                OAuthGrant.subject == account.subject,
            )
            .with_for_update()
        )
        if plan.expected_grant_id and (grant is None or grant.id != plan.expected_grant_id):
            raise OAuthAccountMismatchError("Provider account differs from the selected account")
        rows = list(
            (
                await self.db.scalars(
                    select(Connector).where(Connector.user_id == user_id).with_for_update()
                )
            ).all()
        )
        current_plan = (
            plan_connection(
                provider, rows, list(plan.connector_types), expected_grant_id=plan.expected_grant_id
            )
            if mode == "connect"
            else plan_reconnection(provider, rows, list(plan.connector_types))
        )
        if current_plan.expected_grant_id != plan.expected_grant_id:
            raise OAuthAccountMismatchError("Connector account changed during OAuth authorization")
        return grant, rows
