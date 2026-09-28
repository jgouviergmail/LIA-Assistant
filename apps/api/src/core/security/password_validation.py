"""
Password validation utilities.

Centralized password policy enforcement for non-OAuth accounts: a minimum and a
maximum length, and minimum counts of uppercase letters, digits and special
characters — the ``PASSWORD_*`` constants of ``core/constants.py`` are the
policy. A violation is reported in the declared language (the request's), one
sentence per rule broken.
"""

from dataclasses import dataclass

from src.core.constants import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_DIGITS,
    PASSWORD_MIN_LENGTH,
    PASSWORD_MIN_SPECIAL,
    PASSWORD_MIN_UPPERCASE,
    PASSWORD_SPECIAL_CHARS,
)
from src.core.i18n import _


@dataclass
class PasswordValidationResult:
    """Result of password validation."""

    is_valid: bool
    errors: list[str]

    @property
    def error_message(self) -> str:
        """Get combined error message."""
        return " ".join(self.errors)


def validate_password(password: str) -> PasswordValidationResult:
    """
    Validate password against policy requirements.

    Args:
        password: The password to validate

    Returns:
        PasswordValidationResult with validation status and any errors, each
        written in the declared language
    """
    errors: list[str] = []

    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(
            _("Password must be at least {count} characters long.").format(
                count=PASSWORD_MIN_LENGTH
            )
        )

    if len(password) > PASSWORD_MAX_LENGTH:
        errors.append(
            _("Password cannot be longer than {count} characters.").format(
                count=PASSWORD_MAX_LENGTH
            )
        )

    uppercase_count = sum(1 for c in password if c.isupper())
    if uppercase_count < PASSWORD_MIN_UPPERCASE:
        errors.append(
            _("Password must contain at least {count} uppercase letters.").format(
                count=PASSWORD_MIN_UPPERCASE
            )
        )

    digit_count = sum(1 for c in password if c.isdigit())
    if digit_count < PASSWORD_MIN_DIGITS:
        errors.append(
            _("Password must contain at least {count} digits.").format(count=PASSWORD_MIN_DIGITS)
        )

    special_count = sum(1 for c in password if c in PASSWORD_SPECIAL_CHARS)
    if special_count < PASSWORD_MIN_SPECIAL:
        errors.append(
            _("Password must contain at least {count} special characters ({examples}...).").format(
                count=PASSWORD_MIN_SPECIAL, examples=PASSWORD_SPECIAL_CHARS[:10]
            )
        )

    return PasswordValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
    )


def validate_password_strict(password: str) -> str:
    """
    Validate password and raise ValueError if invalid.

    This is designed to be used as a Pydantic field_validator.

    Args:
        password: The password to validate

    Returns:
        The password if valid

    Raises:
        ValueError: If password does not meet requirements
    """
    result = validate_password(password)
    if not result.is_valid:
        raise ValueError(result.error_message)
    return password
