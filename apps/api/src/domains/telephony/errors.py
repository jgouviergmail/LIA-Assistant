"""How the person's phone identity can be refused (lot 1).

Built on the central taxonomy (rule #18: never a raw ``HTTPException``), kept
in the domain like the bookmarks' and the meetings' raisers so
``core/exceptions.py`` — size-frozen — does not grow by a family it has no
reason to know. Every sentence is translated through ``APIMessages``.
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import status

from src.core.exceptions import BaseAPIException, ResourceConflictError, ValidationError
from src.core.i18n import normalize_language
from src.core.i18n_api_messages import APIMessages

__all__ = [
    "PhoneVerificationLockedError",
    "raise_phone_number_invalid",
    "raise_phone_number_missing",
    "raise_phone_verification_call_not_placed",
    "raise_phone_verification_code_wrong",
    "raise_phone_verification_locked",
    "raise_phone_verification_not_pending",
    "raise_phone_verification_too_many_calls",
]


class PhoneVerificationLockedError(BaseAPIException):
    """Too many wrong codes: the pending verification is void — 429.

    A class of its own so the client can tell « try again » from « start a
    new call » without parsing a translated sentence.
    """

    def __init__(self, detail: str, *, log_event: str = "phone_verification_locked") -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            log_level="info",
            log_event=log_event,
        )


def raise_phone_number_invalid(language: str) -> NoReturn:
    """Raise 400 when the typed number is not a dialable line.

    Args:
        language: The caller's language, for the translated sentence.

    Raises:
        ValidationError: 400 Bad Request.
    """
    raise ValidationError(
        detail=APIMessages.phone_number_invalid(normalize_language(language)),
        field="phone_number",
    )


def raise_phone_call_mode_unknown(language: str) -> NoReturn:
    """Raise 400 when a call mode is off the vocabulary (ADR-301).

    Args:
        language: The caller's language, for the translated sentence.

    Raises:
        ValidationError: 400 Bad Request.
    """
    raise ValidationError(
        detail=APIMessages.phone_call_mode_unknown(normalize_language(language)),
        field="call_mode",
    )


def raise_phone_domain_unknown(language: str) -> NoReturn:
    """Raise 400 when a domain switch names something the phone does not offer.

    Args:
        language: The caller's language, for the translated sentence.

    Raises:
        ValidationError: 400 Bad Request.
    """
    raise ValidationError(
        detail=APIMessages.phone_domain_unknown(normalize_language(language)),
        field="disabled_domains",
    )


def raise_phone_number_missing(language: str) -> NoReturn:
    """Raise 409 when an act needs a declared number and there is none.

    Args:
        language: The caller's language, for the translated sentence.

    Raises:
        ResourceConflictError: 409 Conflict.
    """
    raise ResourceConflictError(
        resource_type="phone_identity",
        detail=APIMessages.phone_number_missing(normalize_language(language)),
    )


def raise_phone_verification_not_pending(language: str) -> NoReturn:
    """Raise 409 when a code is typed while no verification is in flight.

    Args:
        language: The caller's language, for the translated sentence.

    Raises:
        ResourceConflictError: 409 Conflict.
    """
    raise ResourceConflictError(
        resource_type="phone_verification",
        detail=APIMessages.phone_verification_not_pending(normalize_language(language)),
    )


def raise_phone_verification_code_wrong(attempts_left: int, language: str) -> NoReturn:
    """Raise 400 when the typed code does not match the one spoken.

    Args:
        attempts_left: How many tries remain before the verification is void.
        language: The caller's language, for the translated sentence.

    Raises:
        ValidationError: 400 Bad Request.
    """
    raise ValidationError(
        detail=APIMessages.phone_verification_code_wrong(
            attempts_left, normalize_language(language)
        ),
        field="code",
        attempts_left=attempts_left,
    )


def raise_phone_verification_locked(language: str) -> NoReturn:
    """Raise 429 once the attempts are spent.

    Args:
        language: The caller's language, for the translated sentence.

    Raises:
        PhoneVerificationLockedError: 429 Too Many Requests.
    """
    raise PhoneVerificationLockedError(
        detail=APIMessages.phone_verification_locked(normalize_language(language))
    )


def raise_phone_verification_too_many_calls(language: str) -> NoReturn:
    """Raise 429 when the account started too many verification calls this hour.

    Args:
        language: The caller's language, for the translated sentence.

    Raises:
        PhoneVerificationLockedError: 429 Too Many Requests.
    """
    raise PhoneVerificationLockedError(
        detail=APIMessages.phone_verification_too_many_calls(normalize_language(language)),
        log_event="phone_verification_rate_limited",
    )


def raise_phone_verification_call_not_placed(language: str, *, reason: str) -> NoReturn:
    """Raise 409 when the verification call could not be placed.

    Args:
        language: The caller's language, for the translated sentence.
        reason: The initiate status, for the log only (never the number).

    Raises:
        ResourceConflictError: 409 Conflict.
    """
    raise ResourceConflictError(
        resource_type="phone_verification",
        detail=APIMessages.phone_verification_call_not_placed(normalize_language(language)),
        reason=reason,
    )
