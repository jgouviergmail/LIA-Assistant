"""
OAuth 2.1 with PKCE (RFC 7636) module.

This module provides generic OAuth flow handling with:
- PKCE (Proof Key for Code Exchange) mandatory
- State token CSRF protection
- Secure token storage
- Provider abstraction
"""

from .exceptions import (
    OAuthFlowError,
    OAuthProviderError,
    OAuthStateValidationError,
    OAuthTokenExchangeError,
)
from .flow_handler import OAuthFlowHandler, OAuthTokenResponse
from .providers.base import OAuthProvider
from .providers.google import GoogleOAuthProvider
from .providers.microsoft import MicrosoftOAuthProvider

__all__ = [
    "GoogleOAuthProvider",
    "MicrosoftOAuthProvider",
    "OAuthFlowError",
    "OAuthFlowHandler",
    "OAuthProvider",
    "OAuthProviderError",
    "OAuthStateValidationError",
    "OAuthTokenExchangeError",
    "OAuthTokenResponse",
]
