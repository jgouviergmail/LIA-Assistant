"""
Test data factories for creating test objects.
Provides factory functions for User, Connector, and other models.
"""

import json
from datetime import UTC, datetime
from uuid import uuid4

from src.core.security import encrypt_data, get_password_hash
from src.domains.auth.models import User
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType


class UserFactory:
    """Factory for creating User test instances."""

    @staticmethod
    def create(
        email: str | None = None,
        password: str | None = None,
        full_name: str | None = None,
        is_active: bool = True,
        is_verified: bool = True,
        is_superuser: bool = False,
        oauth_provider: str | None = None,
        oauth_provider_id: str | None = None,
        picture_url: str | None = None,
        memory_enabled: bool = True,
        voice_enabled: bool = False,
    ) -> User:
        """
        Create a User instance with default or custom values.

        Args:
            email: User email (defaults to random)
            password: User password (defaults to "TestPass123!!")
            full_name: User full name (defaults to "Test User")
            is_active: Whether user is active
            is_verified: Whether user email is verified
            is_superuser: Whether user is superuser
            oauth_provider: OAuth provider name
            oauth_provider_id: OAuth provider user ID
            picture_url: Profile picture URL
            memory_enabled: Whether memory feature is enabled
            voice_enabled: Whether voice feature is enabled

        Returns:
            User instance (not persisted to database)
        """
        if email is None:
            email = f"test-{uuid4()}@example.com"

        if password is None:
            # Password must meet policy: 10+ chars, 2 uppercase, 2 digits, 2 special
            password = "TestPass123!!"

        if full_name is None:
            full_name = "Test User"

        hashed_password = get_password_hash(password) if password else None

        return User(
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            is_active=is_active,
            is_verified=is_verified,
            is_superuser=is_superuser,
            oauth_provider=oauth_provider,
            oauth_provider_id=oauth_provider_id,
            picture_url=picture_url,
            timezone="Europe/Paris",  # Default timezone for test users
            language="fr",  # Default language for test users
            memory_enabled=memory_enabled,
            voice_enabled=voice_enabled,
            theme="system",  # Default theme for test users
            color_theme="default",  # Default color theme for test users
        )

    @staticmethod
    def create_superuser(
        email: str | None = None,
        password: str | None = None,
        full_name: str | None = None,
    ) -> User:
        """
        Create a superuser instance.

        Args:
            email: User email
            password: User password
            full_name: User full name

        Returns:
            User instance with superuser privileges
        """
        return UserFactory.create(
            email=email or f"admin-{uuid4()}@example.com",
            # Password must meet policy: 10+ chars, 2 uppercase, 2 digits, 2 special
            password=password or "AdminPass123!!",
            full_name=full_name or "Admin User",
            is_active=True,
            is_verified=True,
            is_superuser=True,
        )

    @staticmethod
    def create_oauth_user(
        provider: str = "google",
        email: str | None = None,
        full_name: str | None = None,
    ) -> User:
        """
        Create a user registered via OAuth.

        Args:
            provider: OAuth provider name
            email: User email
            full_name: User full name

        Returns:
            User instance with OAuth data
        """
        return UserFactory.create(
            email=email or f"oauth-{uuid4()}@example.com",
            password=None,  # No password for OAuth users
            full_name=full_name or "OAuth User",
            is_active=True,
            is_verified=True,
            oauth_provider=provider,
            oauth_provider_id=f"{provider}-{uuid4()}",
            picture_url=f"https://example.com/avatar/{uuid4()}.jpg",
        )


class ConnectorFactory:
    """Factory for creating Connector test instances."""

    @staticmethod
    def create(
        user_id: str,
        connector_type: ConnectorType = ConnectorType.GOOGLE_GMAIL,
        status: ConnectorStatus = ConnectorStatus.ACTIVE,
        scopes: list[str] | None = None,
        access_token: str = "test-access-token",
        refresh_token: str = "test-refresh-token",
        expires_at: int | None = None,
        metadata: dict | None = None,
    ) -> Connector:
        """
        Create a Connector instance with default or custom values.

        Args:
            user_id: User ID (UUID as string)
            connector_type: Type of connector
            status: Connector status
            scopes: OAuth scopes granted
            access_token: OAuth access token
            refresh_token: OAuth refresh token
            expires_at: Token expiration timestamp
            metadata: Additional metadata

        Returns:
            Connector instance (not persisted to database)
        """
        if scopes is None:
            scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

        if expires_at is None:
            expires_at = int(datetime.now(UTC).timestamp()) + 3600

        if metadata is None:
            metadata = {}

        # Create credentials dict and encrypt
        credentials = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
        }
        credentials_encrypted = encrypt_data(json.dumps(credentials))

        return Connector(
            user_id=user_id,
            connector_type=connector_type,
            status=status,
            scopes=scopes,
            credentials_encrypted=credentials_encrypted,
            connector_metadata=metadata,
        )

    @staticmethod
    def create_gmail_connector(
        user_id: str,
        email: str = "test@example.com",
        status: ConnectorStatus = ConnectorStatus.ACTIVE,
    ) -> Connector:
        """
        Create a Gmail connector instance.

        Args:
            user_id: User ID
            email: Gmail email address
            status: Connector status

        Returns:
            Connector instance for Gmail
        """
        return ConnectorFactory.create(
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_GMAIL,
            status=status,
            scopes=[
                "https://www.googleapis.com/auth/gmail.readonly",
                "https://www.googleapis.com/auth/gmail.send",
            ],
            metadata={"email": email},
        )

    @staticmethod
    def create_drive_connector(
        user_id: str,
        status: ConnectorStatus = ConnectorStatus.ACTIVE,
    ) -> Connector:
        """
        Create a Google Drive connector instance.

        Args:
            user_id: User ID
            status: Connector status

        Returns:
            Connector instance for Google Drive
        """
        return ConnectorFactory.create(
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_DRIVE,
            status=status,
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
            ],
        )

    @staticmethod
    def create_calendar_connector(
        user_id: str,
        status: ConnectorStatus = ConnectorStatus.ACTIVE,
    ) -> Connector:
        """
        Create a Google Calendar connector instance.

        Args:
            user_id: User ID
            status: Connector status

        Returns:
            Connector instance for Google Calendar
        """
        return ConnectorFactory.create(
            user_id=user_id,
            connector_type=ConnectorType.GOOGLE_CALENDAR,
            status=status,
            scopes=[
                "https://www.googleapis.com/auth/calendar.readonly",
            ],
        )

    @staticmethod
    def create_revoked_connector(
        user_id: str,
        connector_type: ConnectorType = ConnectorType.GOOGLE_GMAIL,
    ) -> Connector:
        """
        Create a revoked connector instance.

        Args:
            user_id: User ID
            connector_type: Type of connector

        Returns:
            Connector instance with revoked status
        """
        return ConnectorFactory.create(
            user_id=user_id,
            connector_type=connector_type,
            status=ConnectorStatus.REVOKED,
        )


# Convenience function for creating test data
def create_test_user(**kwargs) -> User:
    """
    Create a test user with default values.
    Wrapper around UserFactory.create for convenience.
    """
    return UserFactory.create(**kwargs)


def create_test_connector(user_id: str, **kwargs) -> Connector:
    """
    Create a test connector with default values.
    Wrapper around ConnectorFactory.create for convenience.
    """
    return ConnectorFactory.create(user_id=user_id, **kwargs)
