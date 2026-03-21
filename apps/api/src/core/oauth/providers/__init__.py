"""OAuth providers module."""

from .base import OAuthProvider
from .google import GoogleOAuthProvider
from .hue import HueOAuthProvider
from .microsoft import MicrosoftOAuthProvider

__all__ = [
    "GoogleOAuthProvider",
    "HueOAuthProvider",
    "MicrosoftOAuthProvider",
    "OAuthProvider",
]
