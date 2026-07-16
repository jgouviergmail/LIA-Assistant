"""Functional verifiers for API-key connectors (audit F034 / F051).

Two-tier activation contract. ``ACTIVE`` means "activated and usable"; the
connector-metadata flag ``functionally_verified`` is what distinguishes a
provider-proven key from a format-only one — *not* the ``ACTIVE`` status itself:

- Types **with** an entry in ``API_KEY_FUNCTIONAL_VERIFIERS`` are gated on a
  real, cheap, authenticated call: ``validate_api_key`` runs the verifier (under
  a timeout) and the activation route refuses to save when it fails, so a
  wrong/revoked key never reaches ``ACTIVE`` and ``functionally_verified`` is
  ``True``.
- Types **without** an entry activate on the format check alone: a well-formed
  key goes ``ACTIVE`` with ``functionally_verified=False`` (surfaced honestly in
  the API/UI). Such a key may still be wrong and fail on first real use — the UI
  must never present a format-only connector as verified.

Each entry performs one real, cheap, authenticated call and returns
``(is_valid, message)``. A verifier is added ONLY for providers exposing a
cheap, side-effect-free, non-billed authenticated probe. Deliberately
format-only today:

- ``PERPLEXITY`` — the only authenticated endpoint is a billed chat completion;
  there is no free "who am I / list models" probe, so verifying would spend the
  user's credits on activation. Format-only until a free probe exists.
- ``GOOGLE_PLACES`` — authenticated through the *global* ``GOOGLE_API_KEY`` (not a
  per-user connector key) and every call is billed; not a per-key activation.
- ``PHILIPS_HUE`` — authenticates against a LAN bridge, not a cloud API; liveness
  is device-reachability, handled in its own client.
- ``ELEVENLABS_TELEPHONY`` — runs its own functional ``validate_key`` ping in
  ``domains/telephony/connector.py`` and does not use this generic path.
"""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable

from src.domains.connectors.models import ConnectorType
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# (api_key, api_secret) -> (is_valid, human-readable message)
ApiKeyVerifier = Callable[[str, str | None], Awaitable[tuple[bool, str]]]


async def _verify_openweathermap(api_key: str, _api_secret: str | None) -> tuple[bool, str]:
    """Confirm an OpenWeatherMap key by geocoding a known city (401 on bad key)."""
    from src.domains.connectors.clients.openweathermap_client import OpenWeatherMapClient

    client = OpenWeatherMapClient(api_key=api_key)
    try:
        await client.geocode("London", country="GB", limit=1)
        return True, "OpenWeatherMap API key verified"
    except Exception as exc:  # noqa: BLE001 - any failure means "not verified"
        logger.info("api_key_verify_failed", connector="openweathermap", error=str(exc))
        return False, f"OpenWeatherMap rejected the key ({type(exc).__name__})"
    finally:
        with contextlib.suppress(Exception):
            await client.close()


async def _verify_brave_search(api_key: str, _api_secret: str | None) -> tuple[bool, str]:
    """Confirm a Brave Search key with a minimal 1-result web query.

    A wrong/revoked key makes ``_make_request`` raise on 401/403, which
    ``BraveSearchClient.search`` collapses to ``None`` — so a non-``None`` result
    means the key authenticated. Any failure (bad key, network, quota) fails
    closed: the connector must not go ACTIVE on uncertainty.
    """
    from src.domains.connectors.clients.brave_search_client import BraveSearchClient

    client = BraveSearchClient(api_key=api_key)
    try:
        result = await client.search("lia connectivity check", count=1)
        if result is not None:
            return True, "Brave Search API key verified"
        return False, "Brave Search rejected the key or was unreachable"
    except Exception as exc:  # noqa: BLE001 - any failure means "not verified"
        logger.info("api_key_verify_failed", connector="brave_search", error=str(exc))
        return False, f"Brave Search rejected the key ({type(exc).__name__})"
    finally:
        with contextlib.suppress(Exception):
            await client.close()


# Registry — extend as connectors gain cheap, side-effect-free verification.
API_KEY_FUNCTIONAL_VERIFIERS: dict[ConnectorType, ApiKeyVerifier] = {
    ConnectorType.OPENWEATHERMAP: _verify_openweathermap,
    ConnectorType.BRAVE_SEARCH: _verify_brave_search,
}
