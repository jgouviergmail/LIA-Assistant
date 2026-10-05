"""Bind legacy OAuth mailboxes without putting credential material in card metadata.

The initial refresh credential identifies a connection generation. The opaque
generation stays inside the existing encrypted credential document across token
rotation; a fresh OAuth callback creates a new random generation. The public UUID
is separately scoped to the owning user, connector row and provider.
"""

import hmac
import json
from uuid import UUID, uuid4

from src.core.config import settings
from src.domains.connectors.models import Connector, ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

_LEGACY_EMAIL_TYPES = frozenset(
    (ConnectorType.GOOGLE_GMAIL, ConnectorType.GMAIL, ConnectorType.MICROSOFT_OUTLOOK)
)


def start_legacy_email_connection(
    provider: ConnectorType, credentials: ConnectorCredentials
) -> ConnectorCredentials:
    """A successful new consent starts a generation even if the provider reuses its token."""
    if provider not in _LEGACY_EMAIL_TYPES:
        return credentials
    return credentials.model_copy(
        update={"legacy_account_generation": str(uuid4()), "account_binding": None}
    )


def _identity(parts: tuple[str, ...]) -> str:
    encoded = json.dumps(parts, separators=(",", ":")).encode()
    digest = hmac.digest(settings.secret_key.encode(), encoded, "sha256")
    return str(UUID(bytes=digest[:16], version=5))


def bind_legacy_email_account(
    connector: Connector, credentials: ConnectorCredentials
) -> ConnectorCredentials:
    """Mint from authenticated stored credentials, never from HTML or a supplied UUID."""
    if connector.oauth_grant_id or connector.connector_type not in _LEGACY_EMAIL_TYPES:
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
