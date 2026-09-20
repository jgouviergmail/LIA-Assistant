"""The live key is verified by a FREE probe: the model listing, filtered on the
live generation method and on a conversational purpose. A model without the
method — or a transcription/translation model that carries it (measured
2026-09-18) — is not offered; a key the provider refuses never reaches ACTIVE."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.connectors.api_key_verifiers import API_KEY_FUNCTIONAL_VERIFIERS
from src.domains.connectors.models import ConnectorType
from src.infrastructure.llm.providers.gemini_live_listing import list_live_model_names

pytestmark = pytest.mark.unit

MODULE = "src.infrastructure.llm.providers.gemini_live_listing"


def _models(*specs: tuple[str, list[str]]):
    async def _aiter():
        for name, actions in specs:
            yield SimpleNamespace(name=f"models/{name}", supported_actions=actions)

    return _aiter()


async def test_live_type_has_a_functional_verifier() -> None:
    assert ConnectorType.GEMINI_LIVE in API_KEY_FUNCTIONAL_VERIFIERS


async def test_listing_keeps_conversational_live_models_only() -> None:
    listing = _models(
        ("gemini-3.8-live", ["bidiGenerateContent"]),
        ("gemini-3.8-live-extended-thinking", ["bidiGenerateContent", "generateContent"]),
        ("gemini-3.5-transcribe-live", ["bidiGenerateContent"]),
        ("gemini-3.5-live-translate-preview", ["bidiGenerateContent"]),
        ("gemini-robotics-er-2-streaming-preview", ["bidiGenerateContent"]),
        ("gemini-x", ["generateContent"]),
    )
    with patch(f"{MODULE}._models_of", AsyncMock(return_value=listing)):
        names = await list_live_model_names("AIza-test-key")
    assert names == ["gemini-3.8-live", "gemini-3.8-live-extended-thinking"]


async def test_a_key_that_lists_a_live_model_is_verified() -> None:
    verifier = API_KEY_FUNCTIONAL_VERIFIERS[ConnectorType.GEMINI_LIVE]
    listing = _models(
        ("gemini-3.8-live", ["bidiGenerateContent"]), ("gemini-x", ["generateContent"])
    )
    with patch(f"{MODULE}._models_of", AsyncMock(return_value=listing)):
        ok, message = await verifier("AIza-test-key", None)
    assert ok is True
    assert "1" in message  # one live model found


async def test_a_key_with_no_live_model_is_refused() -> None:
    verifier = API_KEY_FUNCTIONAL_VERIFIERS[ConnectorType.GEMINI_LIVE]
    listing = _models(("gemini-x", ["generateContent"]))
    with patch(f"{MODULE}._models_of", AsyncMock(return_value=listing)):
        ok, _ = await verifier("AIza-test-key", None)
    assert ok is False


async def test_a_provider_refusal_is_a_refusal() -> None:
    verifier = API_KEY_FUNCTIONAL_VERIFIERS[ConnectorType.GEMINI_LIVE]
    with patch(f"{MODULE}._models_of", AsyncMock(side_effect=RuntimeError("401"))):
        ok, message = await verifier("bad-key-value", None)
    assert ok is False
    assert "RuntimeError" in message
