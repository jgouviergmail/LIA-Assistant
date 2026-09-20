"""What an ElevenLabs key can open as a LIVE conversation: its agents (ADR-300 wave 4).

The same seam as ``gemini_live_listing`` and ``openai_live_listing``, for the
same reason: the live provider (``domains/live/providers/elevenlabs_live.py``)
offers the listing in the connector form and the API-key verifier
(``domains/connectors``) accepts a key on it, so ``connectors`` never imports
``live`` nor ``telephony``.

One page of the agents listing, the largest the endpoint serves: a workspace
holding more agents than that is not a personal account. The HTTP client is
built per call on the PERSON's key and never kept (the singleton rule);
``http_client`` is the seam the tests replace with a ``MockTransport``.
"""

from __future__ import annotations

import httpx

from src.core.constants import (
    DEFAULT_ELEVENLABS_BASE_URL,
    ELEVENLABS_LIVE_AGENTS_PAGE_SIZE,
    OPENAI_LIVE_HTTP_TIMEOUT_SECONDS,
)

#: ElevenLabs authenticates with this header, never a bearer token.
AUTH_HEADER = "xi-api-key"


def http_client(*, timeout: float = OPENAI_LIVE_HTTP_TIMEOUT_SECONDS) -> httpx.AsyncClient:
    """A per-call HTTP client on the provider's base URL (a seam the tests replace)."""
    return httpx.AsyncClient(base_url=DEFAULT_ELEVENLABS_BASE_URL, timeout=timeout)


async def list_agents(api_key: str) -> list[tuple[str, str]]:
    """The agents of the workspace as ``(agent_id, name)``, in the listing's order.

    Args:
        api_key: The person's ElevenLabs key.

    Returns:
        One page of agents; a row without an id is skipped.

    Raises:
        httpx.HTTPStatusError: The provider refused the key or the listing.
    """
    async with http_client() as client:
        response = await client.get(
            "/convai/agents",
            headers={AUTH_HEADER: api_key},
            params={"page_size": ELEVENLABS_LIVE_AGENTS_PAGE_SIZE},
        )
        response.raise_for_status()
        payload = response.json()
    rows = payload.get("agents", []) if isinstance(payload, dict) else []
    return [
        (str(row["agent_id"]), str(row.get("name") or row["agent_id"]))
        for row in rows
        if isinstance(row, dict) and row.get("agent_id")
    ]


__all__ = ["AUTH_HEADER", "http_client", "list_agents"]
