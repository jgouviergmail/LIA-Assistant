"""
Service for managing encrypted connector preferences.

Provides:
    - Validation against Pydantic schemas
    - Sanitization to prevent prompt injection
    - Fernet encryption (same as credentials_encrypted)
    - Decryption for runtime access

Security:
    - All string values are sanitized before encryption
    - Dangerous characters removed: newlines, quotes, backslashes, braces
    - Maximum length enforced (100 chars)
    - Encrypted using Fernet symmetric encryption
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import ValidationError

from src.core.security import decrypt_data, encrypt_data
from src.domains.connectors.preferences.registry import get_preference_schema

if TYPE_CHECKING:
    from src.domains.connectors.preferences.schemas import BaseConnectorPreferences

logger = structlog.get_logger(__name__)

# Pattern for characters that could be used for prompt injection
# Removes: newlines, tabs, quotes, backticks, backslashes, braces
DANGEROUS_CHARS_PATTERN = re.compile(r'[\n\r\t"\'`\\{}]')

# Maximum length for preference string values
MAX_PREFERENCE_LENGTH = 100


class ConnectorPreferencesService:
    """
    Service for managing encrypted connector preferences.

    All operations are static - no instance state needed.
    """

    @staticmethod
    def validate_and_encrypt(
        connector_type: str,
        preferences_data: dict[str, Any],
    ) -> tuple[bool, str | None, list[str]]:
        """
        Validate preferences against schema, sanitize, and encrypt.

        Args:
            connector_type: Connector type string
            preferences_data: Raw preferences data from API

        Returns:
            Tuple of (success, encrypted_data, errors)
            - success: True if validation and encryption succeeded
            - encrypted_data: Encrypted JSON string or None on failure
            - errors: List of validation error messages
        """
        schema_class = get_preference_schema(connector_type)
        if not schema_class:
            return False, None, [f"No preferences schema for connector type: {connector_type}"]

        try:
            # Validate against schema
            validated = schema_class.model_validate(preferences_data)

            # Sanitize to prevent prompt injection
            sanitized = ConnectorPreferencesService._sanitize(validated)

            # Encrypt like credentials
            encrypted = encrypt_data(sanitized.model_dump_json())

            logger.debug(
                "connector_preferences_encrypted",
                connector_type=connector_type,
            )

            return True, encrypted, []

        except ValidationError as e:
            errors = []
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"]) if err["loc"] else "root"
                errors.append(f"{loc}: {err['msg']}")
            return False, None, errors

        except Exception as e:
            logger.error(
                "connector_preferences_encrypt_failed",
                connector_type=connector_type,
                error=str(e),
            )
            return False, None, [f"Encryption failed: {e!s}"]

    @staticmethod
    def decrypt_and_get(
        connector_type: str,
        encrypted_preferences: str | None,
    ) -> BaseConnectorPreferences | None:
        """
        Decrypt and return preferences object.

        Args:
            connector_type: Connector type string
            encrypted_preferences: Encrypted preferences JSON or None

        Returns:
            Typed preferences object or None if decryption fails
        """
        if not encrypted_preferences:
            return None

        schema_class = get_preference_schema(connector_type)
        if not schema_class:
            return None

        try:
            decrypted_json = decrypt_data(encrypted_preferences)
            return schema_class.model_validate_json(decrypted_json)

        except Exception as e:
            logger.warning(
                "connector_preferences_decrypt_failed",
                connector_type=connector_type,
                error=str(e),
            )
            return None

    @staticmethod
    def get_preference_value(
        connector_type: str,
        encrypted_preferences: str | None,
        preference_name: str,
        default: str | None = None,
    ) -> str | None:
        """
        Get a single preference value (decrypted).

        Convenience method for getting a specific preference field.

        Args:
            connector_type: Connector type string
            encrypted_preferences: Encrypted preferences JSON or None
            preference_name: Name of the preference field
            default: Default value if preference not set

        Returns:
            Preference value or default
        """
        prefs = ConnectorPreferencesService.decrypt_and_get(connector_type, encrypted_preferences)

        if prefs and hasattr(prefs, preference_name):
            value = getattr(prefs, preference_name)
            return value if value is not None else default

        return default

    @staticmethod
    def _sanitize(prefs: BaseConnectorPreferences) -> BaseConnectorPreferences:
        """
        Sanitize preference values to prevent prompt injection.

        Security measures:
            - Remove dangerous characters that could escape prompt context
            - Enforce maximum length
            - Strip whitespace

        Args:
            prefs: Validated preferences object

        Returns:
            Sanitized preferences object
        """
        sanitized_data: dict[str, Any] = {}

        for field_name, value in prefs.model_dump().items():
            if isinstance(value, str):
                # Remove dangerous characters for prompt injection
                clean = DANGEROUS_CHARS_PATTERN.sub("", value)

                # Enforce max length
                clean = clean[:MAX_PREFERENCE_LENGTH]

                # Strip whitespace
                clean = clean.strip()

                sanitized_data[field_name] = clean
            else:
                sanitized_data[field_name] = value

        return type(prefs).model_validate(sanitized_data)
