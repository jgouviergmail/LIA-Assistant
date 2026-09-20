"""What an OpenAI key can open as a LIVE conversation (ADR-299, wave 2 A9).

The same seam as ``gemini_live_listing``, for the same reason: the live
provider (``domains/live/providers/openai_live.py``) offers the listing in the
connector form and the API-key verifier (``domains/connectors``) accepts a key
on it, so ``connectors`` never imports ``live``.

Measured 2026-09-19 on the dev instance's key: ``GET /v1/models`` lists
``gpt-live-1`` AND ``gpt-live-transcribe`` — a transcription model under the
live prefix, told apart by the same purpose word as Gemini's
(``LIVE_NON_CONVERSATIONAL_MODEL_WORDS``); ``GET /v1/models/gpt-live-1``
answers 200 with ``shutdown_date: null``.

The HTTP client is built per call on the PERSON's key and never kept (the
singleton rule); ``http_client`` is the seam the tests replace with a
``MockTransport``.
"""

from __future__ import annotations

import httpx

from src.core.constants import (
    LIVE_NON_CONVERSATIONAL_MODEL_WORDS,
    OPENAI_API_BASE_URL_DEFAULT,
    OPENAI_LIVE_HTTP_TIMEOUT_SECONDS,
    OPENAI_LIVE_MODEL_PREFIX,
)


def http_client(*, timeout: float = OPENAI_LIVE_HTTP_TIMEOUT_SECONDS) -> httpx.AsyncClient:
    """A per-call HTTP client on the provider's base URL (a seam the tests replace).

    Args:
        timeout: The bound of every request made through the client.

    Returns:
        An ``httpx.AsyncClient`` the caller closes (``async with``).
    """
    return httpx.AsyncClient(base_url=OPENAI_API_BASE_URL_DEFAULT, timeout=timeout)


def auth_header(api_key: str) -> dict[str, str]:
    """The bearer header of the person's key."""
    return {"Authorization": f"Bearer {api_key}"}


def is_conversational_live_model(name: str) -> bool:
    """Whether a model id is a live CONVERSATION model — the prefix, minus the purpose words."""
    return name.startswith(OPENAI_LIVE_MODEL_PREFIX) and not any(
        word in name for word in LIVE_NON_CONVERSATIONAL_MODEL_WORDS
    )


async def list_live_model_names(api_key: str) -> list[str]:
    """The conversational live models the key may open, sorted.

    Args:
        api_key: The person's provider key.

    Returns:
        Model ids (``gpt-live-1`` …), possibly empty.

    Raises:
        httpx.HTTPStatusError: When the provider refuses the key (401) or the
            listing (any non-2xx) — the caller reads it as « not verified ».
    """
    async with http_client() as client:
        response = await client.get("/models", headers=auth_header(api_key))
        response.raise_for_status()
        data = response.json().get("data", [])
    return sorted(
        str(model.get("id"))
        for model in data
        if isinstance(model, dict) and is_conversational_live_model(str(model.get("id", "")))
    )


__all__ = ["auth_header", "http_client", "is_conversational_live_model", "list_live_model_names"]
