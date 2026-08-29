"""Tests for the ``import_user_skill`` chat tool.

Covers the tool-level contract that wraps :class:`SkillImportService`:
- ``files`` coercion (dict, JSON string, invalid)
- feature-flag gating
- success path (delegates to the service, returns a confirmation)
- rejection path (service raises → structured failure the LLM can act on)

The service itself is unit-tested in ``test_import_service.py``; here it is
mocked so the tool wiring is what's under test.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from langchain.tools import ToolRuntime

from src.core.exceptions import ValidationError
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


def _runtime() -> ToolRuntime:
    """A runtime carrying the identity on its typed context (ADR-231)."""
    return make_tool_runtime(
        user_id=_USER if isinstance(_USER, UUID) else UUID(str(_USER)),
        thread_id="thread-123",
        conversation_id="thread-123",
        store=MagicMock(),
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
    async def test_success_delegates_to_service(self) -> None:
        settings = MagicMock(skills_chat_import_enabled=True)
        svc = MagicMock()
        svc.import_files = AsyncMock(
            return_value={"name": "chat-skill", "scripts": [], "all_resources": ["references/n.md"]}
        )

        class _DummyCtx:
            async def __aenter__(self) -> MagicMock:
                return MagicMock()

            async def __aexit__(self, *a: object) -> None:
                return None

        with (
            patch("src.core.config.get_settings", return_value=settings),
            patch(
                "src.domains.skills.import_service.SkillImportService",
                return_value=svc,
            ),
            patch(
                "src.infrastructure.database.session.get_db_context",
                return_value=_DummyCtx(),
            ),
        ):
            result = await import_user_skill.coroutine(
                files={"SKILL.md": _VALID_SKILL_MD}, runtime=_runtime()
            )

        assert result.success is True
        assert result.metadata["skill_name"] == "chat-skill"
        assert result.metadata["resource_count"] == 1
        svc.import_files.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_service_rejection_becomes_structured_failure(self) -> None:
        settings = MagicMock(skills_chat_import_enabled=True)
        svc = MagicMock()
        svc.import_files = AsyncMock(side_effect=ValidationError(detail="bad name"))

        class _DummyCtx:
            async def __aenter__(self) -> MagicMock:
                return MagicMock()

            async def __aexit__(self, *a: object) -> None:
                return None

        with (
            patch("src.core.config.get_settings", return_value=settings),
            patch(
                "src.domains.skills.import_service.SkillImportService",
                return_value=svc,
            ),
            patch(
                "src.infrastructure.database.session.get_db_context",
                return_value=_DummyCtx(),
            ),
        ):
            result = await import_user_skill.coroutine(
                files={"SKILL.md": _VALID_SKILL_MD}, runtime=_runtime()
            )

        assert result.success is False
        assert result.error_code == "IMPORT_REJECTED"
        assert "bad name" in result.message
