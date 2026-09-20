"""The GPT-Live key is verified by a FREE probe: the model listing, filtered on
the live prefix and on a conversational purpose. Measured 2026-09-19: the
listing carries ``gpt-live-transcribe`` under the prefix — a transcription
model — told apart by the same purpose words as Gemini's."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from src.domains.connectors.api_key_verifiers import API_KEY_FUNCTIONAL_VERIFIERS
from src.domains.connectors.models import (
    CONNECTOR_FUNCTIONAL_CATEGORIES,
    ConnectorType,
    get_conflicting_connector_types,
)
from src.infrastructure.llm.providers.openai_live_listing import (
    is_conversational_live_model,
    list_live_model_names,
)

pytestmark = pytest.mark.unit

MODULE = "src.infrastructure.llm.providers.openai_live_listing"


def _client(handler):  # type: ignore[no-untyped-def]
    return httpx.AsyncClient(
        base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handler)
    )


def _listing(*ids: str):  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={"data": [{"id": i, "object": "model"} for i in ids]})

    return handler


def test_gpt_live_is_a_live_connector_with_a_functional_verifier() -> None:
    assert ConnectorType.GPT_LIVE in API_KEY_FUNCTIONAL_VERIFIERS
    assert ConnectorType.GPT_LIVE in CONNECTOR_FUNCTIONAL_CATEGORIES["live"]
    # Additive: a second live key never deactivates the first (wave 2 A10).
    assert get_conflicting_connector_types(ConnectorType.GPT_LIVE) == frozenset()


def test_the_filter_keeps_conversational_live_models_only() -> None:
    assert is_conversational_live_model("gpt-live-1")
    assert not is_conversational_live_model("gpt-live-transcribe")
    assert not is_conversational_live_model("gpt-4o-realtime")


async def test_listing_drops_the_transcription_model_and_sorts() -> None:
    handler = _listing("gpt-live-transcribe", "gpt-live-2", "gpt-live-1", "whisper-1")
    with patch(f"{MODULE}.http_client", lambda **_: _client(handler)):
        assert await list_live_model_names("sk-test") == ["gpt-live-1", "gpt-live-2"]


async def test_a_key_that_lists_a_live_model_is_verified() -> None:
    verifier = API_KEY_FUNCTIONAL_VERIFIERS[ConnectorType.GPT_LIVE]
    with patch(f"{MODULE}.http_client", lambda **_: _client(_listing("gpt-live-1", "whisper-1"))):
        ok, message = await verifier("sk-test", None)
    assert ok is True and "1" in message


async def test_a_key_with_no_live_model_is_refused() -> None:
    verifier = API_KEY_FUNCTIONAL_VERIFIERS[ConnectorType.GPT_LIVE]
    with patch(f"{MODULE}.http_client", lambda **_: _client(_listing("whisper-1"))):
        ok, _ = await verifier("sk-test", None)
    assert ok is False


async def test_a_provider_refusal_is_a_refusal_that_names_no_key() -> None:
    def unauthorized(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided"}})

    verifier = API_KEY_FUNCTIONAL_VERIFIERS[ConnectorType.GPT_LIVE]
    with patch(f"{MODULE}.http_client", lambda **_: _client(unauthorized)):
        ok, message = await verifier("sk-test", None)
    assert ok is False
    assert "HTTPStatusError" in message and "sk-test" not in message
