"""The workboard card of the briefing (ADR-276 on the dashboard).

What on the person's board needs them, as exact counts plus the first tickets
waiting on them. Hidden when the instance switched the workboard off — read at
call time, so a switch flipped after boot hides the card on the next load.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import get_args
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.briefing.constants import SECTION_NAMES, SECTION_WORKBOARD
from src.domains.briefing.exceptions import ConnectorNotConfiguredError
from src.domains.briefing.fetchers import fetch_workboard
from src.domains.briefing.schemas import (
    CardSection,
    CardStatus,
    RemindersData,
    WorkboardData,
    WorkboardTicketItem,
)
from src.domains.briefing.service import _has_content

NOW = datetime.now(UTC)


def _db_ctx() -> Callable[[], AbstractAsyncContextManager[MagicMock]]:
    @asynccontextmanager
    async def _ctx() -> AsyncIterator[MagicMock]:
        yield MagicMock()

    return _ctx


def _ticket(**over: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": uuid4(),
        "title": "Book the venue",
        "status": "waiting",
        "due_at": None,
    }
    values.update(over)
    return SimpleNamespace(**values)


def _figures(
    *,
    needs_me: int = 0,
    held_by_lia: int = 0,
    overdue: int = 0,
    open_total: int = 0,
    first: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    """The shape of ``AttentionFigures``, with duck-typed tickets."""
    return SimpleNamespace(
        needs_me=needs_me,
        held_by_lia=held_by_lia,
        overdue=overdue,
        open_total=open_total,
        needs_me_first=first or [],
    )


@pytest.mark.unit
class TestFetchWorkboard:
    async def test_switched_off_hides_the_card_without_reading_the_board(self) -> None:
        read = AsyncMock()
        with (
            patch(
                "src.domains.briefing.fetchers.is_capability_enabled",
                AsyncMock(return_value=False),
            ),
            patch("src.domains.briefing.fetchers.read_attention", read),
            patch("src.domains.briefing.fetchers.get_db_context", new=_db_ctx()),
        ):
            with pytest.raises(ConnectorNotConfiguredError):
                await fetch_workboard(user_id=uuid4())
        read.assert_not_called()

    async def test_the_counts_are_the_aggregates_never_the_page_length(self) -> None:
        late = _ticket(title="Pay the invoice", status="todo", due_at=NOW - timedelta(days=1))
        waiting = _ticket(title="Answer LIA", status="waiting", due_at=NOW + timedelta(days=2))
        read = AsyncMock(
            return_value=_figures(
                needs_me=7, held_by_lia=2, overdue=4, open_total=12, first=[late, waiting]
            )
        )
        with (
            patch(
                "src.domains.briefing.fetchers.is_capability_enabled",
                AsyncMock(return_value=True),
            ),
            patch("src.domains.briefing.fetchers.read_attention", read),
            patch("src.domains.briefing.fetchers.get_db_context", new=_db_ctx()),
        ):
            data = await fetch_workboard(user_id=uuid4())

        assert (data.needs_me, data.held_by_lia, data.overdue, data.open_total) == (7, 2, 4, 12)
        assert [item.title for item in data.items] == ["Pay the invoice", "Answer LIA"]
        assert [item.overdue for item in data.items] == [True, False]
        assert data.items[0].id == str(late.id)
        # The page size is the published setting, never a number typed here.
        assert read.await_args is not None
        assert read.await_args.kwargs["limit"] == settings.briefing_max_workboard_items

    async def test_a_closed_ticket_past_its_date_is_not_late(self) -> None:
        done = _ticket(status="done", due_at=NOW - timedelta(days=3))
        read = AsyncMock(return_value=_figures(needs_me=1, open_total=0, first=[done]))
        with (
            patch(
                "src.domains.briefing.fetchers.is_capability_enabled",
                AsyncMock(return_value=True),
            ),
            patch("src.domains.briefing.fetchers.read_attention", read),
            patch("src.domains.briefing.fetchers.get_db_context", new=_db_ctx()),
        ):
            data = await fetch_workboard(user_id=uuid4())
        assert data.items[0].overdue is False


@pytest.mark.unit
class TestWorkboardCardStatus:
    def test_a_board_with_no_open_ticket_is_the_empty_state(self) -> None:
        assert (
            _has_content(WorkboardData(needs_me=0, held_by_lia=0, overdue=0, open_total=0)) is False
        )

    def test_open_tickets_with_nothing_waiting_still_have_something_to_say(self) -> None:
        assert (
            _has_content(WorkboardData(needs_me=0, held_by_lia=3, overdue=0, open_total=3)) is True
        )

    def test_the_section_is_declared_everywhere_a_section_must_be(self) -> None:
        from src.domains.briefing.preferences import sanitize_briefing_preferences
        from src.domains.briefing.schemas import CardsBundle, RefreshSectionLiteral

        assert SECTION_WORKBOARD in SECTION_NAMES
        assert SECTION_WORKBOARD in CardsBundle.model_fields
        assert SECTION_WORKBOARD in get_args(RefreshSectionLiteral)
        # An account whose preferences predate the card gets it, visible, last.
        stored = {"hidden": [], "order": [n for n in SECTION_NAMES if n != SECTION_WORKBOARD]}
        prefs = sanitize_briefing_preferences(stored)
        assert prefs.order[-1] == SECTION_WORKBOARD
        assert SECTION_WORKBOARD not in prefs.hidden


@pytest.mark.unit
class TestTheCachedPayloadReadsBackAsItself:
    """The section payload is an untagged union read back from Redis."""

    @pytest.mark.parametrize(
        "items",
        [
            [],
            [WorkboardTicketItem(id="t1", title="x", status="waiting", overdue=False)],
        ],
    )
    def test_round_trip(self, items: list[WorkboardTicketItem]) -> None:
        section = CardSection(
            status=CardStatus.OK,
            data=WorkboardData(needs_me=1, held_by_lia=0, overdue=0, open_total=1, items=items),
            generated_at=NOW,
        )
        restored = CardSection.model_validate_json(section.model_dump_json())
        # An empty `items` list would ALSO validate as RemindersData; the
        # union must keep the richer match.
        assert isinstance(restored.data, WorkboardData)
        assert not isinstance(restored.data, RemindersData)
        assert restored.data == section.data
