"""Exceptions for the STT abstraction layer."""

from __future__ import annotations


class STTProviderError(Exception):
    """Raised when a remote STT provider call fails.

    Carries a stable error code so the WebSocket handler can map it to the
    matching close code / frontend i18n key without parsing the message.

    Recognised codes (kept in sync with the WebSocket handler and the
    meetings' permanent codes):
    - ``elevenlabs_api_key_missing`` / ``openai_api_key_missing`` /
      ``fishaudio_api_key_missing``: the provider's key is not configured.
    - ``provider_unknown``: no remote engine serves the configured provider.
    - ``invalid_api_key``: the provider refused the configured key.
    - ``provider_payment_required``: the provider's account has no credit
      left (Fish Audio, HTTP 402).
    - ``provider_file_too_large``: the provider refused the recording's size
      or length.
    - ``provider_timeout``: HTTP timeout while calling the provider.
    - ``provider_rate_limited``: HTTP 429 from the provider; ``retry_after``
      may carry the seconds suggested by the ``Retry-After`` header.
    - ``provider_http_error``: any other 4xx/5xx response.
    - ``provider_audio_too_short``: the audio is below the provider's minimum;
      resending the same recording to that provider cannot fix it.
    - ``provider_invalid_response``: 200 OK but the body did not match the
      expected schema.
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
