"""All-day events reach the assistant, end to end (ADR-369, owner decision D2).

The calendar clients gained ``all_day`` for the « Tools » section; the owner's
rule is that what the clients gain reaches the assistant in the same lot. The
model speaks INCLUSIVE days (« from the 3rd to the 5th »), the clients speak the
exclusive end they read: the tool converts once, the draft carries the client's
convention, and the card shows days — never « 00:00 → 00:00 », never a date a
timezone moved to the previous day.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.date_contract import InvertedPeriodError, UnreadableDateError
from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.calendar.catalogue_manifests import (
    create_event_catalogue_manifest,
    update_event_catalogue_manifest,
)
from src.domains.agents.calendar.event_times import (
    ALL_DAY_DESCRIPTION,
    ALL_DAY_UPDATE_DESCRIPTION,
    all_day_bounds,
    updated_bounds,
)
from src.domains.agents.drafts.card_spec import to_markdown_lines
from src.domains.agents.drafts.dates import draft_datetime_formatter
from src.domains.agents.drafts.models import EventDraftInput, EventUpdateDraftInput
from src.domains.agents.drafts.preview_renderer import _render_event
from src.domains.agents.tools.base import _current_runtime
from src.domains.agents.tools.calendar_draft_execution import (
    execute_event_draft,
    execute_event_update_draft,
)
from src.domains.agents.tools.calendar_tools import (
    CreateEventDraftTool,
    UpdateEventDraftTool,
    create_event_tool,
    update_event_tool,
)
from src.domains.agents.tools.exceptions import ToolValidationError
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

#: An all-day event the way every client reads one: first day, EXCLUSIVE end.
_CONGRESS: dict[str, Any] = {
    "id": "e1",
    "summary": "Congress",
    "start": {"date": "2026-11-03"},
    "end": {"date": "2026-11-06"},
}
_MEETING: dict[str, Any] = {
    "id": "e2",
    "summary": "Review",
    "start": {"dateTime": "2026-11-03T10:00:00+00:00"},
    "end": {"dateTime": "2026-11-03T11:00:00+00:00"},
}

_ALL_DAY: dict[str, Any] = {
    "summary": "Congress",
    "start_datetime": "2026-11-03",
    "end_datetime": "2026-11-06",
    "timezone": "UTC",
    "all_day": True,
}


class TestTheToolConvertsOnce:
    def test_the_last_day_named_becomes_the_exclusive_end(self) -> None:
        assert all_day_bounds("2026-11-03", "2026-11-05") == ("2026-11-03", "2026-11-06")

    def test_one_day_needs_no_end(self) -> None:
        assert all_day_bounds("2026-11-03T00:00:00", None) == ("2026-11-03", "2026-11-04")

    def test_a_last_day_before_the_first_is_refused(self) -> None:
        with pytest.raises(ValueError):
            all_day_bounds("2026-11-05", "2026-11-03")


class TestTheContractIsPublishedToBothReaders:
    @pytest.mark.parametrize(
        ("manifest", "tool", "wording"),
        [
            (create_event_catalogue_manifest, create_event_tool, ALL_DAY_DESCRIPTION),
            (update_event_catalogue_manifest, update_event_tool, ALL_DAY_UPDATE_DESCRIPTION),
        ],
    )
    def test_manifest_and_schema_read_one_description(
        self, manifest: Any, tool: Any, wording: str
    ) -> None:
        parameter = next(p for p in manifest.parameters if p.name == "all_day")
        assert parameter.description == wording
        schema = tool.tool_call_schema.model_json_schema()
        assert schema["properties"]["all_day"]["description"] == wording


class TestTheDraftCarriesTheShape:
    def test_the_create_draft_round_trips_all_day(self) -> None:
        draft = EventDraftInput(**_ALL_DAY, user_language="en")
        assert draft.to_create_event_args()["all_day"] is True
        assert EventDraftInput.model_validate(draft.model_dump()) == draft

    def test_the_update_draft_keeps_none_as_keep_the_shape(self) -> None:
        draft = EventUpdateDraftInput(event_id="e1", user_language="en")
        assert draft.all_day is None
        assert EventUpdateDraftInput.model_validate(draft.model_dump()) == draft


class TestTheExecutorPassesIt:
    async def _client(self, method: str) -> Any:
        client = MagicMock()
        setattr(client, method, AsyncMock(return_value={"id": "evt-1"}))
        return client

    async def test_create_reaches_the_client_with_its_dates(self) -> None:
        client = await self._client("create_event")
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
            await execute_event_draft(dict(_ALL_DAY), uuid4(), MagicMock())
        bounds = client.create_event.call_args.kwargs["bounds"]
        # Days, the end exclusive: no time of day, so no zone can move them.
        assert (bounds.first, bounds.after_last) == (date(2026, 11, 3), date(2026, 11, 6))

    async def test_update_without_a_switch_keeps_the_shape(self) -> None:
        client = await self._client("update_event")
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
            await execute_event_update_draft(
                {"event_id": "e1", "summary": "x", "timezone": "UTC"}, uuid4(), MagicMock()
            )
        assert client.update_event.call_args.kwargs["bounds"] is None

    async def test_a_confirmed_update_tells_the_attendees_as_a_deletion_does(self) -> None:
        """Parity (ADR-369, D2): Graph tells attendees of every change; Google told
        nobody of an update the assistant made, though its deletions tell everyone."""
        client = await self._client("update_event")
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
            await execute_event_update_draft(
                {"event_id": "e1", "summary": "x", "timezone": "UTC"}, uuid4(), MagicMock()
            )
        assert client.update_event.call_args.kwargs["send_updates"] == "all"


class TestTheCardShowsDays:
    def _card(self, content: dict[str, Any], language: str, timezone: str = "UTC") -> str:
        labels = get_draft_preview_labels(language)
        lines = _render_event(content, labels, draft_datetime_formatter(timezone, language))
        return "\n".join(to_markdown_lines(lines, labels["separator"]))

    def test_a_three_day_event_shows_its_first_and_last_days(self) -> None:
        card = self._card(dict(_ALL_DAY), "en")
        assert "03 November 2026" in card
        assert "05 November 2026" in card, "the LAST day, not the exclusive end"
        assert "06 November" not in card
        assert "00:00" not in card
        assert get_draft_preview_labels("en")["all_day"] in card

    def test_a_date_is_never_moved_by_a_timezone(self) -> None:
        """Midnight UTC is the previous evening in New York; a date is not an instant."""
        card = self._card(dict(_ALL_DAY), "fr", timezone="America/New_York")
        assert "03 novembre 2026" in card
        assert "02 novembre" not in card

    def test_a_one_day_event_shows_one_day(self) -> None:
        card = self._card({**_ALL_DAY, "end_datetime": "2026-11-04"}, "en")
        assert card.count("November 2026") == 1


class TestAnUpdateSpeaksDaysToo:
    """The model names an all-day event's LAST day whether it creates or moves it."""

    def test_an_all_day_event_extended_without_the_flag_keeps_its_days(self) -> None:
        """« Extend the congress to the 7th »: read as the exclusive end, it lost a day."""
        assert updated_bounds(None, "2026-11-07", "UTC", None, _CONGRESS) == (
            "2026-11-03",
            "2026-11-08",
            True,
        )

    def test_a_day_not_given_is_the_events_own(self) -> None:
        assert updated_bounds("2026-11-02", None, "UTC", True, _CONGRESS) == (
            "2026-11-02",
            "2026-11-06",
            True,
        )

    def test_a_timed_event_turned_all_day_on_one_day(self) -> None:
        assert updated_bounds("2026-11-04", None, "UTC", True, _MEETING) == (
            "2026-11-04",
            "2026-11-05",
            True,
        )

    def test_a_timed_event_keeps_its_shape(self) -> None:
        start, end, all_day = updated_bounds(
            "2026-11-03T14:00:00", None, "Europe/Paris", None, _MEETING
        )
        assert start is not None and start.startswith("2026-11-03T14:00")
        assert (end, all_day) == (None, None)

    def test_turning_timed_needs_both_times(self) -> None:
        with pytest.raises(ValueError, match="end_datetime"):
            updated_bounds("2026-11-03T10:00", None, "UTC", False, _CONGRESS)

    def test_turning_all_day_needs_a_first_day(self) -> None:
        with pytest.raises(ValueError, match="start_datetime"):
            updated_bounds(None, None, "UTC", True, _MEETING)

    def test_an_unreadable_day_is_named_never_guessed(self) -> None:
        with pytest.raises(UnreadableDateError) as caught:
            updated_bounds("tomorrow", None, "UTC", True, _MEETING)
        assert caught.value.reference == "tomorrow"

    def test_a_move_past_its_last_day_is_refused_not_guessed(self) -> None:
        with pytest.raises(InvertedPeriodError):
            updated_bounds("2026-11-10", None, "UTC", None, _CONGRESS)


class TestTheToolsRefuseWhatTheyCannotRead:
    async def _prepare(self, tool: Any, client: Any, **arguments: Any) -> dict[str, Any]:
        token = _current_runtime.set(
            make_tool_runtime(user_id=uuid4(), thread_id="t", store=MagicMock())
        )
        try:
            return dict(await tool.execute_api_call(client, uuid4(), **arguments))
        finally:
            _current_runtime.reset(token)

    def _client(self, event: dict[str, Any]) -> Any:
        client = MagicMock()
        client.get_event = AsyncMock(return_value=deepcopy(event))
        return client

    async def test_the_update_reads_the_event_before_its_days(self) -> None:
        draft = await self._prepare(
            UpdateEventDraftTool(),
            self._client(_CONGRESS),
            event_id="e1",
            calendar_id="primary",
            timezone="UTC",
            end_datetime="2026-11-07",
        )
        assert (draft["start_datetime"], draft["end_datetime"], draft["all_day"]) == (
            "2026-11-03",
            "2026-11-08",
            True,
        )

    async def test_an_incomplete_switch_is_a_typed_refusal(self) -> None:
        with pytest.raises(ToolValidationError, match="end_datetime"):
            await self._prepare(
                UpdateEventDraftTool(),
                self._client(_MEETING),
                event_id="e2",
                calendar_id="primary",
                timezone="UTC",
                start_datetime="2026-11-04T09:00",
                all_day=False,
            )

    async def test_an_unreadable_day_on_create_names_today(self) -> None:
        with pytest.raises(ToolValidationError, match="today is"):
            await self._prepare(
                CreateEventDraftTool(),
                MagicMock(),
                summary="Congress",
                start_datetime="tomorrow",
                end_datetime="tomorrow",
                timezone="UTC",
                all_day=True,
            )
