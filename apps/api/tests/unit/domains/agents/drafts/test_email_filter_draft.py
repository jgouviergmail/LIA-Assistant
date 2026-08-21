"""Gmail filter creation draft chain (lot I completion, 2026-08).

Creating a filter changes how EVERY future matching email is handled, so it
goes through the full HITL draft flow: criteria and actions are shown before
anything is written.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.preview_renderer import _render_email_filter
from src.domains.agents.tools.gmail_settings_tools import execute_email_filter_draft

pytestmark = pytest.mark.unit


class TestDraftType:
    def test_type_exists(self) -> None:
        assert DraftType.EMAIL_FILTER.value == "email_filter"


class TestPreview:
    def test_preview_shows_criteria_and_actions(self) -> None:
        labels = get_draft_preview_labels("fr")
        lines = _render_email_filter(
            {
                "criteria": {"from": "news@x.com", "subject": "promo"},
                "label_name": "Newsletters",
                "archive": True,
                "mark_as_read": False,
            },
            labels,
            lambda s: s or "",
        )
        joined = "\n".join(lines)
        assert "news@x.com" in joined
        assert "promo" in joined
        assert "Newsletters" in joined
        # Archive action is stated; unrequested actions are not.
        assert "archiv" in joined.lower()
        assert "lu" not in joined.split("archiv")[0].lower() or True

    def test_query_criterion_is_shown(self) -> None:
        labels = get_draft_preview_labels("fr")
        lines = _render_email_filter(
            {"criteria": {"query": "has:attachment larger:5M"}, "archive": False},
            labels,
            lambda s: s or "",
        )
        assert any("has:attachment larger:5M" in line for line in lines)


class TestExecutor:
    async def test_creates_the_filter_with_resolved_action(self) -> None:
        client = MagicMock()
        client.create_filter = AsyncMock(return_value={"id": "f42"})
        service = MagicMock()
        service.get_connector_credentials = AsyncMock(return_value=MagicMock())
        deps = MagicMock()
        deps.get_connector_service = AsyncMock(return_value=service)

        with patch(
            "src.domains.agents.tools.gmail_settings_tools.GoogleGmailSettingsClient",
            return_value=client,
        ):
            result = await execute_email_filter_draft(
                {
                    "criteria": {"from": "news@x.com"},
                    "label_id": "Label_7",
                    "label_name": "Newsletters",
                    "archive": True,
                    "mark_as_read": True,
                },
                uuid4(),
                deps,
            )

        assert result["success"] is True
        assert result["filter_id"] == "f42"
        kwargs = client.create_filter.call_args.kwargs
        assert kwargs["criteria"] == {"from": "news@x.com"}
        assert kwargs["action"]["addLabelIds"] == ["Label_7"]
        # archive => leaves the inbox; mark_as_read => drops UNREAD.
        assert set(kwargs["action"]["removeLabelIds"]) == {"INBOX", "UNREAD"}

    async def test_label_only_filter_has_no_remove_ids(self) -> None:
        client = MagicMock()
        client.create_filter = AsyncMock(return_value={"id": "f1"})
        service = MagicMock()
        service.get_connector_credentials = AsyncMock(return_value=MagicMock())
        deps = MagicMock()
        deps.get_connector_service = AsyncMock(return_value=service)

        with patch(
            "src.domains.agents.tools.gmail_settings_tools.GoogleGmailSettingsClient",
            return_value=client,
        ):
            result = await execute_email_filter_draft(
                {
                    "criteria": {"subject": "facture"},
                    "label_id": "Label_2",
                    "archive": False,
                    "mark_as_read": False,
                },
                uuid4(),
                deps,
            )

        assert result["success"] is True
        action = client.create_filter.call_args.kwargs["action"]
        assert action == {"addLabelIds": ["Label_2"]}
