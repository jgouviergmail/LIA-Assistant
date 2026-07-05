"""The draft-modifier LLM scaffolding must be English (no inline French).

The versioned ``draft_modifier_prompt.txt`` is English and instructs the model to
``Respond in {user_language}`` — so the output language is already controlled.
The Python scaffolding fed into that prompt (context labels, the user-role
instruction) is LLM-facing and never shown to the end user; per
``core/i18n.py`` ("LLM prompts are NOT translated") it must be English, not
French. These tests pin that no French scaffolding remains.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.services.hitl.draft_modifier import DraftModificationService

pytestmark = [pytest.mark.unit]


def _service() -> DraftModificationService:
    with patch(
        "src.domains.agents.services.hitl.draft_modifier.get_llm",
        return_value=MagicMock(),
    ):
        return DraftModificationService()


def test_context_info_email_is_english() -> None:
    info = _service()._build_context_info(
        {"to": "a@b.com", "cc": "c@d.com", "subject": "Subject"}, "email"
    )
    assert "Current recipient" in info
    assert "Destinataire" not in info
    assert "actuel" not in info


def test_context_info_task_is_english() -> None:
    info = _service()._build_context_info({"title": "Buy milk"}, "task")
    assert info.startswith("Task:")
    assert "Tâche" not in info


def test_context_info_generic_is_english() -> None:
    assert _service()._build_context_info({}, "unknown_type") == "Generic draft"


def test_contact_context_info_is_english() -> None:
    info = _service()._build_contact_context_info(
        [{"name": "Jean", "emails": ["jean@example.com"]}]
    )
    assert "Contact email addresses" in info
    assert "Adresses email" not in info


def test_expected_fields_example_is_english() -> None:
    result = _service()._format_expected_fields(["body"])
    assert "modified content" in result
    assert "contenu modifié" not in result


def test_modification_user_message_is_english() -> None:
    messages = _service()._build_modification_prompt(
        original_draft={"to": "a@b.com"},
        instructions="change the recipient",
        draft_type="email",
        content_fields=["to"],
        user_language="de",
    )
    user_msg = next(m for m in messages if m["role"] == "user")
    assert user_msg["content"].startswith("Modify the draft")
    assert "Modifie" not in user_msg["content"]
