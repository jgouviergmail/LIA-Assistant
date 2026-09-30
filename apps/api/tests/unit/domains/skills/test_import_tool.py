"""Tests for the ``import_user_skill`` chat tool (ADR-327: it PROPOSES).

Covers the tool-level contract that wraps the proposal service:
- ``files`` coercion (dict, JSON string, invalid)
- feature-flag gating
- a validated package is proposed under the conversation's answer — never
  installed — and the model is told that nothing is installed yet
- a package the import checks refuse comes back with their reason
- a cache that fails offers nothing, and says so

The proposal service is unit-tested in ``test_proposal_service.py``; here it is
mocked so the tool wiring is what's under test.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from langchain.tools import ToolRuntime

from src.core.exceptions import ValidationError
from src.domains.skills.proposals import SkillProposal
from src.domains.skills.tools import _coerce_files, import_user_skill
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

_USER = uuid4()


class TestCoerceFiles:
    def test_dict_passthrough(self) -> None:
        files, err = _coerce_files({"SKILL.md": "x"})
        assert err is None
        assert files == {"SKILL.md": "x"}

    def test_json_string_parsed(self) -> None:
        files, err = _coerce_files('{"SKILL.md": "x"}')
        assert err is None
        assert files == {"SKILL.md": "x"}

    def test_none_rejected(self) -> None:
        files, err = _coerce_files(None)
        assert files is None
        assert err is not None
        assert err.error_code == "INVALID_INPUT"

    def test_invalid_json_rejected(self) -> None:
        files, err = _coerce_files("{not-json}")
        assert files is None
        assert err is not None
        assert err.error_code == "INVALID_INPUT"

    def test_json_non_object_rejected(self) -> None:
        files, err = _coerce_files("[1, 2]")
        assert files is None
        assert err is not None
        assert err.error_code == "INVALID_INPUT"

    def test_non_string_values_stringified(self) -> None:
        files, err = _coerce_files({"SKILL.md": 123})
        assert err is None
        assert files == {"SKILL.md": "123"}


_VALID_SKILL_MD = """---
name: chat-skill
description: >
  Generates something useful, purely for the purposes of this test.
category: test
priority: 50
---

# Chat Skill

## Instructions
1. Do the thing.
"""


def _runtime(conversation_id: str = "thread-123") -> ToolRuntime:
    """A runtime carrying the identity on its typed context (ADR-231)."""
    return make_tool_runtime(
        user_id=_USER if isinstance(_USER, UUID) else UUID(str(_USER)),
        thread_id="thread-123",
        conversation_id=conversation_id,
        store=MagicMock(),
    )


def _proposal() -> SkillProposal:
    return SkillProposal(
        id="c" * 32,
        owner_id=str(_USER),
        name="chat-skill",
        description="Generates something useful.",
        files={"SKILL.md": _VALID_SKILL_MD},
        sizes={"SKILL.md": len(_VALID_SKILL_MD)},
        created_at="2026-09-30T10:00:00+00:00",
        expires_at="2026-10-01T10:00:00+00:00",
        replaces=None,
        changes=None,
    )


class TestImportUserSkillTool:
    @pytest.mark.asyncio
    async def test_feature_flag_disabled_returns_failure(self) -> None:
        settings = MagicMock(skills_chat_import_enabled=False)
        with patch("src.core.config.get_settings", return_value=settings):
            result = await import_user_skill.coroutine(files={"SKILL.md": "x"}, runtime=_runtime())
        assert result.success is False
        assert result.error_code == "FEATURE_DISABLED"

    @pytest.mark.asyncio
    async def test_a_valid_package_is_proposed_never_installed(self) -> None:
        settings = MagicMock(skills_chat_import_enabled=True)
        propose = AsyncMock(return_value=(_proposal(), 0))
        with (
            patch("src.core.config.get_settings", return_value=settings),
            patch("src.domains.skills.proposal_service.propose", propose),
        ):
            result = await import_user_skill.coroutine(
                files={"SKILL.md": _VALID_SKILL_MD}, runtime=_runtime()
            )

        assert result.success is True
        assert result.metadata["proposal_id"] == "c" * 32
        assert result.metadata["replaces"] is False
        assert "NOTHING is installed" in result.message
        assert "never say the skill is installed" in result.message
        propose.assert_awaited_once_with(
            {"SKILL.md": _VALID_SKILL_MD}, owner_id=_USER, conversation_id="thread-123"
        )

    @pytest.mark.asyncio
    async def test_a_package_the_checks_refuse_comes_back_with_the_reason(self) -> None:
        settings = MagicMock(skills_chat_import_enabled=True)
        propose = AsyncMock(side_effect=ValidationError(detail="bad name"))
        with (
            patch("src.core.config.get_settings", return_value=settings),
            patch("src.domains.skills.proposal_service.propose", propose),
        ):
            result = await import_user_skill.coroutine(
                files={"SKILL.md": _VALID_SKILL_MD}, runtime=_runtime()
            )

        assert result.success is False
        assert result.error_code == "IMPORT_REJECTED"
        assert "bad name" in result.message

    @pytest.mark.asyncio
    async def test_a_failing_cache_offers_nothing(self) -> None:
        settings = MagicMock(skills_chat_import_enabled=True)
        propose = AsyncMock(side_effect=ConnectionError("down"))
        with (
            patch("src.core.config.get_settings", return_value=settings),
            patch("src.domains.skills.proposal_service.propose", propose),
        ):
            result = await import_user_skill.coroutine(
                files={"SKILL.md": _VALID_SKILL_MD}, runtime=_runtime()
            )

        assert result.success is False
        assert result.error_code == "DEPENDENCY_ERROR"
        assert "nothing was proposed" in result.message

    @pytest.mark.asyncio
    async def test_where_no_card_reaches_the_person_nothing_is_proposed(self) -> None:
        """A ticket run's rows stay out of the chat, a channel renders plain text:
        a card queued there would never be seen, and the model would announce it."""
        from src.domains.agents.api.run_origin import plain_surface_ctx

        settings = MagicMock(skills_chat_import_enabled=True)
        propose = AsyncMock()
        token = plain_surface_ctx.set(True)
        try:
            with (
                patch("src.core.config.get_settings", return_value=settings),
                patch("src.domains.skills.proposal_service.propose", propose),
            ):
                result = await import_user_skill.coroutine(
                    files={"SKILL.md": _VALID_SKILL_MD}, runtime=_runtime()
                )
        finally:
            plain_surface_ctx.reset(token)

        assert result.success is False
        assert result.error_code == "CONFIGURATION_ERROR"
        assert "chat" in result.message
        propose.assert_not_awaited()

    async def test_without_a_conversation_nothing_is_proposed(self) -> None:
        """A card needs an answer to sit under."""
        settings = MagicMock(skills_chat_import_enabled=True)
        propose = AsyncMock()
        with (
            patch("src.core.config.get_settings", return_value=settings),
            patch("src.domains.skills.proposal_service.propose", propose),
        ):
            result = await import_user_skill.coroutine(
                files={"SKILL.md": _VALID_SKILL_MD}, runtime=_runtime(conversation_id="")
            )

        assert result.success is False
        propose.assert_not_awaited()
