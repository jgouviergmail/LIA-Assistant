"""Optional provider-key verification contract (B10).

- verification is advisory: 200 = valid, 401/403 = invalid, anything else
  (timeout, network error, 5xx) = unverified — installation NEVER blocks on
  a network error;
- the key travels ONLY in the Authorization header, never in the URL;
- base URLs honor the same {PROVIDER}_BASE_URL overrides as the backend
  adapter so hermetic qualification can point at the fake provider.
"""

from __future__ import annotations

import urllib.error

import pytest

from scripts.install.model import REQUIRED_PROVIDER_IDS, VerifyOutcome
from scripts.install.verify import provider_models_url, verify_provider_key

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
    assert request.get_header("Authorization") == f"Bearer {KEY}"  # type: ignore[attr-defined]


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failures_are_invalid(status: int) -> None:
    error = urllib.error.HTTPError("u", status, "denied", None, None)  # type: ignore[arg-type]
    assert verify_provider_key("openai", KEY, _Opener(error)) is VerifyOutcome.INVALID


@pytest.mark.parametrize(
    "outcome",
    [
        urllib.error.URLError("unreachable"),
        TimeoutError("slow"),
        urllib.error.HTTPError("u", 500, "boom", None, None),  # type: ignore[arg-type]
    ],
)
def test_network_and_server_errors_never_block(outcome: Exception) -> None:
    assert (
        verify_provider_key("openai", KEY, _Opener(outcome))
        is VerifyOutcome.UNVERIFIED
    )


def test_base_urls_default_to_the_vendor_endpoints() -> None:
    assert provider_models_url("openai") == "https://api.openai.com/v1/models"
    assert provider_models_url("deepseek") == "https://api.deepseek.com/models"


def test_base_urls_honor_the_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://fake-provider:18080/v1")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "http://fake-provider:18080/v1")
    assert provider_models_url("openai") == "http://fake-provider:18080/v1/models"
    assert provider_models_url("deepseek") == "http://fake-provider:18080/v1/models"
