"""Draft plumbing for chat-created scheduled actions (P11, Lot 3, ADR-140).

Pins the SCHEDULED_ACTION draft type across its four mandatory surfaces:
enum, display registry (boot-asserted), i18n noun/verb ×6, executor
registration.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.drafts.display import (
    DRAFT_DISPLAY_REGISTRY,
    assert_registry_completeness,
)
from src.domains.agents.drafts.models import DraftType

# Backend-canonical language keys (zh-CN, never zh — CLAUDE.md i18n rule).
SUPPORTED = ("fr", "en", "es", "de", "it", "zh-CN")


@pytest.mark.unit
class TestScheduledActionDraftType:
    def test_enum_value(self):
        assert DraftType.SCHEDULED_ACTION.value == "scheduled_action"

    def test_display_registry_entry_shape(self):
        config = DRAFT_DISPLAY_REGISTRY[DraftType.SCHEDULED_ACTION]
        assert "title" in config.item_label_fields
        detail_keys = {f.content_key for f in config.detail_fields}
        assert {"title", "action_prompt"} <= detail_keys

    def test_registry_completeness_still_boots(self):
        assert_registry_completeness()


@pytest.mark.unit
class TestScheduledActionDraftI18n:
    def test_noun_exists_in_all_languages(self):
        from src.core.i18n_drafts import DRAFT_RESULT_NOUNS

        for lang in SUPPORTED:
            assert "automation" in DRAFT_RESULT_NOUNS[lang], f"missing noun for '{lang}'"
            assert DRAFT_RESULT_NOUNS[lang]["automation"]["singular"], lang

    def test_verb_exists_in_all_languages(self):
        from src.core.i18n_drafts import DRAFT_RESULT_VERBS_PAST

        for lang in SUPPORTED:
            assert "scheduled" in DRAFT_RESULT_VERBS_PAST[lang], f"missing verb for '{lang}'"


@pytest.mark.unit
class TestScheduledActionDraftExecutor:
    async def test_executor_creates_action_via_service(self):
        from contextlib import asynccontextmanager

        from src.domains.agents.tools.automation_tools import (
            execute_scheduled_action_draft,
        )

        service = MagicMock()
        created = MagicMock()
        created.id = uuid4()
        created.title = "Revue de presse IA"
        service.create = AsyncMock(return_value=created)

        @asynccontextmanager
        async def _db_ctx():
            session = MagicMock()
            session.commit = AsyncMock()
            yield session

        draft_content = {
            "title": "Revue de presse IA",
            "action_prompt": "Fais-moi une revue de presse IA",
            "days_of_week": [1, 2, 3, 4, 5],
            "trigger_hour": 8,
            "trigger_minute": 0,
            "user_timezone": "Europe/Paris",
        }

        with (
            patch(
                "src.domains.scheduled_actions.service.ScheduledActionService",
                return_value=service,
            ),
            patch(
                "src.domains.agents.tools.automation_tools.get_db_context",
                new=_db_ctx,
            ),
        ):
            result = await execute_scheduled_action_draft(draft_content, uuid4(), MagicMock())

        assert result["success"] is True
        assert result["title"] == "Revue de presse IA"
        create_kwargs = service.create.await_args.kwargs
        assert create_kwargs["data"].trigger_hour == 8
        assert create_kwargs["data"].days_of_week == [1, 2, 3, 4, 5]
        assert create_kwargs["user_timezone"] == "Europe/Paris"

    def test_executor_is_registered_for_draft_type(self):
        from src.domains.agents.services import draft_executor

        draft_executor._ensure_executors_registered()
        assert DraftType.SCHEDULED_ACTION.value in draft_executor._EXECUTOR_REGISTRY
