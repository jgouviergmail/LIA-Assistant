"""Advisory provider-key verification (B10).

A network problem must NEVER block installation: 200 proves the key, a 401
or 403 disproves it, and everything else (timeouts, DNS, 5xx) is reported
as unverified and the flow continues. The key travels only in the
``Authorization`` header — never in a URL.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

from scripts.install.model import UrlOpener, VerifyOutcome

_DEFAULT_TIMEOUT_S = 10.0

#: Same defaults and {PROVIDER}_BASE_URL override contract as the backend
#: adapter (`_BASE_URL_DEFAULTS`) so hermetic qualification points both at
#: the same fake endpoint. Pinned by the backend alignment test.
_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
}


def provider_models_url(provider: str) -> str:
    """Resolve the provider's model-listing URL (env override honored)."""
    env_value = os.environ.get(f"{provider.upper()}_BASE_URL", "").strip()
    base = env_value or _BASE_URLS[provider]
    return f"{base.rstrip('/')}/models"


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
        headers={"Authorization": f"Bearer {key}"},
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 0))
    except urllib.error.HTTPError as exc:
        return (
            VerifyOutcome.INVALID
            if exc.code in (401, 403)
            else VerifyOutcome.UNVERIFIED
        )
    except Exception:
        return VerifyOutcome.UNVERIFIED
    return VerifyOutcome.VALID if status == 200 else VerifyOutcome.UNVERIFIED
