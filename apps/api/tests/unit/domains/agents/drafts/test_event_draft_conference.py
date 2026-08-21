"""The add_conference flag must survive the whole draft chain (lot A, 2026-08).

Chain: create_event_tool → EventDraftInput (draft content) → HITL preview →
execute_event_draft → client.create_event → confirmation with the join link.
A field present on one side only is the recurring silent-loss bug the
round-trip rule exists for (CLAUDE.md, Registries & vocabulary).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.drafts.models import EventDraftInput
from src.domains.agents.drafts.preview_renderer import _render_event
from src.domains.agents.tools.calendar_draft_execution import execute_event_draft

pytestmark = pytest.mark.unit

_DRAFT_CONTENT: dict[str, Any] = {
    "summary": "Point avec Marc",
    "start_datetime": "2026-08-27T10:00:00",
    "end_datetime": "2026-08-27T10:30:00",
    "timezone": "Europe/Paris",
    "attendees": ["marc@example.com"],
}


class TestEventDraftInputCarriesTheFlag:
    def test_field_defaults_to_false_and_round_trips(self) -> None:
        draft = EventDraftInput(**_DRAFT_CONTENT, user_language="fr")
        assert draft.add_conference is False
        assert draft.model_dump()["add_conference"] is False

        with_conf = EventDraftInput(**_DRAFT_CONTENT, add_conference=True, user_language="fr")
        assert with_conf.model_dump()["add_conference"] is True
        assert with_conf.to_create_event_args()["add_conference"] is True


class TestPreviewShowsTheConference:
    def test_preview_line_present_when_flag_set(self) -> None:
        labels = get_draft_preview_labels("fr")
        lines = _render_event({**_DRAFT_CONTENT, "add_conference": True}, labels, lambda s: s or "")
        joined = "\n".join(lines)
        assert "Visioconférence" in joined

    def test_no_preview_line_without_flag(self) -> None:
        labels = get_draft_preview_labels("fr")
        lines = _render_event(dict(_DRAFT_CONTENT), labels, lambda s: s or "")
        assert "Visioconférence" not in "\n".join(lines)


class TestExecuteEventDraftPassesTheFlag:
    async def _execute(self, draft_content: dict[str, Any], create_result: dict[str, Any]) -> Any:
        client = MagicMock()
        client.create_event = AsyncMock(return_value=create_result)
        with (
            patch(
                "src.domains.connectors.provider_resolver.resolve_client_for_category",
                new=AsyncMock(return_value=(client, MagicMock())),
            ),
            patch(
                "src.domains.agents.tools.calendar_draft_execution._resolve_calendar_id",
                new=AsyncMock(return_value="primary"),
            ),
        ):
            result = await execute_event_draft(draft_content, uuid4(), MagicMock())
        return client, result

    async def test_flag_reaches_the_client_call(self) -> None:
        client, _ = await self._execute(
            {**_DRAFT_CONTENT, "add_conference": True},
            {"id": "evt-1", "hangoutLink": "https://meet.google.com/abc-defg-hij"},
        )
        assert client.create_event.call_args.kwargs["add_conference"] is True

    async def test_confirmation_carries_the_join_link(self) -> None:
        _, result = await self._execute(
            {**_DRAFT_CONTENT, "add_conference": True},
            {"id": "evt-1", "hangoutLink": "https://meet.google.com/abc-defg-hij"},
        )
        assert result["conference_link"] == "https://meet.google.com/abc-defg-hij"

    async def test_conference_link_falls_back_to_entry_points(self) -> None:
        """Teams events (Graph normalizer) have no hangoutLink shortcut on some
        paths — the video entry point is the canonical source."""
        _, result = await self._execute(
            {**_DRAFT_CONTENT, "add_conference": True},
            {
                "id": "evt-1",
                "conferenceData": {
                    "entryPoints": [
                        {"entryPointType": "phone", "uri": "tel:+331"},
                        {"entryPointType": "video", "uri": "https://teams.microsoft.com/j/1"},
                    ]
                },
            },
        )
        assert result["conference_link"] == "https://teams.microsoft.com/j/1"

    async def test_no_link_key_when_provider_created_none(self) -> None:
        """Meet creation can fail while the event succeeds — the confirmation
        must not invent a link (absence of exception is not delivery)."""
        _, result = await self._execute(
            {**_DRAFT_CONTENT, "add_conference": True},
            {"id": "evt-1"},
        )
        assert "conference_link" not in result

    async def test_flag_absent_defaults_to_false(self) -> None:
        client, _ = await self._execute(dict(_DRAFT_CONTENT), {"id": "evt-1"})
        assert client.create_event.call_args.kwargs["add_conference"] is False
