"""Canonical credential names shared by redaction and external-data presentation."""

from src.core.field_names import FIELD_SESSION_ID

CREDENTIAL_FIELD_NAMES = frozenset(
    {
        "password",
        "hashed_password",
        "secret",
        "api_key",
        "apikey",
        "token",
        "access_token",
        "refresh_token",
        "auth_token",
        "id_token",
        "bearer",
        "authorization",
        "cookie",
        FIELD_SESSION_ID,
        "csrf",
        "private_key",
        "code_verifier",
        "code_challenge",
        "client_secret",
        "authorization_code",
        "auth_code",
        "oauth_state",
    }
)

_NORMALIZED_CREDENTIAL_NAMES = frozenset(name.replace("_", "") for name in CREDENTIAL_FIELD_NAMES)


def is_credential_field(name: str) -> bool:
    """Recognize the same names in JSON's snake, camel and kebab spellings."""
    return name.casefold().replace("_", "").replace("-", "") in _NORMALIZED_CREDENTIAL_NAMES
