"""Vacation responder draft chain (lot I, 2026-08).

Setting the Gmail vacation responder is a WRITE on the user's mailbox: it
goes through the full HITL draft flow (preview → confirm → execute), like
every other write in LIA.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.preview_renderer import _render_vacation_responder
from src.domains.agents.tools.gmail_settings_tools import execute_vacation_responder_draft

pytestmark = pytest.mark.unit

_DRAFT_CONTENT: dict[str, Any] = {
    "enable": True,
    "subject": "Absent jusqu'au 30/08",
    "body": "Je suis en congés, je répondrai à mon retour.",
    "start_date": "2026-08-24",
    "end_date": "2026-08-30",
    "user_language": "fr",
}


class TestDraftTypeWiring:
    def test_vacation_responder_draft_type_exists(self) -> None:
        assert DraftType.VACATION_RESPONDER.value == "vacation_responder"


class TestPreview:
    def test_enable_preview_shows_subject_message_and_dates(self) -> None:
        labels = get_draft_preview_labels("fr")
        lines = _render_vacation_responder(dict(_DRAFT_CONTENT), labels, lambda s: s or "")
        joined = "\n".join(lines)
        assert "Absent jusqu'au 30/08" in joined
        assert "Je suis en congés" in joined
        assert "2026-08-24" in joined

    def test_disable_preview_states_deactivation(self) -> None:
        labels = get_draft_preview_labels("fr")
        lines = _render_vacation_responder(
            {"enable": False, "user_language": "fr"}, labels, lambda s: s or ""
        )
        assert any("désactiv" in line.lower() for line in lines)


class TestExecutor:
    async def _execute(self, draft_content: dict[str, Any]) -> MagicMock:
        client = MagicMock()
        client.update_vacation = AsyncMock(return_value={"enableAutoReply": True})
        service = MagicMock()
        service.get_connector_credentials = AsyncMock(return_value=MagicMock())
        deps = MagicMock()
        deps.get_connector_service = AsyncMock(return_value=service)
        with patch(
            "src.domains.agents.tools.gmail_settings_tools.GoogleGmailSettingsClient",
            return_value=client,
        ):
            result = await execute_vacation_responder_draft(draft_content, uuid4(), deps)
        assert result["success"] is True
        return client

    async def test_enable_passes_settings_with_epoch_millis(self) -> None:
        client = await self._execute(dict(_DRAFT_CONTENT))
        kwargs = client.update_vacation.call_args.kwargs
        assert kwargs["enable"] is True
        assert kwargs["subject"] == "Absent jusqu'au 30/08"
        # Dates become epoch milliseconds (Gmail contract); end is EXCLUSIVE
        # end-of-day so the responder covers the whole last day.
        assert isinstance(kwargs["start_time_ms"], int)
        assert isinstance(kwargs["end_time_ms"], int)
        assert kwargs["end_time_ms"] > kwargs["start_time_ms"]

    async def test_disable_sends_no_times(self) -> None:
        client = await self._execute({"enable": False, "user_language": "fr"})
        kwargs = client.update_vacation.call_args.kwargs
        assert kwargs["enable"] is False
        assert kwargs.get("start_time_ms") is None
        assert kwargs.get("end_time_ms") is None
