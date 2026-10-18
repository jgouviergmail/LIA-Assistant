"""The embeddings read their Gemini key where every provider key is read, at every call.

Five getters read the key from the environment alone, once, when their
singleton was built. The guided installer stores the Gemini key it asks in the
administration, like every provider key, and an administrator enters one in LLM
Configuration — neither ever reached memory recall, document search, journal
search or interest matching. One resolver now reads the administration first,
then the environment, and the client follows the key without a restart.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.infrastructure.llm import gemini_embeddings as module
from src.infrastructure.llm.gemini_embeddings import (
    GeminiRetrievalEmbeddings,
    resolve_gemini_embedding_key,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_google_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def _stored(key: str | None) -> AbstractContextManager[MagicMock]:
    """The key LLM Configuration holds — read through the factory's own resolution."""
    return patch.object(LLMConfigOverrideCache, "get_api_key", return_value=key)


class TestTheResolutionOrder:
    def test_the_administration_key_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "env-gemini")
        monkeypatch.setenv("GOOGLE_API_KEY", "env-google")
        with _stored("admin-gemini") as stored:
            assert resolve_gemini_embedding_key() == "admin-gemini"
        stored.assert_called_once_with("gemini")

    def test_the_gemini_environment_key_comes_next(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "env-gemini")
        monkeypatch.setenv("GOOGLE_API_KEY", "env-google")
        with _stored(None):
            assert resolve_gemini_embedding_key() == "env-gemini"

    def test_the_generic_google_key_is_the_last_resort(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GOOGLE_API_KEY", "env-google")
        with _stored(None):
            assert resolve_gemini_embedding_key() == "env-google"

    def test_a_template_placeholder_is_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_GEMINI_API_KEY", "CHANGE_ME_GEMINI_API_KEY")
        monkeypatch.setenv("GOOGLE_API_KEY", "CHANGE_ME_API_KEY")
        with _stored(None):
            assert resolve_gemini_embedding_key() == ""


class _ClientFactory:
    """Stands for the Google client: records the key each instance was built with."""

    def __init__(self) -> None:
        self.keys: list[str] = []
        self.clients: list[MagicMock] = []

    def __call__(self, *, model: str, google_api_key: str) -> MagicMock:
        if not google_api_key:
            raise ValueError("API key required")
        self.keys.append(google_api_key)
        client = MagicMock()
        client.aembed_query = AsyncMock(return_value=[0.1])
        self.clients.append(client)
        return client


class TestTheClientFollowsTheKey:
    async def test_a_new_key_builds_a_new_client_and_an_unchanged_one_reuses_it(self) -> None:
        keys = iter(["first", "first", "second"])
        factory = _ClientFactory()

        async def run(factory_call: Any, **_: object) -> list[float]:
            # The tracked funnel runs the call it is handed: which client answers.
            result: list[float] = await factory_call()
            return result

        with patch.object(module, "GoogleGenerativeAIEmbeddings", factory):
            embeddings = GeminiRetrievalEmbeddings(key_resolver=lambda: next(keys))
            with patch.object(embeddings, "_async_tracked_call", AsyncMock(side_effect=run)):
                for _ in range(3):
                    await embeddings.aembed_query("hello")

        assert factory.keys == ["first", "second"]
        first, second = factory.clients
        assert first.aembed_query.await_count == 2, "an unchanged key reuses its client"
        assert second.aembed_query.await_count == 1, "the new key's client answers"

    async def test_no_key_refuses_before_any_tracked_call(self) -> None:
        factory = _ClientFactory()
        with patch.object(module, "GoogleGenerativeAIEmbeddings", factory):
            embeddings = GeminiRetrievalEmbeddings(key_resolver=lambda: "")
            tracked = AsyncMock(return_value=[0.1])
            with (
                patch.object(embeddings, "_async_tracked_call", tracked),
                pytest.raises(ValueError, match="API key required"),
            ):
                await embeddings.aembed_query("hello")

        # A missing key is a configuration state, never an embedding failure
        # the self-check would count against the provider.
        tracked.assert_not_awaited()

    def test_a_fixed_key_builds_its_client_at_construction(self) -> None:
        factory = _ClientFactory()
        with patch.object(module, "GoogleGenerativeAIEmbeddings", factory):
            GeminiRetrievalEmbeddings(google_api_key="fixed")
        assert factory.keys == ["fixed"]
