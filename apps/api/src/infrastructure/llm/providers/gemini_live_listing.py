"""What a Gemini key can open as a LIVE conversation (ADR-299).

Two readers, and the seam sits here so they share nothing but this module: the
live provider (``domains/live/providers/gemini.py``) offers the listing in the
connector form, and the API-key verifier (``domains/connectors``) accepts a key
on the same listing — a key with no conversational live model is refused before
it is stored. Placing the listing in the live domain closed the
``connectors <-> live`` cycle the coupling ratchet refuses.

Measured 2026-09-18: the listing marks non-conversational models live too (a
transcription, a translation and a robotics model carry
``bidiGenerateContent``), and no structural field tells them apart — a purpose
word in the name does.

The SDK client is built per call on the PERSON's key and never kept (the
singleton rule).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from src.core.constants import LIVE_BIDI_METHOD, LIVE_NON_CONVERSATIONAL_MODEL_WORDS


def gemini_client_of(api_key: str, *, api_version: str | None = None) -> Any:
    """A per-call SDK client (a seam the tests replace).

    Args:
        api_key: The person's provider key.
        api_version: An explicit API version (``v1alpha`` for ephemeral tokens).

    Returns:
        A ``google.genai.Client`` bound to the key.
    """
    from google import genai
    from google.genai import types

    if api_version:
        return genai.Client(
            api_key=api_key, http_options=types.HttpOptions(api_version=api_version)
        )
    return genai.Client(api_key=api_key)


async def _models_of(api_key: str) -> AsyncIterator[Any]:
    """The provider's model listing, on the given key (a seam the tests replace).

    The client is HELD for the whole walk. Measured in the API container on
    2026-09-18 (google-genai 2.10.0): a client built as a temporary in the
    ``list()`` expression is collected while its first request is in flight,
    its aiohttp session closes underneath, and the request dies on
    ``assert self._connector is not None`` — the same listing succeeds the
    moment the client is bound to a name that outlives the iteration.
    """
    client = gemini_client_of(api_key)
    pager = await client.aio.models.list()

    async def _walk(owner: Any) -> AsyncIterator[Any]:
        async for model in pager:
            yield model
        del owner

    return _walk(client)


def is_conversational_live_model(name: str, actions: list[str]) -> bool:
    """Whether a listed model can hold a live CONVERSATION.

    Args:
        name: The model name, without the ``models/`` prefix.
        actions: Its ``supported_actions``.

    Returns:
        True for a model the connector may offer.
    """
    if LIVE_BIDI_METHOD not in actions:
        return False
    lowered = name.lower()
    return not any(word in lowered for word in LIVE_NON_CONVERSATIONAL_MODEL_WORDS)


async def list_live_model_names(api_key: str) -> list[str]:
    """The conversational live models this key may open, without the ``models/`` prefix.

    Args:
        api_key: The person's provider key.

    Returns:
        Sorted names.

    Raises:
        Exception: Whatever the SDK raises for a refused key — the caller
            decides what a refusal means on its surface.
    """
    names: list[str] = []
    async for model in await _models_of(api_key):
        name = str(model.name).removeprefix("models/")
        actions = [str(a) for a in (getattr(model, "supported_actions", None) or [])]
        if is_conversational_live_model(name, actions):
            names.append(name)
    return sorted(names)


__all__ = ["gemini_client_of", "is_conversational_live_model", "list_live_model_names"]
