"""Google OAuth 2.0 provider configuration."""

from dataclasses import dataclass

from src.core.config import Settings
from src.core.constants import (
    GOOGLE_CALENDAR_SCOPES,
    GOOGLE_CONTACTS_SCOPES,
    GOOGLE_DRIVE_SCOPES,
    GOOGLE_GMAIL_SCOPES,
    GOOGLE_OAUTH_AUTHORIZATION_ENDPOINT,
    GOOGLE_OAUTH_REVOCATION_ENDPOINT,
    GOOGLE_OAUTH_TOKEN_ENDPOINT,
    GOOGLE_TASKS_SCOPES,
)


@dataclass
class GoogleOAuthProvider:  # pylint: disable=too-many-instance-attributes
    """
    Google OAuth 2.0 provider configuration.

    Best Practices:
    - Always use PKCE (S256)
    - Request offline_access for refresh tokens
    - Use prompt=consent to force re-consent (gets refresh token)
    """

    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str]
    authorization_endpoint: str = GOOGLE_OAUTH_AUTHORIZATION_ENDPOINT
    token_endpoint: str = GOOGLE_OAUTH_TOKEN_ENDPOINT
    revocation_endpoint: str = GOOGLE_OAUTH_REVOCATION_ENDPOINT
    provider_name: str = "google"

    @classmethod
    def for_authentication(cls, settings: Settings) -> "GoogleOAuthProvider":
        """
        Create provider config for user authentication (OpenID Connect).

        Scopes: openid, email, profile
        """
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=settings.google_redirect_uri,
            scopes=["openid", "email", "profile"],
        )

    @classmethod
    def for_gmail(cls, settings: Settings) -> "GoogleOAuthProvider":
        """
        Create provider config for Gmail connector.

        Scopes: gmail.readonly, gmail.send, gmail.modify (read/write, labels, trash)

        Note: Redirect URI constructed dynamically from api_url to avoid
        additional configuration requirement.
        """
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=f"{settings.api_url}{settings.api_prefix}/connectors/gmail/callback",
            scopes=GOOGLE_GMAIL_SCOPES,
        )

    @classmethod
    def for_contacts(cls, settings: Settings) -> "GoogleOAuthProvider":
        """
        Create provider config for Google Contacts connector.

        Scopes: contacts (full), contacts.readonly, contacts.other.readonly

        Note: Redirect URI constructed dynamically from api_url to avoid
        additional configuration requirement.
        """
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=f"{settings.api_url}{settings.api_prefix}/connectors/google-contacts/callback",
            scopes=GOOGLE_CONTACTS_SCOPES,
        )

    @classmethod
    def for_calendar(cls, settings: Settings) -> "GoogleOAuthProvider":
        """
        Create provider config for Google Calendar connector.

        Scopes: calendar.readonly, calendar.events (read + write events), calendar (full)

        Note: Redirect URI constructed dynamically from api_url to avoid
        additional configuration requirement.
        """
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=f"{settings.api_url}{settings.api_prefix}/connectors/google-calendar/callback",
            scopes=GOOGLE_CALENDAR_SCOPES,
        )

    @classmethod
    def for_drive(cls, settings: Settings) -> "GoogleOAuthProvider":
        """
        Create provider config for Google Drive connector.

        Scopes: drive.readonly, drive.file (read + write files created by this app), drive (full)

        Note: Redirect URI constructed dynamically from api_url to avoid
        additional configuration requirement.
        """
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=f"{settings.api_url}{settings.api_prefix}/connectors/google-drive/callback",
            scopes=GOOGLE_DRIVE_SCOPES,
        )

    @classmethod
    def for_tasks(cls, settings: Settings) -> "GoogleOAuthProvider":
        """
        Create provider config for Google Tasks connector.

        Scopes: tasks.readonly, tasks (read + write tasks)

        Note: Redirect URI constructed dynamically from api_url to avoid
        additional configuration requirement.
        """
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            redirect_uri=f"{settings.api_url}{settings.api_prefix}/connectors/google-tasks/callback",
            scopes=GOOGLE_TASKS_SCOPES,
        )
