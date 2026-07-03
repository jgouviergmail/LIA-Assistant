"""Pure unit tests for ConversationService metadata persistence semantics.

Regression coverage for the 2026-07 codebase audit (wave 1), fast-suite
counterpart of the DB round-trip test in test_conversations_service.py:
SQLAlchemy only persists a JSONB column when a NEW object is assigned, so
``update_last_user_message`` must never reassign the same (mutated) dict.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.conversations.service import ConversationService


@pytest.mark.unit
async def test_update_last_user_message_assigns_new_metadata_dict():
    """With preexisting metadata, the assigned dict must be a NEW object."""
    original_metadata = {"run_id": "abc123"}
    message = SimpleNamespace(
        content="original",
        message_metadata=original_metadata,
    )

    service = ConversationService()
    with patch("src.domains.conversations.service.ConversationRepository") as repo_cls:
        repo_cls.return_value.get_last_user_message = AsyncMock(return_value=message)

        updated = await service.update_last_user_message(
            conversation_id=uuid4(),
            new_content="reformulated",
            metadata_updates={"hitl_edit": True},
            db=MagicMock(),
        )

    assert updated is message
    # New object identity is what makes SQLAlchemy change detection fire
    assert message.message_metadata is not original_metadata
    # And the original dict must not have been mutated in place
    assert original_metadata == {"run_id": "abc123"}
    assert message.message_metadata == {
        "run_id": "abc123",
        "hitl_edit": True,
        "hitl_original_content": "original",
    }
