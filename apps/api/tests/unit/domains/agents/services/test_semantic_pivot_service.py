"""Semantic pivot: an empty translation is a failure, not an intent (ex-F4/G2).

``translate_to_english`` fed the tool-routing embeddings. It only fell back to
the original query on an EXCEPTION — an empty completion (content filter,
output budget consumed by reasoning) was a successful return, so the empty
string became "the user's intent in English" and, cached, poisoned the routing
of every identical query for the full TTL.

What must hold:
- an empty or whitespace translation falls back to the original query;
- a real translation is returned unchanged;
- an exception still falls back (historical behavior preserved);
- the success log carries query CONTENT at DEBUG, never INFO (PII rule — the
  message body is content, the log levels shipped to production are INFO+).
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.services import semantic_pivot_service as pivot


@pytest.fixture(autouse=True)
def _stub_prompt():
    with patch.object(pivot, "load_prompt", create=True):
        # load_prompt is imported inside the function — patch its source module.
        with patch(
            "src.domains.agents.prompts.prompt_loader.load_prompt",
            return_value="Translate to English.",
        ):
            yield


class TestEmptyTranslationFallback:
    @pytest.mark.parametrize("empty", ["", "   ", "\n"])
    async def test_empty_translation_falls_back_to_original(self, empty: str) -> None:
        with patch.object(pivot, "_cached_translate_llm_call", new=AsyncMock(return_value=empty)):
            result = await pivot.translate_to_english("mes derniers emails")

        assert result == "mes derniers emails"

    async def test_real_translation_is_returned(self) -> None:
        with patch.object(
            pivot,
            "_cached_translate_llm_call",
            new=AsyncMock(return_value="Get my latest emails"),
        ):
            result = await pivot.translate_to_english("mes derniers emails")

        assert result == "Get my latest emails"

    async def test_exception_still_falls_back(self) -> None:
        with patch.object(
            pivot,
            "_cached_translate_llm_call",
            new=AsyncMock(side_effect=RuntimeError("provider down")),
        ):
            result = await pivot.translate_to_english("mes derniers emails")

        assert result == "mes derniers emails"


class TestLogHygiene:
    async def test_success_log_with_content_is_not_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Query content must not reach INFO (the level production ships)."""
        with patch.object(
            pivot,
            "_cached_translate_llm_call",
            new=AsyncMock(return_value="Get my latest emails"),
        ):
            with caplog.at_level(logging.INFO):
                await pivot.translate_to_english("secret personal query")

        for record in caplog.records:
            if record.levelno >= logging.INFO:
                assert "secret personal query" not in record.getMessage()
