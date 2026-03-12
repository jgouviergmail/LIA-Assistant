"""Microsoft OAuth 2.0 provider configuration (Entra ID / Azure AD)."""

from dataclasses import dataclass

from src.core.config import Settings
from src.core.constants import (
    API_PREFIX_DEFAULT,
    MICROSOFT_CALENDAR_SCOPES,
    MICROSOFT_CONTACTS_SCOPES,
    MICROSOFT_OAUTH_AUTHORIZATION_ENDPOINT,
    MICROSOFT_OAUTH_TOKEN_ENDPOINT,
    MICROSOFT_OUTLOOK_SCOPES,
    MICROSOFT_TASKS_SCOPES,
)


@dataclass
class MicrosoftOAuthProvider:
    """
    Microsoft OAuth 2.0 provider configuration (Entra ID / Azure AD).

    Multi-tenant transparent: tenant="common" accepts both personal accounts
    (outlook.com, hotmail.com, live.com) and enterprise accounts (Azure AD).
    Microsoft detects the account type from the email entered by the user.

    Best Practices:
    - Always use PKCE (S256) — supported by OAuthFlowHandler
    - Token refresh REQUIRES scope parameter (unlike Google)
    - No revocation endpoint available
    """

    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str]
    authorization_endpoint: str
    token_endpoint: str
    revocation_endpoint: str | None = None  # Microsoft has NO revocation endpoint
    provider_name: str = "microsoft"

    @classmethod
    def for_outlook(cls, settings: Settings) -> "MicrosoftOAuthProvider":
        """Create provider config for Microsoft Outlook (email) connector."""
        tenant = settings.microsoft_tenant_id
        return cls(
            client_id=settings.microsoft_client_id,
            client_secret=settings.microsoft_client_secret,
            redirect_uri=(
                f"{settings.api_url}{API_PREFIX_DEFAULT}/connectors/microsoft-outlook/callback"
            ),
            scopes=MICROSOFT_OUTLOOK_SCOPES,
            authorization_endpoint=MICROSOFT_OAUTH_AUTHORIZATION_ENDPOINT.format(tenant=tenant),
            token_endpoint=MICROSOFT_OAUTH_TOKEN_ENDPOINT.format(tenant=tenant),
        )

    @classmethod
    def for_calendar(cls, settings: Settings) -> "MicrosoftOAuthProvider":
        """Create provider config for Microsoft Calendar connector."""
        tenant = settings.microsoft_tenant_id
        return cls(
            client_id=settings.microsoft_client_id,
            client_secret=settings.microsoft_client_secret,
            redirect_uri=(
                f"{settings.api_url}{API_PREFIX_DEFAULT}/connectors/microsoft-calendar/callback"
            ),
            scopes=MICROSOFT_CALENDAR_SCOPES,
            authorization_endpoint=MICROSOFT_OAUTH_AUTHORIZATION_ENDPOINT.format(tenant=tenant),
            token_endpoint=MICROSOFT_OAUTH_TOKEN_ENDPOINT.format(tenant=tenant),
        )

    @classmethod
    def for_contacts(cls, settings: Settings) -> "MicrosoftOAuthProvider":
        """Create provider config for Microsoft Contacts connector."""
        tenant = settings.microsoft_tenant_id
        return cls(
            client_id=settings.microsoft_client_id,
            client_secret=settings.microsoft_client_secret,
            redirect_uri=(
                f"{settings.api_url}{API_PREFIX_DEFAULT}/connectors/microsoft-contacts/callback"
            ),
            scopes=MICROSOFT_CONTACTS_SCOPES,
            authorization_endpoint=MICROSOFT_OAUTH_AUTHORIZATION_ENDPOINT.format(tenant=tenant),
            token_endpoint=MICROSOFT_OAUTH_TOKEN_ENDPOINT.format(tenant=tenant),
        )

    @classmethod
    def for_tasks(cls, settings: Settings) -> "MicrosoftOAuthProvider":
        """Create provider config for Microsoft To Do (tasks) connector."""
        tenant = settings.microsoft_tenant_id
        return cls(
            client_id=settings.microsoft_client_id,
            client_secret=settings.microsoft_client_secret,
            redirect_uri=(
                f"{settings.api_url}{API_PREFIX_DEFAULT}/connectors/microsoft-tasks/callback"
            ),
            scopes=MICROSOFT_TASKS_SCOPES,
            authorization_endpoint=MICROSOFT_OAUTH_AUTHORIZATION_ENDPOINT.format(tenant=tenant),
            token_endpoint=MICROSOFT_OAUTH_TOKEN_ENDPOINT.format(tenant=tenant),
        )
