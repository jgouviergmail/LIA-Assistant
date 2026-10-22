"""Credential identity, scope and default-container fencing without a token refresh or cached catalogue."""

from hashlib import sha256
from uuid import UUID

from sqlalchemy import select

from src.core.content_source import content_source_binding
from src.core.exceptions import AuthorizationError
from src.core.security.utils import decrypt_data
from src.domains.connectors.legacy_oauth_binding import bind_legacy_oauth_account
from src.domains.connectors.models import (
    Connector,
    ConnectorGlobalConfig,
    ConnectorStatus,
    ConnectorType,
    OAuthGrant,
)
from src.domains.connectors.provider_authority import resolve_active_connector_fresh
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from src.domains.connectors.service import ConnectorService
from src.domains.shared.discussion_catalogue import SOURCE_REGISTRY
from src.domains.shared.discussion_sources import SourceKey, semantic_version
from src.domains.users.active_reader import require_active_owner_read
from src.infrastructure.database.session import get_db_context


def _binding(row: Connector) -> str:
    if row.oauth_grant_id is not None:
        return str(row.oauth_grant_id)
    if row.connector_type.is_apple:
        return AppleCredentials.model_validate_json(
            decrypt_data(row.credentials_encrypted)
        ).apple_id
    credentials = ConnectorCredentials.model_validate_json(decrypt_data(row.credentials_encrypted))
    return bind_legacy_oauth_account(row, credentials).account_binding or ""


async def read_connector_scope(owner: UUID, kind: ConnectorType) -> str:
    """Return the scope a connector reads under: kind, account identity and permissions.

    The connector must be active and globally enabled, its grant must still belong
    to the account, and its account binding must be known; any change of account,
    scopes or preferences yields another scope.

    Args:
        owner: The account.
        kind: The connector type.

    Returns:
        ``<kind>:<account hash>:<permission hash>``.

    Raises:
        AuthorizationError: The connector is inactive, disabled or unbound
            (``FORBIDDEN`` or ``ACCOUNT_IDENTITY_UNAVAILABLE``).
    """
    async with get_db_context() as db:
        await require_active_owner_read(db, owner)
        enabled = await db.scalar(
            select(ConnectorGlobalConfig.is_enabled).where(
                ConnectorGlobalConfig.connector_type == kind
            )
        )
        row = await db.scalar(
            select(Connector).where(
                Connector.user_id == owner,
                Connector.connector_type == kind,
                Connector.status == ConnectorStatus.ACTIVE,
            )
        )
        if enabled is False or row is None:
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
        if (
            row.oauth_grant_id is not None
            and await db.scalar(
                select(OAuthGrant.id).where(
                    OAuthGrant.id == row.oauth_grant_id, OAuthGrant.user_id == owner
                )
            )
            is None
        ):
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
        binding = _binding(row)
        if not binding:
            raise AuthorizationError(detail={"error_code": "ACCOUNT_IDENTITY_UNAVAILABLE"})
        identity = sha256(binding.encode()).hexdigest()
        policy = semantic_version((*sorted(row.scopes), row.preferences_encrypted or ""))[:16]
        return f"{kind.value}:{identity}:{policy}"


async def is_selected_discussion_connector(
    owner: UUID, source: SourceKey, kind: ConnectorType
) -> bool:
    """Whether this connector type is the one currently serving the source's category.

    Args:
        owner: The account.
        source: A connector-backed source.
        kind: The connector type to check.

    Returns:
        True when the category's active connector, read fresh, is ``kind``.

    Raises:
        ValueError: No connector category serves ``source``.
    """
    category = SOURCE_REGISTRY[source].connector_category
    if category is None:
        raise ValueError("discussion source is not served by a connector")
    async with get_db_context() as db:
        return await resolve_active_connector_fresh(owner, category, ConnectorService(db)) == kind


async def require_reader_authority(
    owner: UUID, kind: ConnectorType, client: object, *, container: str = ""
) -> str:
    """Check the client reads the connector's own account; return the read's scope.

    Args:
        owner: The account.
        kind: The connector type.
        client: The opened provider client.
        container: The container read (a calendar or task list), if any.

    Returns:
        The connector scope, suffixed by the container's hash.

    Raises:
        AuthorizationError: The client's account is not the connector's
            (``SOURCE_ACCOUNT_CHANGED``), or the connector is no longer usable.
    """
    scope = await read_connector_scope(owner, kind)
    binding = content_source_binding(client)
    if not binding or scope.split(":")[1] != binding:
        raise AuthorizationError(detail={"error_code": "SOURCE_ACCOUNT_CHANGED"})
    return f"{scope}:{semantic_version((container,))[:16]}"
