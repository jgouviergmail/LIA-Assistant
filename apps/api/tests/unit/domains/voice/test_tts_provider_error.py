"""Whether a voice provider's failure is worth a second attempt — read from its code."""

from __future__ import annotations

import pytest

from src.domains.voice.exceptions import TTSProviderError, tts_failure_facts

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("code", "details", "transient"),
    [
        ("provider_timeout", None, True),
        ("provider_rate_limited", {"status_code": 429}, True),
        ("provider_network_error", None, True),
        ("provider_invalid_response", None, True),  # the free engine's missing audio
        ("provider_http_error", {"status_code": 503}, True),
        ("provider_http_error", {"status_code": 408}, True),
        ("provider_http_error", {"status_code": 400}, False),  # a refused request stays refused
        ("provider_http_error", {"status_code": 401}, False),
        ("provider_http_error", {"exception_type": "NoAudioReceived"}, True),  # no status known
        ("api_key_missing", None, False),
        ("voice_missing", None, False),
    ],
)
def test_transient_is_read_from_the_code_and_the_status(
    code: str, details: dict[str, object] | None, transient: bool
) -> None:
    assert TTSProviderError(code, details=details).transient is transient


def test_the_message_never_decides() -> None:
    """A message that reads like a passing failure changes nothing."""
    error = TTSProviderError("api_key_missing", "timeout while connecting, rate limited")
    assert error.transient is False


@pytest.mark.parametrize(
    ("code", "details", "rate_limited"),
    [
        ("provider_rate_limited", None, True),
        ("provider_http_error", {"status_code": 429}, True),
        ("provider_http_error", {"status_code": 503}, False),
        ("provider_timeout", None, False),
    ],
)
def test_a_rate_limit_is_read_from_the_code_and_the_status(
    code: str, details: dict[str, object] | None, rate_limited: bool
) -> None:
    """A quota answer asks for a longer wait than a blip: it is told apart structurally."""
    assert TTSProviderError(code, details=details).rate_limited is rate_limited


def test_a_failure_log_carries_the_facts_never_the_message() -> None:
    """ADR-303: what a provider says may quote the text it refused."""
    error = TTSProviderError(
        "provider_http_error",
        "HTTP 400: refused « the words of the answer »",
        details={"status_code": 400},
    )

    assert tts_failure_facts(error) == {
        "error_type": "TTSProviderError",
        "error_code": "provider_http_error",
        "status_code": 400,
        "transient": False,
    }


def test_an_unclassified_failure_is_named_by_its_type_alone() -> None:
    assert tts_failure_facts(RuntimeError("the words of the answer")) == {
        "error_type": "RuntimeError"
    }
