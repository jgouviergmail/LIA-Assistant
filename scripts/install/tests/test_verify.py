"""Optional provider-key verification contract (B10).

- verification is advisory: 200 = valid, 401/403 = invalid, anything else
  (timeout, network error, 5xx) = unverified — installation NEVER blocks on
  a network error;
- the key travels ONLY in a request header, never in the URL: the bearer
  token of an OpenAI-compatible provider, Anthropic's ``x-api-key`` beside
  the API version that API requires;
- base URLs honor the same {PROVIDER}_BASE_URL overrides as the backend
  adapter so hermetic qualification can point at the fake provider;
- the operator is told what each REQUIRED provider answered, in the wizard's
  language; an accepted key is said nothing about, an optional key is sent
  nowhere, and the advice stops nothing.
"""

from __future__ import annotations

import urllib.error

import pytest

from scripts.install.i18n import msg
from scripts.install.model import REQUIRED_PROVIDER_IDS, VerifyOutcome
from scripts.install.verify import (
    advise_on_provider_keys,
    provider_models_url,
    verify_provider_key,
)

KEY = "sk-CANARY-secret"


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _Opener:
    def __init__(self, outcome: object) -> None:
        self._outcome = outcome
        self.requests: list[object] = []

    def __call__(self, request: object, *, timeout: float) -> object:
        self.requests.append(request)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return _Response(int(self._outcome))  # type: ignore[arg-type]


@pytest.mark.parametrize("provider", REQUIRED_PROVIDER_IDS)
def test_200_is_valid_and_key_stays_out_of_the_url(provider: str) -> None:
    opener = _Opener(200)
    assert verify_provider_key(provider, KEY, opener) is VerifyOutcome.VALID
    request = opener.requests[0]
    assert KEY not in request.full_url  # type: ignore[attr-defined]
    sent = dict(request.header_items())  # type: ignore[attr-defined]
    assert KEY in " ".join(sent.values())


def test_an_openai_compatible_provider_reads_a_bearer_token() -> None:
    opener = _Opener(200)
    verify_provider_key("deepseek", KEY, opener)
    request = opener.requests[0]
    assert request.get_header("Authorization") == f"Bearer {KEY}"  # type: ignore[attr-defined]


def test_anthropic_reads_its_own_header_beside_the_api_version() -> None:
    """A bearer token is refused there: the API key travels in ``x-api-key``,
    and a request naming no ``anthropic-version`` is a 400, which would read
    as « unverified » for a valid key."""
    opener = _Opener(200)
    verify_provider_key("anthropic", KEY, opener)
    request = opener.requests[0]
    assert request.get_header("X-api-key") == KEY  # type: ignore[attr-defined]
    assert request.get_header("Anthropic-version")  # type: ignore[attr-defined]
    assert request.get_header("Authorization") is None  # type: ignore[attr-defined]


@pytest.mark.parametrize("provider", REQUIRED_PROVIDER_IDS)
@pytest.mark.parametrize("status", [401, 403])
def test_auth_failures_are_invalid(provider: str, status: int) -> None:
    error = urllib.error.HTTPError("u", status, "denied", None, None)  # type: ignore[arg-type]
    assert verify_provider_key(provider, KEY, _Opener(error)) is VerifyOutcome.INVALID


@pytest.mark.parametrize("provider", REQUIRED_PROVIDER_IDS)
@pytest.mark.parametrize(
    "outcome",
    [
        urllib.error.URLError("unreachable"),
        TimeoutError("slow"),
        urllib.error.HTTPError("u", 500, "boom", None, None),  # type: ignore[arg-type]
    ],
)
def test_network_and_server_errors_never_block(provider: str, outcome: Exception) -> None:
    assert (
        verify_provider_key(provider, KEY, _Opener(outcome))
        is VerifyOutcome.UNVERIFIED
    )


def test_base_urls_default_to_the_vendor_endpoints() -> None:
    assert provider_models_url("anthropic") == "https://api.anthropic.com/v1/models"
    assert provider_models_url("deepseek") == "https://api.deepseek.com/models"


def test_base_urls_honor_the_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://fake-provider:18080")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "http://fake-provider:18080/v1")
    assert provider_models_url("anthropic") == "http://fake-provider:18080/v1/models"
    assert provider_models_url("deepseek") == "http://fake-provider:18080/v1/models"


def test_the_body_of_a_refusal_is_released() -> None:
    """An HTTP error carries the response it refused with: left open, its
    temporary file is closed by the garbage collector, whenever that runs."""
    import io

    body = io.BytesIO(b"denied")
    error = urllib.error.HTTPError("u", 401, "denied", None, body)  # type: ignore[arg-type]

    assert verify_provider_key("deepseek", KEY, _Opener(error)) is VerifyOutcome.INVALID
    assert body.closed


class _ByProvider:
    """An opener answering each provider's model listing in its own way."""

    def __init__(self, outcomes: dict[str, object]) -> None:
        self._outcomes = outcomes
        self.requests: list[object] = []

    def __call__(self, request: object, *, timeout: float) -> object:
        self.requests.append(request)
        url = request.full_url  # type: ignore[attr-defined]
        for provider, outcome in self._outcomes.items():
            if provider in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return _Response(int(outcome))  # type: ignore[call-overload]
        raise AssertionError(f"a provider nobody declared was asked: {url}")


def _refused() -> urllib.error.HTTPError:
    return urllib.error.HTTPError("u", 401, "denied", None, None)  # type: ignore[arg-type]


def test_the_operator_is_told_what_each_required_provider_answered() -> None:
    """The check existed, tested, and had no caller: a mistyped key was learnt
    from a chat that failed, after the whole installation."""
    printed: list[str] = []
    opener = _ByProvider(
        {"anthropic": _refused(), "deepseek": urllib.error.URLError("unreachable")}
    )

    outcomes = advise_on_provider_keys(
        {"anthropic": KEY, "deepseek": KEY}, opener, print_fn=printed.append, language="en"
    )

    assert outcomes == {
        "anthropic": VerifyOutcome.INVALID,
        "deepseek": VerifyOutcome.UNVERIFIED,
    }
    assert printed == [
        msg("info.key_invalid", "en", provider="anthropic"),
        msg("info.key_unverified", "en", provider="deepseek"),
    ]
    assert KEY not in " ".join(printed)


def test_a_key_its_provider_accepts_is_said_nothing_about() -> None:
    printed: list[str] = []
    opener = _ByProvider({"anthropic": 200, "deepseek": 200})

    outcomes = advise_on_provider_keys(
        {"anthropic": KEY, "deepseek": KEY}, opener, print_fn=printed.append, language="en"
    )

    assert set(outcomes.values()) == {VerifyOutcome.VALID}
    assert printed == []


def test_only_the_required_keys_are_sent_and_each_to_its_own_provider() -> None:
    """An optional key has no listing this module knows: it is sent nowhere."""
    opener = _ByProvider({"anthropic": 200, "deepseek": 200})
    keys = {"anthropic": "sk-a-CANARY", "deepseek": "sk-d-CANARY", "gemini": "g-CANARY"}

    outcomes = advise_on_provider_keys(keys, opener, print_fn=lambda _: None, language="en")

    assert set(outcomes) == set(REQUIRED_PROVIDER_IDS)
    assert len(opener.requests) == len(REQUIRED_PROVIDER_IDS)
    for request in opener.requests:
        url = request.full_url  # type: ignore[attr-defined]
        sent = " ".join(dict(request.header_items()).values())  # type: ignore[attr-defined]
        own = next(key for provider, key in keys.items() if provider in url)
        assert own in sent
        assert all(other not in sent for other in keys.values() if other != own)
        assert all(key not in url for key in keys.values())


def test_a_required_key_nobody_gave_is_not_asked_about() -> None:
    opener = _ByProvider({"deepseek": 200})

    outcomes = advise_on_provider_keys(
        {"deepseek": KEY}, opener, print_fn=lambda _: None, language="en"
    )

    assert set(outcomes) == {"deepseek"}


def test_the_advice_speaks_the_language_of_the_wizard() -> None:
    printed: list[str] = []
    opener = _ByProvider({"anthropic": _refused(), "deepseek": 200})

    advise_on_provider_keys(
        {"anthropic": KEY, "deepseek": KEY}, opener, print_fn=printed.append, language="fr"
    )

    assert printed == [msg("info.key_invalid", "fr", provider="anthropic")]
    assert printed != [msg("info.key_invalid", "en", provider="anthropic")]
