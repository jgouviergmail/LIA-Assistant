"""The extraction target must be what the user said, not what the system wrote (L5 / D3).

On a tool-level HITL refusal, the resumption layer injects a fabricated
``HumanMessage`` whose body is a localized instruction block for the response
LLM. It is long enough to escape the triviality heuristic, so it became the
target of all three extractions: memory, interests and journal analysing the
assistant's own directives, with the risk of persisting them.

Classification is by flag, never by matching the text — the scaffolding exists
in six languages.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.domains.shared.extraction_targets import (
    SYNTHETIC_MESSAGE_KEY,
    find_last_user_message,
    is_synthetic_message,
)


def _synthetic(content: str) -> HumanMessage:
    return HumanMessage(content=content, additional_kwargs={SYNTHETIC_MESSAGE_KEY: True})


@pytest.mark.unit
class TestSyntheticDetection:
    def test_plain_message_is_not_synthetic(self):
        assert is_synthetic_message(HumanMessage(content="je déménage à Lyon")) is False

    def test_flagged_message_is_synthetic(self):
        assert is_synthetic_message(_synthetic("[USER REFUSAL] ...")) is True

    def test_assistant_message_without_kwargs_is_not_synthetic(self):
        assert is_synthetic_message(AIMessage(content="ok")) is False

    def test_detection_does_not_read_the_text(self):
        """A user genuinely typing the scaffolding wording is still genuine."""
        assert is_synthetic_message(HumanMessage(content="[REFUS UTILISATEUR] blah")) is False


@pytest.mark.unit
class TestFindLastUserMessage:
    def test_returns_the_last_human_message(self):
        messages = [
            HumanMessage(content="first"),
            AIMessage(content="answer"),
            HumanMessage(content="second"),
        ]
        message, index = find_last_user_message(messages)
        assert message is not None
        assert message.content == "second"
        assert index == 2

    def test_skips_the_synthetic_refusal_scaffold(self):
        """The regression oracle for D3."""
        messages = [
            HumanMessage(content="envoie un mail à Marie, je déménage à Lyon"),
            AIMessage(content="draft ready"),
            _synthetic("[REFUS UTILISATEUR] ... IMPORTANT: ne mentionne aucun problème"),
        ]
        message, index = find_last_user_message(messages)
        assert message is not None
        assert message.content == "envoie un mail à Marie, je déménage à Lyon"
        assert index == 0

    def test_skips_several_consecutive_scaffolds(self):
        messages = [
            HumanMessage(content="real request"),
            _synthetic("scaffold one"),
            _synthetic("scaffold two"),
        ]
        message, _ = find_last_user_message(messages)
        assert message is not None
        assert message.content == "real request"

    def test_no_human_message_returns_none(self):
        message, index = find_last_user_message(
            [AIMessage(content="hi"), SystemMessage(content="s")]
        )
        assert message is None
        assert index == -1

    def test_only_synthetic_messages_returns_none(self):
        """Nothing genuine to analyse — extraction must not fall back to scaffolding."""
        message, index = find_last_user_message([_synthetic("scaffold")])
        assert message is None
        assert index == -1

    def test_empty_history_returns_none(self):
        message, index = find_last_user_message([])
        assert message is None
        assert index == -1


@pytest.mark.unit
class TestExtractorsHonourTheFlag:
    """All three extractors must share the helper — a fourth cannot forget it."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "src.domains.agents.services.memory_extractor",
            "src.domains.interests.services.extraction_service",
            "src.domains.journals.extraction_service",
        ],
    )
    def test_extractor_imports_the_shared_helpers(self, module_path: str):
        import importlib

        module = importlib.import_module(module_path)
        assert hasattr(module, "find_last_user_message")
        assert hasattr(module, "is_synthetic_message")

    def test_response_context_targets_the_same_message_as_the_extractors(self):
        """Otherwise the embedding is computed on one text and used for another.

        ``extract_last_user_message`` drives three decisions — the triviality
        verdict, the embedding that is paid for and cached, and the memory/journal
        context injected for the turn. Leaving it unfiltered while the extractors
        skip scaffolding desynchronized the embedding from what it embeds.
        """
        from src.domains.agents.services.response_context import extract_last_user_message

        state = {
            "messages": [
                HumanMessage(content="je déménage à Lyon"),
                AIMessage(content="draft ready"),
                _synthetic("[REFUS UTILISATEUR] IMPORTANT ne mentionne aucun problème"),
            ]
        }

        assert extract_last_user_message(state) == "je déménage à Lyon"

    def test_response_context_still_skips_empty_messages(self):
        """Pre-existing behaviour preserved."""
        from src.domains.agents.services.response_context import extract_last_user_message

        state = {
            "messages": [
                HumanMessage(content="real content"),
                HumanMessage(content=""),
            ]
        }

        assert extract_last_user_message(state) == "real content"

    def test_memory_context_formatter_drops_scaffolding(self):
        """Not the target, and not even context: the scaffolding never reaches the prompt."""
        from src.domains.agents.services.memory_extractor import _format_messages_for_extraction

        formatted = _format_messages_for_extraction(
            [
                HumanMessage(content="je déménage à Lyon"),
                _synthetic("[REFUS UTILISATEUR] IMPORTANT ne mentionne aucun problème technique"),
            ]
        )

        assert "je déménage à Lyon" in formatted
        assert "REFUS UTILISATEUR" not in formatted
