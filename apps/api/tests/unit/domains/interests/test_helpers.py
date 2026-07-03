"""Tests for interest domain helpers (audit wave 3, item A6).

``generate_interest_embedding`` runs on async paths (routers, extraction,
proactive tasks); it must use the native async embedding API instead of
the blocking sync one.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.interests.helpers import generate_interest_embedding, normalize_language_code


@pytest.mark.unit
class TestNormalizeLanguageCode:
    """Locale normalization to base ISO 639-1 codes."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("fr", "fr"),
            ("fr-FR", "fr"),
            ("en_US", "en"),
            ("zh-CN", "zh"),
        ],
    )
    def test_normalizes(self, raw: str, expected: str) -> None:
        assert normalize_language_code(raw) == expected


@pytest.mark.unit
class TestGenerateInterestEmbedding:
    """Async embedding generation via aembed_documents."""

    def test_is_a_coroutine_function(self) -> None:
        """The helper must be awaitable (called from async paths only)."""
        assert asyncio.iscoroutinefunction(generate_interest_embedding)

    async def test_uses_native_async_embedding(self) -> None:
        """Delegates to aembed_documents (non-blocking), returns first vector."""
        embeddings = MagicMock()
        embeddings.aembed_documents = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

        with patch(
            "src.domains.interests.embedding.get_interest_embeddings",
            return_value=embeddings,
        ):
            result = await generate_interest_embedding("machine learning")

        assert result == [0.1, 0.2, 0.3]
        embeddings.aembed_documents.assert_awaited_once_with(["machine learning"])

    async def test_returns_none_on_failure(self) -> None:
        """Graceful degradation: embedding failure yields None, no raise."""
        embeddings = MagicMock()
        embeddings.aembed_documents = AsyncMock(side_effect=RuntimeError("api down"))

        with patch(
            "src.domains.interests.embedding.get_interest_embeddings",
            return_value=embeddings,
        ):
            result = await generate_interest_embedding("machine learning")

        assert result is None
