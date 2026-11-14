"""Advisory provider-key verification (B10).

A network problem must NEVER block installation: 200 proves the key, a 401
or 403 disproves it, and everything else (timeouts, DNS, 5xx) is reported
as unverified and the flow continues. The key travels only in a request
header — never in a URL.

The wizard asks it of each required key as soon as the keys are collected,
before anything is generated or deployed (``advise_on_provider_keys``): a
mistyped key is then learnt at the prompt, not from a chat that fails once
the whole installation has run.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping

from scripts.install.i18n import msg
from scripts.install.model import REQUIRED_PROVIDER_IDS, UrlOpener, VerifyOutcome

_DEFAULT_TIMEOUT_S = 10.0

#: Same defaults and {PROVIDER}_BASE_URL override contract as the backend
#: adapter (`_BASE_URL_DEFAULTS`) so hermetic qualification points both at
#: the same fake endpoint. Pinned by the backend alignment test.
_BASE_URLS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com",
    "deepseek": "https://api.deepseek.com",
}

#: Where a provider lists its models, under its base URL. Anthropic's base URL
#: is the host alone — its SDK appends the API version itself.
_MODELS_PATHS: dict[str, str] = {"anthropic": "/v1/models"}
_DEFAULT_MODELS_PATH = "/models"

#: The version every Anthropic request must name; a request without it is a 400.
_ANTHROPIC_VERSION = "2023-06-01"


def provider_models_url(provider: str) -> str:
    """Resolve the provider's model-listing URL (env override honored)."""
    env_value = os.environ.get(f"{provider.upper()}_BASE_URL", "").strip()
    base = env_value or _BASE_URLS[provider]
    return f"{base.rstrip('/')}{_MODELS_PATHS.get(provider, _DEFAULT_MODELS_PATH)}"


def provider_auth_headers(provider: str, key: str) -> dict[str, str]:
    """The header the provider reads its key from.

    Anthropic refuses a bearer token for an API key: it reads ``x-api-key``.
    Every other required provider is OpenAI-compatible.
    """
    if provider == "anthropic":
        return {"x-api-key": key, "anthropic-version": _ANTHROPIC_VERSION}
    return {"Authorization": f"Bearer {key}"}


def verify_provider_key(
    provider: str,
    key: str,
    opener: UrlOpener,
    *,
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> VerifyOutcome:
    """Probe the provider's models endpoint with the collected key."""
    request = urllib.request.Request(
        provider_models_url(provider),
        headers=provider_auth_headers(provider, key),
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 0))
    except urllib.error.HTTPError as exc:
        # The error IS the refused response: its body is released here, not
        # whenever the garbage collector reaches it.
        exc.close()
        return (
            VerifyOutcome.INVALID
            if exc.code in (401, 403)
            else VerifyOutcome.UNVERIFIED
        )
    except Exception:
        return VerifyOutcome.UNVERIFIED
    return VerifyOutcome.VALID if status == 200 else VerifyOutcome.UNVERIFIED


def advise_on_provider_keys(
    provider_keys: Mapping[str, str],
    opener: UrlOpener,
    *,
    print_fn: Callable[[str], None],
    language: str,
) -> dict[str, VerifyOutcome]:
    """Ask each required provider about its key and tell the operator.

    Advisory by contract: a rejected key and an unreachable provider are
    said and stop nothing; an accepted key is said nothing about. Only the
    required providers are asked — theirs are the model listings this module
    knows — so an optional key is sent nowhere.

    Args:
        provider_keys: The keys the operator gave, by provider.
        opener: Injected ``urllib``-style opener.
        print_fn: Where the advice is written.
        language: The wizard language the advice is written in.

    Returns:
        What each required provider answered, for the keys that were given.
    """
    outcomes: dict[str, VerifyOutcome] = {}
    for provider in REQUIRED_PROVIDER_IDS:
        key = provider_keys.get(provider)
        if not key:
            continue
        outcome = verify_provider_key(provider, key, opener)
        outcomes[provider] = outcome
        if outcome is VerifyOutcome.INVALID:
            print_fn(msg("info.key_invalid", language, provider=provider))
        elif outcome is VerifyOutcome.UNVERIFIED:
            print_fn(msg("info.key_unverified", language, provider=provider))
    return outcomes
