"""Exceptions for the TTS abstraction layer.

Mirrors :class:`STTProviderError` (``stt/exceptions.py``) so both halves of
the voice domain expose structured failures to the rest of the codebase
instead of raw :class:`RuntimeError` blobs that swallow context. Keeping
both halves symmetrical lets callers handle voice provider failures with
a single ``except (STTProviderError, TTSProviderError)`` when needed.
"""

from __future__ import annotations


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
