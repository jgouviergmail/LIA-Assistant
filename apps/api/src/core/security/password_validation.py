"""
Password validation utilities.

Centralized password policy enforcement for non-OAuth accounts.
This module provides validation functions and error messages for password requirements.

Password Policy:
- Minimum 10 characters
- At least 2 uppercase letters
- At least 2 special characters
- At least 2 digits
"""

import re
from dataclasses import dataclass

from src.core.constants import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_DIGITS,
    PASSWORD_MIN_LENGTH,
    PASSWORD_MIN_SPECIAL,
    PASSWORD_MIN_UPPERCASE,
    PASSWORD_SPECIAL_CHARS,
)


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
        PasswordValidationResult with validation status and any errors
    """
    errors: list[str] = []

    # Check minimum length
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"Le mot de passe doit contenir au moins {PASSWORD_MIN_LENGTH} caractères.")

    # Check maximum length
    if len(password) > PASSWORD_MAX_LENGTH:
        errors.append(f"Le mot de passe ne peut pas dépasser {PASSWORD_MAX_LENGTH} caractères.")

    # Count uppercase letters
    uppercase_count = sum(1 for c in password if c.isupper())
    if uppercase_count < PASSWORD_MIN_UPPERCASE:
        errors.append(
            f"Le mot de passe doit contenir au moins {PASSWORD_MIN_UPPERCASE} lettres majuscules."
        )

    # Count digits
    digit_count = sum(1 for c in password if c.isdigit())
    if digit_count < PASSWORD_MIN_DIGITS:
        errors.append(f"Le mot de passe doit contenir au moins {PASSWORD_MIN_DIGITS} chiffres.")

    # Count special characters
    special_count = sum(1 for c in password if c in PASSWORD_SPECIAL_CHARS)
    if special_count < PASSWORD_MIN_SPECIAL:
        errors.append(
            f"Le mot de passe doit contenir au moins {PASSWORD_MIN_SPECIAL} caractères spéciaux ({PASSWORD_SPECIAL_CHARS[:10]}...)."
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


def get_password_requirements_message() -> str:
    """
    Get a human-readable message describing password requirements.

    Returns:
        Formatted string with password requirements
    """
    return (
        f"Le mot de passe doit contenir au moins {PASSWORD_MIN_LENGTH} caractères, "
        f"dont {PASSWORD_MIN_UPPERCASE} majuscules, "
        f"{PASSWORD_MIN_DIGITS} chiffres et "
        f"{PASSWORD_MIN_SPECIAL} caractères spéciaux."
    )


# Regex pattern for client-side validation (JavaScript compatible)
PASSWORD_REGEX_PATTERN = (
    f"^(?=(?:.*[A-Z]){{{PASSWORD_MIN_UPPERCASE},}})"  # At least N uppercase
    f"(?=(?:.*[0-9]){{{PASSWORD_MIN_DIGITS},}})"  # At least N digits
    f"(?=(?:.*[{re.escape(PASSWORD_SPECIAL_CHARS)}]){{{PASSWORD_MIN_SPECIAL},}})"  # At least N special
    f".{{{PASSWORD_MIN_LENGTH},{PASSWORD_MAX_LENGTH}}}$"  # Length constraint
)
