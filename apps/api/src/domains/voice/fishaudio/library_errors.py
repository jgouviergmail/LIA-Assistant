"""How a voice-library request is refused (ADR-345): a stable code the page translates.

A refusal names itself — ``{"code": ...}`` and the facts the page quotes (a
bound, the slots speaking with a voice) — the shape the knowledge spaces'
refusals already take; the page holds the sentence in six languages. Built on
the central taxonomy (rule #18) and kept in the domain, like the bookmarks' and
the meetings' raisers, so the size-frozen ``core/exceptions.py`` does not grow
by a family it has no reason to know.
"""

from __future__ import annotations

from typing import Final, NoReturn, get_args

from fastapi import status

from src.core.exceptions import BaseAPIException
from src.domains.voice.fishaudio.voices import FishVoicesError, FishVoicesFailure

API_KEY_MISSING: Final[str] = "fishaudio_api_key_missing"
ACCOUNT_CHANGED: Final[str] = "fishaudio_account_changed"
CREATION_DISABLED: Final[str] = "fishaudio_voice_creation_disabled"
CONSENT_REQUIRED: Final[str] = "fishaudio_clone_consent_required"
SAMPLES_COUNT: Final[str] = "fishaudio_clone_samples_count"
SAMPLE_TOO_LARGE: Final[str] = "fishaudio_clone_sample_too_large"
SAMPLE_FORMAT: Final[str] = "fishaudio_clone_sample_format"
TEXTS_MISMATCH: Final[str] = "fishaudio_clone_texts_mismatch"
TITLE_INVALID: Final[str] = "fishaudio_voice_title_invalid"
VOICE_IN_USE: Final[str] = "fishaudio_voice_in_use"
CANDIDATE_EXPIRED: Final[str] = "fishaudio_design_candidate_expired"
CANDIDATE_SAVE_PENDING: Final[str] = "fishaudio_design_save_pending"
DESIGN_STORE_UNAVAILABLE: Final[str] = "fishaudio_design_store_unavailable"
PREFILL_UNAVAILABLE: Final[str] = "fishaudio_prefill_unavailable"
PREFILL_TOO_LONG: Final[str] = "fishaudio_prefill_too_long"
SAMPLE_UNREADABLE: Final[str] = "fishaudio_sample_unreadable"
AUDIT_UNAVAILABLE: Final[str] = "fishaudio_audit_unavailable"
PIN_CONSENT_REQUIRED: Final[str] = "fishaudio_pin_consent_required"
PINS_FULL: Final[str] = "fishaudio_pins_full"
PIN_UNAVAILABLE: Final[str] = "fishaudio_pin_unavailable"
PIN_AUDIT_UNAVAILABLE: Final[str] = "fishaudio_pin_audit_unavailable"

VOICE_NOT_FOUND: Final[str] = "fishaudio_voice_not_found"

#: How each failure of the vendor reaches the page: a status and a code.
_VENDOR_REFUSALS: Final[dict[FishVoicesFailure, tuple[int, str]]] = {
    "rate_limited": (status.HTTP_429_TOO_MANY_REQUESTS, "fishaudio_rate_limited"),
    "payment_required": (status.HTTP_402_PAYMENT_REQUIRED, "fishaudio_payment_required"),
    "unauthorized": (status.HTTP_502_BAD_GATEWAY, "fishaudio_key_refused"),
    "not_found": (status.HTTP_404_NOT_FOUND, VOICE_NOT_FOUND),
    "rejected": (status.HTTP_422_UNPROCESSABLE_CONTENT, "fishaudio_request_rejected"),
    "unavailable": (status.HTTP_502_BAD_GATEWAY, "fishaudio_unavailable"),
}

# Every failure the client can name has its answer (ADR-085: checked at import).
if set(_VENDOR_REFUSALS) != set(get_args(FishVoicesFailure)):
    raise RuntimeError("every Fish Audio library failure needs its refusal")

#: Every code a refusal of this family can carry — the page translates each one.
REFUSAL_CODES: Final[frozenset[str]] = frozenset(
    {
        API_KEY_MISSING,
        ACCOUNT_CHANGED,
        CREATION_DISABLED,
        CONSENT_REQUIRED,
        SAMPLES_COUNT,
        SAMPLE_TOO_LARGE,
        SAMPLE_FORMAT,
        TEXTS_MISMATCH,
        TITLE_INVALID,
        VOICE_IN_USE,
        CANDIDATE_EXPIRED,
        CANDIDATE_SAVE_PENDING,
        DESIGN_STORE_UNAVAILABLE,
        PREFILL_UNAVAILABLE,
        PREFILL_TOO_LONG,
        SAMPLE_UNREADABLE,
        AUDIT_UNAVAILABLE,
        PIN_CONSENT_REQUIRED,
        PINS_FULL,
        PIN_UNAVAILABLE,
        PIN_AUDIT_UNAVAILABLE,
        *(code for _, code in _VENDOR_REFUSALS.values()),
    }
)


def refuse(status_code: int, code: str, **facts: object) -> NoReturn:
    """Refuse with ``code`` and the facts the page quotes.

    Args:
        status_code: The HTTP status.
        code: One of :data:`REFUSAL_CODES`.
        **facts: JSON-safe facts (a bound, slot names) — never a person's words.

    Raises:
        BaseAPIException: Always.
    """
    raise BaseAPIException(
        status_code=status_code,
        detail={"code": code, **facts},
        log_level="info",
        log_event="fishaudio_library_refused",
        code=code,
    )


def refuse_vendor(error: FishVoicesError) -> NoReturn:
    """Refuse with what the vendor's failure means to the administrator.

    Args:
        error: The client's typed failure (its facts, never the vendor's prose).

    Raises:
        BaseAPIException: Always.
    """
    status_code, code = _VENDOR_REFUSALS[error.kind]
    raise BaseAPIException(
        status_code=status_code,
        detail={"code": code},
        log_level="warning",
        log_event="fishaudio_library_vendor_refused",
        kind=error.kind,
        vendor_status=error.details.get("status_code"),
        vendor_code=error.details.get("vendor_code"),
    )


__all__ = [
    "ACCOUNT_CHANGED",
    "API_KEY_MISSING",
    "AUDIT_UNAVAILABLE",
    "CANDIDATE_EXPIRED",
    "CANDIDATE_SAVE_PENDING",
    "CONSENT_REQUIRED",
    "CREATION_DISABLED",
    "DESIGN_STORE_UNAVAILABLE",
    "PINS_FULL",
    "PIN_AUDIT_UNAVAILABLE",
    "PIN_CONSENT_REQUIRED",
    "PIN_UNAVAILABLE",
    "PREFILL_TOO_LONG",
    "PREFILL_UNAVAILABLE",
    "REFUSAL_CODES",
    "SAMPLES_COUNT",
    "SAMPLE_FORMAT",
    "SAMPLE_TOO_LARGE",
    "SAMPLE_UNREADABLE",
    "TEXTS_MISMATCH",
    "TITLE_INVALID",
    "VOICE_IN_USE",
    "VOICE_NOT_FOUND",
    "refuse",
    "refuse_vendor",
]
