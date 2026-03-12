"""OAuth providers module."""

from .base import OAuthProvider
from .google import GoogleOAuthProvider
from .microsoft import MicrosoftOAuthProvider

__all__ = ["GoogleOAuthProvider", "MicrosoftOAuthProvider", "OAuthProvider"]
