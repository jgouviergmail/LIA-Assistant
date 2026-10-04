"""Exceptions for the TTS abstraction layer.

Mirrors :class:`STTProviderError` (``stt/exceptions.py``) so both halves of
the voice domain expose structured failures to the rest of the codebase
instead of raw :class:`RuntimeError` blobs that swallow context. Keeping
both halves symmetrical lets callers handle voice provider failures with
a single ``except (STTProviderError, TTSProviderError)`` when needed.
"""

from __future__ import annotations

from typing import Final

#: Failures a second attempt of the same call can outlive: the provider was
#: slow, busy, unreachable, or answered without audio (the free engine does, one
#: synthesis in twenty-four, measured 2026-09-26).
#: The code of a provider's « too many requests » (HTTP 429).
RATE_LIMITED_CODE: Final[str] = "provider_rate_limited"

_TRANSIENT_CODES: Final[frozenset[str]] = frozenset(
    {
        "provider_timeout",
        RATE_LIMITED_CODE,
        "provider_network_error",
        "provider_invalid_response",
    }
)

#: Statuses of a ``provider_http_error`` that say « not now » rather than « no ».
_TRANSIENT_STATUSES: Final[frozenset[int]] = frozenset({408, 429})


class TTSProviderError(Exception):
    """Raised when a TTS provider call fails.

    Carries a stable error code so the streaming pipeline (sentence
    streamer, voice comment service) can log structured failures and
    surface a precise i18n key to the frontend without parsing the
    free-form message.

    Recognised codes (kept in sync with the TTS clients):
    - ``api_key_missing``: no provider key configured for the active
      ``voice_tts`` override (admin must add it via the Provider Keys UI).
    - ``provider_timeout``: HTTP timeout while calling the provider.
    - ``provider_rate_limited``: HTTP 429 from the provider; ``retry_after``
      may carry the seconds suggested by the ``Retry-After`` header.
    - ``provider_http_error``: any other 4xx/5xx response, plus the
      original status in ``details`` for diagnostics.
    - ``provider_invalid_response``: 200 OK but the body did not match the
      expected schema (empty audio, malformed payload).
    - ``provider_network_error``: lower-level transport failure
      (connection refused, DNS error, broken pipe).
    """

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        retry_after_seconds: float | None = None,
        details: object | None = None,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.retry_after_seconds = retry_after_seconds
        self.details = details

    @property
    def transient(self) -> bool:
        """Whether the same call, tried again, may succeed.

        Read from the code and, for ``provider_http_error``, the status the
        client recorded in ``details`` — never from the message. A 5xx, a 408
        or a 429 is transient, a 4xx is not; a failure the client could not
        tie to a status (an unclassified exception it wrapped) is treated as
        transient: trying again costs one call, giving up loses the audio.
        """
        if self.code in _TRANSIENT_CODES:
            return True
        if self.code != "provider_http_error":
            return False
        status = self._status()
        if status is None:
            return True
        return status >= 500 or status in _TRANSIENT_STATUSES

    @property
    def rate_limited(self) -> bool:
        """Whether the provider refused on a QUOTA — a wait, not a blip, is what helps.

        Read from the code, or from the status a client recorded for an error it
        could not name more precisely (never from the message).
        """
        return self.code == RATE_LIMITED_CODE or (
            self.code == "provider_http_error" and self._status() == 429
        )

    def _status(self) -> int | None:
        status = self.details.get("status_code") if isinstance(self.details, dict) else None
        return status if isinstance(status, int) else None


def tts_failure_facts(exc: BaseException) -> dict[str, object]:
    """What a log line may say about a failed synthesis: facts, never the message.

    A provider's message may quote the text it refused, and a code is bounded
    (ADR-303). A failure no client classified is named by its type alone.

    Args:
        exc: The exception a synthesis raised.

    Returns:
        Keyword arguments for the failure's log line.
    """
    if not isinstance(exc, TTSProviderError):
        return {"error_type": type(exc).__name__}
    return {
        "error_type": type(exc).__name__,
        "error_code": exc.code,
        "status_code": exc._status(),
        "transient": exc.transient,
    }
