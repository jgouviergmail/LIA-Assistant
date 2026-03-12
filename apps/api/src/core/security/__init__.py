"""
Security module for authorization, authentication, and access control.
"""

# Authorization utilities
from src.core.security.authorization import (
    check_resource_ownership,
    check_resource_ownership_by_user_id,
)

# Password validation utilities
from src.core.security.password_validation import (
    PasswordValidationResult,
    get_password_requirements_message,
    validate_password,
    validate_password_strict,
)

# Authentication and cryptography utilities
from src.core.security.utils import (
    AuthProvider,
    cipher_suite,
    create_password_reset_token,
    create_verification_token,
    decrypt_data,
    encrypt_data,
    generate_code_challenge,
    generate_code_verifier,
    generate_state_token,
    get_password_hash,
    is_token_used,
    mark_token_used,
    verify_password,
    verify_single_use_token,
    verify_state_token,
    verify_token,
)

__all__ = [
    # Authorization
    "check_resource_ownership",
    "check_resource_ownership_by_user_id",
    # Authentication & passwords
    "AuthProvider",
    "verify_password",
    "get_password_hash",
    "verify_token",
    "create_verification_token",
    "create_password_reset_token",
    # Password validation
    "validate_password",
    "validate_password_strict",
    "PasswordValidationResult",
    "get_password_requirements_message",
    # Encryption
    "cipher_suite",
    "encrypt_data",
    "decrypt_data",
    # OAuth CSRF & PKCE
    "generate_state_token",
    "verify_state_token",
    "generate_code_verifier",
    "generate_code_challenge",
    # JTI blacklist (PROD only)
    "is_token_used",
    "mark_token_used",
    # Single-use token verification (DRY helper)
    "verify_single_use_token",
]
