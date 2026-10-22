"""Bind legacy OAuth connectors to their account without exposing credential material.

A connector created before OAuth grants carries no grant id, so its account identity
is minted here: the initial refresh credential identifies a connection generation,
the opaque generation stays inside the encrypted credential document across token
rotation, and a fresh OAuth callback creates a new random generation. The public
UUID is scoped to the owning user, connector row and provider.

Mailboxes were bound first (card actions need it); every legacy OAuth connector now
is: a calendar or an address book left unbound had no account identity at all, and
every discussion read of it was refused (measured on production 2026-10-21). The
derivation strings below are frozen identifiers — changing one would re-key every
binding a mailbox card already carries.
"""

import hmac
import json
from uuid import UUID, uuid4

from src.core.config import settings
from src.domains.connectors.models import Connector, ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials


def start_legacy_oauth_connection(
    provider: ConnectorType, credentials: ConnectorCredentials
) -> ConnectorCredentials:
    """A successful new consent starts a generation even if the provider reuses its token."""
    if not provider.is_oauth:
        return credentials
    return credentials.model_copy(
        update={"legacy_account_generation": str(uuid4()), "account_binding": None}
    )


def _identity(parts: tuple[str, ...]) -> str:
    encoded = json.dumps(parts, separators=(",", ":")).encode()
    digest = hmac.digest(settings.secret_key.encode(), encoded, "sha256")
    return str(UUID(bytes=digest[:16], version=5))


def bind_legacy_oauth_account(
    connector: Connector, credentials: ConnectorCredentials
) -> ConnectorCredentials:
    """Mint from authenticated stored credentials, never from HTML or a supplied UUID.

    Args:
        connector: The connector row; one holding an OAuth grant is bound by it.
        credentials: Its decrypted credentials.

    Returns:
        The credentials with the account binding, and its generation, set — or
        unchanged for a granted or non-OAuth connector; without a refresh token
        there is no binding.
    """
    if connector.oauth_grant_id or not connector.connector_type.is_oauth:
        return credentials
    if not credentials.refresh_token:
        return credentials.model_copy(update={"account_binding": None})
    generation = credentials.legacy_account_generation or _identity(
        ("lia:legacy-email-generation:v1", credentials.refresh_token)
    )
    binding = _identity(
        (
            "lia:legacy-email-account:v1",
            str(connector.user_id),
            str(connector.id),
            connector.connector_type.value,
            generation,
        )
    )
    return credentials.model_copy(
        update={"account_binding": binding, "legacy_account_generation": generation}
    )
