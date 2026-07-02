"""Unit tests for sender identity injection in DraftModificationService.

The modification prompt must carry the user's (signatory's) name so
instructions like "sign with my name" resolve to the real name instead of
a placeholder or a hallucinated one.
"""

from unittest.mock import patch

from src.domains.agents.services.hitl.draft_modifier import DraftModificationService


def _make_service() -> DraftModificationService:
    with patch("src.domains.agents.services.hitl.draft_modifier.get_llm"):
        return DraftModificationService()


class TestSenderInfoInjection:
    """{sender_info} placeholder resolution in the modification prompt."""

    def test_sender_name_injected_in_system_prompt(self):
        service = _make_service()

        prompt = service._build_modification_prompt(
            original_draft={"to": "a@b.com", "subject": "Hi", "body": "Hello"},
            instructions="signe avec mon prénom",
            draft_type="email",
            content_fields=["to", "cc", "bcc", "subject", "body"],
            user_language="fr",
            sender_name="Jérôme",
        )

        system_content = prompt[0]["content"]
        assert "SENDER (the user writing this): Jérôme" in system_content
        assert "{sender_info}" not in system_content

    def test_unknown_sender_leaves_no_placeholder(self):
        service = _make_service()

        prompt = service._build_modification_prompt(
            original_draft={"to": "a@b.com", "subject": "Hi", "body": "Hello"},
            instructions="make it shorter",
            draft_type="email",
            content_fields=["to", "cc", "bcc", "subject", "body"],
            user_language="fr",
            sender_name=None,
        )

        system_content = prompt[0]["content"]
        assert "SENDER (the user writing this)" not in system_content
        assert "{sender_info}" not in system_content
