"""The streamed HITL question path carries its token tracker (contre-audit G1).

``hitl_question_generator`` is one of the three streamed LLM slots, yet it has
never written a single row to ``token_usage_logs`` in the whole history of the
production database (measured 2026-08-16; its siblings
``hitl_plan_approval_question_generator`` and ``hitl_draft_critique`` have
rows). Diagnosis: the path is wired but rarely taken — the owner's real
confirmations flow through draft cards. That makes THIS pin the only thing
standing between "rarely taken" and "silently untracked the day it is taken":
the tracker must reach the LLM config, and the node name must be the one the
ledger will attribute the spend to.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch


class _CapturingLLM:
    """Fake streamed LLM that records the config it was invoked with."""

    def __init__(self) -> None:
        self.captured_config: dict[str, Any] | None = None

    async def astream(self, prompt: str, config: dict[str, Any] | None = None):
        self.captured_config = config
        chunk = MagicMock()
        chunk.text = "Confirmer ?"
        yield chunk

    async def ainvoke(self, prompt: str, config: dict[str, Any] | None = None) -> Any:
        self.captured_config = config
        response = MagicMock()
        response.text = "Confirmer ?"
        return response


async def _generator_with(fake_llm: _CapturingLLM):
    with patch("src.domains.agents.services.hitl.question_generator.get_llm") as mock_get_llm:
        mock_get_llm.return_value = fake_llm
        from src.domains.agents.services.hitl.question_generator import HitlQuestionGenerator

        return HitlQuestionGenerator()


class TestStreamedQuestionCarriesTracker:
    async def test_tracker_reaches_the_llm_config(self) -> None:
        fake_llm = _CapturingLLM()
        generator = await _generator_with(fake_llm)
        tracker = MagicMock(name="TokenTrackingCallback")

        async for _ in generator.generate_confirmation_question_stream(
            tool_name="send_email_tool",
            tool_args={"to": "x@example.com"},
            user_language="fr",
            tracker=tracker,
        ):
            pass

        assert fake_llm.captured_config is not None
        assert tracker in fake_llm.captured_config.get("callbacks", [])

    async def test_node_name_is_the_ledger_attribution(self) -> None:
        """The metadata node name is what token_usage_logs will record."""
        fake_llm = _CapturingLLM()
        generator = await _generator_with(fake_llm)

        async for _ in generator.generate_confirmation_question_stream(
            tool_name="send_email_tool",
            tool_args={},
            user_language="fr",
            tracker=MagicMock(),
        ):
            pass

        metadata = (fake_llm.captured_config or {}).get("metadata", {})
        assert metadata.get("langgraph_node") == "hitl_question_generator"

    async def test_blocking_variant_carries_the_tracker_too(self) -> None:
        fake_llm = _CapturingLLM()
        generator = await _generator_with(fake_llm)
        tracker = MagicMock(name="TokenTrackingCallback")

        await generator.generate_confirmation_question(
            tool_name="send_email_tool",
            tool_args={},
            user_language="fr",
            tracker=tracker,
        )

        assert fake_llm.captured_config is not None
        assert tracker in fake_llm.captured_config.get("callbacks", [])
