"""Philips Hue Remote API OAuth 2.0 provider configuration."""

from dataclasses import dataclass

from src.core.config import Settings
from src.core.constants import (
    HUE_REMOTE_AUTHORIZATION_ENDPOINT,
    HUE_REMOTE_TOKEN_ENDPOINT,
)


@dataclass
class HueOAuthProvider:
    """
    Hue Remote API OAuth2 provider configuration.

    Implements OAuthProvider Protocol for compatibility with OAuthFlowHandler.
    Used for remote Hue Bridge access via api.meethue.com cloud relay.

    Note:
        Hue OAuth does not use standard scopes. The app_id field is
        Hue-specific and required for the authorization URL.
    """

    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str]
    authorization_endpoint: str = HUE_REMOTE_AUTHORIZATION_ENDPOINT
    token_endpoint: str = HUE_REMOTE_TOKEN_ENDPOINT
    revocation_endpoint: str | None = None
    provider_name: str = "hue"
    app_id: str = ""

    @classmethod
    def for_remote_control(cls, settings: Settings) -> "HueOAuthProvider":
        """
        Create provider config for Hue Remote API access.

        Note: Redirect URI constructed dynamically from api_url to avoid
        additional configuration requirement.
        """
        return cls(
            client_id=settings.hue_remote_client_id,
            client_secret=settings.hue_remote_client_secret,
            app_id=settings.hue_remote_app_id,
            redirect_uri=(
                f"{settings.api_url}{settings.api_prefix}" "/connectors/philips-hue/callback"
            ),
            scopes=[],
        )
