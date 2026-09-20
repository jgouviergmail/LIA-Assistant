"""How the live mode refuses (ADR-299), on the central taxonomy.

Kept in the domain like the bookmarks' raisers: ``core/exceptions.py`` is
size-frozen. Every sentence is translated through ``core/i18n_live``.
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import status

from src.core.exceptions import BaseAPIException
from src.core.i18n_live import get_live_phrases

__all__ = [
    "LiveRefusedError",
    "raise_live_connector_missing",
    "raise_live_credential_invalid",
    "raise_live_instance_busy",
    "raise_live_mint_rate_limited",
    "raise_live_mode_unsupported",
    "raise_live_model_unpriced",
    "raise_live_provider_refused",
    "raise_live_session_expired",
    "raise_live_session_in_progress",
    "raise_live_session_not_found",
    "raise_live_thinking_level_unknown",
    "raise_live_voice_unknown",
]


class LiveRefusedError(BaseAPIException):
    """A live session could not start or continue — the CODE names why.

    The wire shape is the typed contract the client already reads
    (``detail: {"code", "message"}`` — ``getApiErrorCode`` / ``readErrorDetail``):
    the code is stable and untranslated, the message is the person's language.
    """

    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message},
            log_level="info",
            log_event=f"live_{code}",
        )
        self.code = code


def raise_live_connector_missing(language: str) -> NoReturn:
    """Raise 409: no active connector of the ``live`` category."""
    raise LiveRefusedError(
        status_code=status.HTTP_409_CONFLICT,
        code="connector_missing",
        message=get_live_phrases(language)["connector_missing"],
    )


def raise_live_session_in_progress(language: str) -> NoReturn:
    """Raise 409: the account already holds a live session."""
    raise LiveRefusedError(
        status_code=status.HTTP_409_CONFLICT,
        code="session_in_progress",
        message=get_live_phrases(language)["session_in_progress"],
    )


def raise_live_instance_busy(language: str) -> NoReturn:
    """Raise 503: the instance cap on open sessions is reached."""
    raise LiveRefusedError(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="instance_busy",
        message=get_live_phrases(language)["instance_busy"],
    )


def raise_live_mint_rate_limited(language: str) -> NoReturn:
    """Raise 429: too many credential mints in the window."""
    raise LiveRefusedError(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code="mint_rate_limited",
        message=get_live_phrases(language)["mint_rate_limited"],
    )


def raise_live_session_not_found(language: str) -> NoReturn:
    """Raise 404: not the caller's session, or already ended (``hide_existence``).

    Coded like every other live refusal — the six sentences existed while the
    raiser answered a bare string, so no client could ever read the code.
    """
    raise LiveRefusedError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="session_not_found",
        message=get_live_phrases(language)["session_not_found"],
    )


def raise_live_credential_invalid(language: str) -> NoReturn:
    """The single-use credential of an offer connection was used, or expired (409)."""
    raise LiveRefusedError(
        status_code=status.HTTP_409_CONFLICT,
        code="credential_invalid",
        message=get_live_phrases(language)["credential_invalid"],
    )


def raise_live_session_expired(language: str) -> NoReturn:
    """Raise 409: the session reached its cap before the extension arrived.

    Told apart from « not found », which the client reads as superseded.
    """
    raise LiveRefusedError(
        status_code=status.HTTP_409_CONFLICT,
        code="session_expired",
        message=get_live_phrases(language)["session_expired"],
    )


def raise_live_provider_refused(language: str, detail: str) -> NoReturn:
    """Raise 422: the provider refused the model, in its own (bounded) words."""
    raise LiveRefusedError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="provider_refused",
        message=get_live_phrases(language)["provider_refused"].format(detail=detail[:200]),
    )


def raise_live_model_unpriced(language: str, model: str) -> NoReturn:
    """Raise 409: the model has no tariff under LLM pricing (ADR-300 wave 3).

    The Live settings offer only declared models, so this is reached by a
    connector configured before the tariff was retired, or by a stored
    choice the listing would no longer make.
    """
    raise LiveRefusedError(
        status_code=status.HTTP_409_CONFLICT,
        code="model_unpriced",
        message=get_live_phrases(language)["model_unpriced"].format(model=model[:96]),
    )


def raise_live_mode_unsupported(language: str) -> NoReturn:
    """Raise 409: the model's wire carries no tool schema, so no DIRECT session (ADR-300 wave 4)."""
    raise LiveRefusedError(
        status_code=status.HTTP_409_CONFLICT,
        code="mode_unsupported",
        message=get_live_phrases(language)["mode_unsupported"],
    )


def raise_live_voice_unknown(language: str, voice: str) -> NoReturn:
    """Raise 422: a voice the provider is not known to serve.

    Measured 2026-09-18: the provider never refuses a wrong voice name — it
    falls back to a default in silence — so LIA is the only place a wrong
    name can be caught.
    """
    raise LiveRefusedError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="voice_unknown",
        message=get_live_phrases(language)["voice_unknown"].format(voice=voice[:64]),
    )


def raise_live_thinking_level_unknown(language: str, level: str) -> NoReturn:
    """Raise 422: a thinking level the chosen model's ladder does not offer.

    The UI is offered exactly what the API accepts (ADR-245): the ladder the
    listing publishes per model is the one the write path enforces.
    """
    raise LiveRefusedError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="thinking_level_unknown",
        message=get_live_phrases(language)["thinking_level_unknown"].format(level=level[:16]),
    )
