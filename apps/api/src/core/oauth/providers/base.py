"""Base OAuth provider protocol."""

from typing import Protocol


class OAuthProvider(Protocol):
    """
    Protocol defining an OAuth 2.1 provider with PKCE.

    Best Practices:
    - All providers must support PKCE (RFC 7636)
    - Scopes must be explicitly defined
    - Endpoints must use HTTPS
    """

    @property
    def client_id(self) -> str:
        """OAuth client ID."""
        ...

    @property
    def client_secret(self) -> str:
        """OAuth client secret."""
        ...

    @property
    def redirect_uri(self) -> str:
        """OAuth redirect URI (must be registered with provider)."""
        ...

    @property
    def scopes(self) -> list[str]:
        """List of OAuth scopes to request."""
        ...

    @property
    def authorization_endpoint(self) -> str:
        """Authorization endpoint URL."""
        ...

    @property
    def token_endpoint(self) -> str:
        """Token exchange endpoint URL."""
        ...

    @property
    def revocation_endpoint(self) -> str | None:
        """Token revocation endpoint URL (optional)."""
        ...

    @property
    def provider_name(self) -> str:
        """Human-readable provider name."""
        ...
