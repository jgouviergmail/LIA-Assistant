"""The three holders of a refreshable token, as the refresh door sees them (audit AC-029).

A token lives in one of two stores, each keeping its own format: a connector row (a
legacy OAuth connector, or a Hue bridge in remote mode) or a shared grant whose linked
connectors carry its copy (ADR-302). Each target reads its store, writes it ONLY when
the stored token is still the one its exchange started from, and marks its holder in
error ONLY when the refused token is still the stored one — the door decides when to
call which (``oauth_refresh.py``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.card_composition import ensure_composition_account
from src.core.constants import OAUTH_TOKEN_REFRESH_MARGIN_SECONDS
from src.core.exceptions import ConnectorTokenExpiredError, ValidationError
from src.core.i18n_api_messages import APIMessages
from src.core.security import decrypt_data, encrypt_data
from src.domains.connectors.errors import ConnectorRevokedError
from src.domains.connectors.legacy_oauth_binding import bind_legacy_oauth_account
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType, OAuthGrant
from src.domains.connectors.oauth_bulk import scopes_cover_connector
from src.domains.connectors.oauth_refresh import (
    Refreshed,
    RefreshTarget,
    StoredToken,
    ensure_fresh_credentials,
)
from src.domains.connectors.oauth_refresh_exchange import (
    RefreshRefusal,
    RefreshRefused,
    exchange_refresh_token,
    hue_remote_endpoint,
    oauth_endpoint,
)
from src.domains.connectors.schemas import (
    ConnectorCredentials,
    HueBridgeCredentials,
    HueConnectionMode,
)

#: The statuses a holder may be refreshed in.
_REFRESHABLE: Final = ConnectorStatus.ACTIVE


def expires_before(expires_at: datetime | None, refresh_before: datetime | None) -> bool:
    """Whether a token expiring at ``expires_at`` needs a refresh.

    Args:
        expires_at: The token's expiry; None for a token that does not expire.
        refresh_before: The threshold; None means now plus the on-demand margin.

    Returns:
        True when the token expires before the threshold.
    """
    if expires_at is None:
        return False
    threshold = refresh_before or datetime.now(UTC) + timedelta(
        seconds=OAUTH_TOKEN_REFRESH_MARGIN_SECONDS
    )
    return expires_at < threshold


def _failed(**context: str) -> Exception:
    return ValidationError(detail=APIMessages.oauth_token_refresh_failed(), **context)


class ConnectorTokenTarget[C: BaseModel]:
    """A token stored in its connector's own row, in that connector's own format."""

    def __init__(
        self,
        connector: Connector,
        *,
        kind: str,
        decode: Callable[[Connector, str], C],
        exchange: Callable[[Connector, C], Awaitable[Refreshed[C]]],
        needs_refresh: Callable[[C, datetime | None], bool],
    ) -> None:
        """Bind the target to one connector row.

        Args:
            connector: The row the caller read; only its identity and type are kept.
            kind: The metrics label.
            decode: Decrypted JSON to credentials, given the row it was read from.
            exchange: The provider exchange for these credentials.
            needs_refresh: The expiry rule for these credentials.
        """
        self._connector_id = connector.id
        self._user_id = connector.user_id
        self._connector_type = connector.connector_type
        self._kind = kind
        self._decode = decode
        self._exchange = exchange
        self._needs_refresh = needs_refresh
        self._row: Connector | None = None
        self._status: ConnectorStatus | None = connector.status

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def flight_key(self) -> str:
        return f"connector:{self._connector_id}"

    @property
    def user_id(self) -> UUID:
        return self._user_id

    def stored(self, connector: Connector) -> StoredToken[C]:
        """What the caller already read, for the door's fast path."""
        return self._snapshot(connector)

    async def read(self, db: AsyncSession) -> StoredToken[C] | None:
        row = await db.scalar(
            select(Connector)
            .where(Connector.id == self._connector_id)
            .execution_options(populate_existing=True)
        )
        self._status = row.status if row is not None else None
        return None if row is None else self._snapshot(row)

    def _snapshot(self, row: Connector) -> StoredToken[C]:
        self._row = row
        credentials = self._decode(row, decrypt_data(row.credentials_encrypted))
        return StoredToken(row.credentials_encrypted, credentials, row.status == _REFRESHABLE)

    def needs_refresh(self, credentials: C, refresh_before: datetime | None) -> bool:
        return self._needs_refresh(credentials, refresh_before)

    async def exchange(self, credentials: C) -> Refreshed[C]:
        if self._row is None:  # the door always reads before it exchanges
            raise RuntimeError("connector token exchanged before it was read")
        return await self._exchange(self._row, credentials)

    async def write_if_unchanged(
        self, db: AsyncSession, expected_ciphertext: str, refreshed: Refreshed[C]
    ) -> bool:
        written = await db.execute(
            update(Connector)
            .where(
                Connector.id == self._connector_id,
                Connector.credentials_encrypted == expected_ciphertext,
                Connector.status == _REFRESHABLE,
            )
            .values(credentials_encrypted=encrypt_data(refreshed.credentials.model_dump_json()))
            .execution_options(synchronize_session=False)
        )
        return _affected(written) == 1

    async def revoke_if_unchanged(self, db: AsyncSession, expected_ciphertext: str) -> bool:
        revoked = await db.execute(
            update(Connector)
            .where(
                Connector.id == self._connector_id,
                Connector.credentials_encrypted == expected_ciphertext,
                Connector.status == _REFRESHABLE,
            )
            .values(status=ConnectorStatus.ERROR)
            .execution_options(synchronize_session=False)
        )
        return _affected(revoked) == 1

    def inactive_error(self) -> Exception:
        if self._status is None or self._status == ConnectorStatus.REVOKED:
            return ConnectorRevokedError(self._connector_type, self._user_id)
        return self.revoked_error(None)

    def revoked_error(self, status_code: int | None) -> Exception:
        return ConnectorTokenExpiredError(
            APIMessages.refresh_token_revoked(),
            connector_type=self._connector_type.value,
            connector_id=str(self._connector_id),
            response_status_code=status_code,
        )

    def failed_error(self) -> Exception:
        return _failed(connector_id=str(self._connector_id))


def _affected(result: object) -> int:
    """The row count of an UPDATE (the async result exposes it as ``rowcount``)."""
    count = getattr(result, "rowcount", 0)
    return count if isinstance(count, int) else 0


# --- a legacy OAuth connector -------------------------------------------------------


def _decode_oauth(connector: Connector, plaintext: str) -> ConnectorCredentials:
    credentials = ConnectorCredentials.model_validate_json(plaintext).model_copy(
        update={"account_binding": None}
    )
    return bind_legacy_oauth_account(connector, credentials)


def _oauth_provider(connector_type: ConnectorType) -> str:
    if connector_type.is_google:
        return "google"
    if connector_type.is_microsoft:
        return "microsoft"
    raise ValueError(f"Unknown OAuth provider for {connector_type.value}")


async def _exchange_oauth(
    connector: Connector, credentials: ConnectorCredentials
) -> Refreshed[ConnectorCredentials]:
    if not credentials.refresh_token:
        raise ValidationError(
            detail=APIMessages.no_refresh_token_available(), connector_id=str(connector.id)
        )
    token = await exchange_refresh_token(
        oauth_endpoint(_oauth_provider(connector.connector_type)),
        refresh_token=credentials.refresh_token,
        scopes=list(connector.scopes or []),
        owner_id=connector.user_id,
    )
    fresh = ConnectorCredentials(
        access_token=token.access_token,
        refresh_token=token.refresh_token,
        token_type="Bearer",
        expires_at=token.expires_at,
        # A rotation keeps this connection's generation; reconnecting starts a new one.
        legacy_account_generation=credentials.legacy_account_generation,
        account_binding=credentials.account_binding,
    )
    return Refreshed(fresh, token.reported_scopes)


def _oauth_needs_refresh(
    credentials: ConnectorCredentials, refresh_before: datetime | None
) -> bool:
    return expires_before(credentials.expires_at, refresh_before)


def legacy_connector_target(connector: Connector) -> ConnectorTokenTarget[ConnectorCredentials]:
    """The target of a legacy (per-connector) OAuth token.

    Args:
        connector: The connector row, holding no shared grant.

    Returns:
        Its refresh target.
    """
    return ConnectorTokenTarget(
        connector,
        kind="connector",
        decode=_decode_oauth,
        exchange=_exchange_oauth,
        needs_refresh=_oauth_needs_refresh,
    )


# --- a Hue bridge in remote mode ------------------------------------------------------


def _decode_hue(connector: Connector, plaintext: str) -> HueBridgeCredentials:
    return HueBridgeCredentials.model_validate_json(plaintext)


async def _exchange_hue(
    connector: Connector, credentials: HueBridgeCredentials
) -> Refreshed[HueBridgeCredentials]:
    if credentials.connection_mode != HueConnectionMode.REMOTE:
        # A local bridge pairs with a key: there is no token, and nothing was revoked.
        raise ValueError("A local Hue bridge holds no OAuth token to refresh")
    if not credentials.refresh_token:
        raise RefreshRefused(RefreshRefusal.REVOKED)
    token = await exchange_refresh_token(
        hue_remote_endpoint(),
        refresh_token=credentials.refresh_token,
        scopes=[],
        owner_id=connector.user_id,
    )
    # Every Hue-specific field (bridge, whitelist username, mode) is kept as stored.
    fresh = credentials.model_copy(
        update={
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "expires_at": token.expires_at,
        }
    )
    return Refreshed(fresh, token.reported_scopes)


def _hue_needs_refresh(credentials: HueBridgeCredentials, refresh_before: datetime | None) -> bool:
    return credentials.connection_mode == HueConnectionMode.REMOTE and expires_before(
        credentials.expires_at, refresh_before
    )


def hue_remote_target(connector: Connector) -> ConnectorTokenTarget[HueBridgeCredentials]:
    """The target of a Hue bridge's remote OAuth token.

    Args:
        connector: The Philips Hue connector row.

    Returns:
        Its refresh target.
    """
    return ConnectorTokenTarget(
        connector,
        kind="hue_remote",
        decode=_decode_hue,
        exchange=_exchange_hue,
        needs_refresh=_hue_needs_refresh,
    )


# --- a shared provider grant (ADR-302) ------------------------------------------------


class GrantTokenTarget:
    """A token stored in a shared grant, its copy carried by every linked connector."""

    def __init__(self, connector: Connector) -> None:
        """Bind the target to the grant of the connector that asked.

        Args:
            connector: A connector linked to a grant (``oauth_grant_id`` set).

        Raises:
            ValueError: The connector holds no shared grant.
        """
        if connector.oauth_grant_id is None:
            raise ValueError("Connector has no shared OAuth grant")
        self._grant_id = connector.oauth_grant_id
        self._user_id = connector.user_id
        self._connector_id = connector.id
        self._connector_type = connector.connector_type
        self._grant: OAuthGrant | None = None
        self._asking_status: ConnectorStatus | None = connector.status

    @property
    def kind(self) -> str:
        return "grant"

    @property
    def flight_key(self) -> str:
        return f"grant:{self._grant_id}"

    @property
    def user_id(self) -> UUID:
        return self._user_id

    async def read(self, db: AsyncSession) -> StoredToken[ConnectorCredentials] | None:
        grant = await db.scalar(
            select(OAuthGrant)
            .where(OAuthGrant.id == self._grant_id, OAuthGrant.user_id == self._user_id)
            .execution_options(populate_existing=True)
        )
        # Still linked to THIS grant: a connector reconnected on its own meanwhile holds
        # a token of its own, and must not be served the grant's.
        self._asking_status = await db.scalar(
            select(Connector.status).where(
                Connector.id == self._connector_id, Connector.oauth_grant_id == self._grant_id
            )
        )
        if grant is None:
            return None
        if not _same_provider(self._connector_type, grant.provider):
            raise ValueError("Connector OAuth grant is missing or belongs to another account")
        self._grant = grant
        return StoredToken(
            grant.credentials_encrypted,
            self._decode(grant),
            self._asking_status == _REFRESHABLE,
        )

    async def current(self, db: AsyncSession) -> StoredToken[ConnectorCredentials] | None:
        """The grant as the CALLER's session sees it — one read, for the door's fast path.

        The asking connector's status is the one the caller just checked on that same
        session; a refresh re-reads both on the door's own sessions.

        Args:
            db: The caller's session.

        Returns:
            The stored token, or None when the grant is gone.

        Raises:
            ValueError: The grant belongs to another provider than the connector.
        """
        grant = await db.scalar(
            select(OAuthGrant).where(
                OAuthGrant.id == self._grant_id, OAuthGrant.user_id == self._user_id
            )
        )
        if grant is None:
            return None
        if not _same_provider(self._connector_type, grant.provider):
            raise ValueError("Connector OAuth grant is missing or belongs to another account")
        self._grant = grant
        return StoredToken(
            grant.credentials_encrypted, self._decode(grant), self._asking_status == _REFRESHABLE
        )

    def _decode(self, grant: OAuthGrant) -> ConnectorCredentials:
        return ConnectorCredentials.model_validate_json(
            decrypt_data(grant.credentials_encrypted)
        ).model_copy(update={"account_binding": str(grant.id)})

    def needs_refresh(
        self, credentials: ConnectorCredentials, refresh_before: datetime | None
    ) -> bool:
        return expires_before(credentials.expires_at, refresh_before)

    async def exchange(self, credentials: ConnectorCredentials) -> Refreshed[ConnectorCredentials]:
        grant = self._grant
        if grant is None:  # the door always reads before it exchanges
            raise RuntimeError("grant token exchanged before it was read")
        if not credentials.refresh_token:
            raise RefreshRefused(RefreshRefusal.REVOKED)
        endpoint = oauth_endpoint(grant.provider)
        if grant.client_id != endpoint.client_id:
            raise ValueError("OAuth client changed; interactive reconnection required")
        token = await exchange_refresh_token(
            endpoint,
            refresh_token=credentials.refresh_token,
            scopes=list(grant.scopes),
            owner_id=self._user_id,
        )
        fresh = ConnectorCredentials(
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            token_type="Bearer",
            expires_at=token.expires_at,
            account_binding=str(grant.id),
        )
        return Refreshed(fresh, token.reported_scopes)

    async def write_if_unchanged(
        self,
        db: AsyncSession,
        expected_ciphertext: str,
        refreshed: Refreshed[ConnectorCredentials],
    ) -> bool:
        grant = await self._locked_grant(db)
        if grant is None or grant.credentials_encrypted != expected_ciphertext:
            return False
        linked = await self._locked_links(db, grant)
        if not any(c.id == self._connector_id and c.status == _REFRESHABLE for c in linked):
            return False
        # The grant stores no binding: it is derived from the grant at every read.
        stored = refreshed.credentials.model_copy(update={"account_binding": None})
        encrypted = encrypt_data(stored.model_dump_json())
        scopes = set(refreshed.reported_scopes) or set(grant.scopes)
        grant.credentials_encrypted = encrypted
        grant.scopes = sorted(scopes)
        for connector in linked:
            connector.credentials_encrypted = encrypted
            if connector.status == _REFRESHABLE and not scopes_cover_connector(
                connector.connector_type, scopes
            ):
                connector.status = ConnectorStatus.ERROR
        return True

    async def revoke_if_unchanged(self, db: AsyncSession, expected_ciphertext: str) -> bool:
        grant = await self._locked_grant(db)
        if grant is None or grant.credentials_encrypted != expected_ciphertext:
            return False
        for connector in await self._locked_links(db, grant):
            if connector.status == _REFRESHABLE:
                connector.status = ConnectorStatus.ERROR
        return True

    async def _locked_grant(self, db: AsyncSession) -> OAuthGrant | None:
        """The grant row, locked first: ADR-302's order is the grant, then its links."""
        locked: OAuthGrant | None = await db.scalar(
            select(OAuthGrant)
            .where(OAuthGrant.id == self._grant_id, OAuthGrant.user_id == self._user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return locked

    async def _locked_links(self, db: AsyncSession, grant: OAuthGrant) -> list[Connector]:
        rows = await db.scalars(
            select(Connector)
            .where(Connector.oauth_grant_id == grant.id)
            .order_by(Connector.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list(rows.all())

    def inactive_error(self) -> Exception:
        if self._asking_status is None or self._asking_status == ConnectorStatus.REVOKED:
            return ConnectorRevokedError(self._connector_type, self._user_id)
        return self.revoked_error(None)

    def revoked_error(self, status_code: int | None) -> Exception:
        return ConnectorTokenExpiredError(
            APIMessages.refresh_token_revoked(),
            connector_type=self._connector_type.value,
            connector_id=str(self._connector_id),
            response_status_code=status_code,
        )

    def failed_error(self) -> Exception:
        return _failed(grant_id=str(self._grant_id))


def _same_provider(connector_type: ConnectorType, provider: str) -> bool:
    return (provider == "google" and connector_type.is_google) or (
        provider == "microsoft" and connector_type.is_microsoft
    )


# --- what a caller holds between its read and the door --------------------------------


@dataclass(frozen=True, slots=True)
class StoredCredentials:
    """A connector's credentials as read, and the one door that freshens them.

    Reading and refreshing are two moments (ADR-304): a caller that OWNS its session
    ends it between them, so no transaction — and no lock of its own — waits on the
    token endpoint. A caller that borrows its session takes both at once
    (``ConnectorService.get_connector_credentials``).

    Attributes:
        target: The holder of the token.
        current: What was read, for the door's fast path; None when the grant is gone.
        user_id: The account the credentials belong to.
        connector_type: The connector they were read for.
    """

    target: RefreshTarget[ConnectorCredentials]
    current: StoredToken[ConnectorCredentials] | None
    user_id: UUID
    connector_type: ConnectorType

    async def fresh(self) -> ConnectorCredentials:
        """Credentials valid past the on-demand margin, refreshed at most once at a time.

        Returns:
            The credentials; a token still valid costs no read, no claim, no exchange.

        Raises:
            Exception: The holder's refusal (gone, revoked, failed), as the door raises it.
        """
        credentials = await ensure_fresh_credentials(self.target, current=self.current)
        ensure_composition_account(
            self.user_id, self.connector_type.value, credentials.account_binding
        )
        return credentials
