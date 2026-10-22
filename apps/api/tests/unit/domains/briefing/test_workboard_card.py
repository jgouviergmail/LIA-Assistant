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
    held_by_me: int = 0,
    held_by_lia: int = 0,
    held_by_peers: int = 0,
    overdue: int = 0,
    open_total: int = 0,
    first: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    """The shape of ``AttentionFigures``, with duck-typed tickets."""
    return SimpleNamespace(
        needs_me=needs_me,
        held_by_me=held_by_me,
        held_by_lia=held_by_lia,
        held_by_peers=held_by_peers,
        overdue=overdue,
        open_total=open_total,
        needs_me_first=first or [],
        previews={
            "needs_me": (first or [])[:2],
            "held_by_me": [],
            "held_by_lia": [],
            "held_by_peers": [],
            "overdue": [],
            "open_total": [],
        },
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
                needs_me=7,
                held_by_me=5,
                held_by_lia=2,
                held_by_peers=9,
                overdue=4,
                open_total=12,
                first=[late, waiting],
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

        assert (
            data.needs_me,
            data.held_by_me,
            data.held_by_lia,
            data.held_by_peers,
            data.overdue,
            data.open_total,
        ) == (7, 5, 2, 9, 4, 12)
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


@pytest.mark.unit
class TestPeerCountCacheCompatibility:
    def test_a_legacy_cached_count_is_unknown_rather_than_zero(self) -> None:
        restored = WorkboardData.model_validate(
            {"needs_me": 5, "held_by_lia": 2, "overdue": 3, "open_total": 12, "items": []}
        )
        assert restored.held_by_peers is None

    @pytest.mark.parametrize("count", [0, 9])
    def test_an_exact_peer_count_survives_the_section_cache(self, count: int) -> None:
        original = CardSection(
            status=CardStatus.OK,
            data=WorkboardData(
                needs_me=5, held_by_lia=2, held_by_peers=count, overdue=3, open_total=12
            ),
            generated_at=NOW,
        )
        restored = CardSection.model_validate_json(original.model_dump_json())
        assert isinstance(restored.data, WorkboardData)
        assert restored.data.held_by_peers == count

    def test_negative_peer_counts_are_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="held_by_peers"):
            WorkboardData(needs_me=0, held_by_lia=0, held_by_peers=-1, overdue=0, open_total=0)


@pytest.mark.unit
class TestGroupedPreviewContract:
    @pytest.mark.parametrize("preview_field", [{}, {"previews": None}])
    def test_old_cache_does_not_claim_known_empty_groups(
        self, preview_field: dict[str, object]
    ) -> None:
        data = WorkboardData.model_validate(
            {"needs_me": 0, "held_by_lia": 0, "overdue": 0, "open_total": 0, **preview_field}
        )
        assert data.model_dump()["previews"] is None
        assert data.held_by_me is None

    def test_a_cache_predating_my_tickets_claims_no_count_of_them(self) -> None:
        # Grouped previews cached before « my tickets » existed: the group reads
        # empty and its count reads unknown — the card shows no tile rather than
        # a zero nobody counted.
        groups = {
            key: [] for key in ("needs_me", "held_by_lia", "held_by_peers", "overdue", "open_total")
        }
        data = WorkboardData.model_validate(
            {"needs_me": 0, "held_by_lia": 0, "overdue": 0, "open_total": 0, "previews": groups}
        )
        assert data.held_by_me is None
        assert data.previews is not None and data.previews.held_by_me == []

    def test_known_empty_groups_survive_the_section_cache(self) -> None:
        groups = {
            key: []
            for key in (
                "needs_me",
                "held_by_me",
                "held_by_lia",
                "held_by_peers",
                "overdue",
                "open_total",
            )
        }
        data = WorkboardData.model_validate(
            {"needs_me": 0, "held_by_lia": 0, "overdue": 0, "open_total": 0, "previews": groups}
        )
        section = CardSection(status=CardStatus.OK, data=data, generated_at=NOW)
        restored = CardSection.model_validate_json(section.model_dump_json())
        assert isinstance(restored.data, WorkboardData)
        assert restored.data.model_dump()["previews"] == groups

    def test_a_preview_cannot_claim_to_be_an_unbounded_ticket_page(self) -> None:
        from pydantic import ValidationError

        groups = {
            key: [] for key in ("needs_me", "held_by_lia", "held_by_peers", "overdue", "open_total")
        }
        groups["needs_me"] = [
            {"id": str(index), "title": "Ticket", "status": "waiting", "overdue": False}
            for index in range(3)
        ]
        with pytest.raises(ValidationError, match="needs_me"):
            WorkboardData.model_validate(
                {"needs_me": 3, "held_by_lia": 0, "overdue": 0, "open_total": 3, "previews": groups}
            )

    async def test_fetcher_projects_each_set_and_keeps_the_legacy_page_separate(self) -> None:
        first = _ticket(title="Needs me")
        peer = _ticket(title="Peer held")
        figures = _figures(needs_me=1, held_by_peers=1, open_total=2, first=[first])
        figures.previews = {
            "needs_me": [first],
            "held_by_lia": [],
            "held_by_peers": [peer],
            "overdue": [],
            "open_total": [first, peer],
        }
        with (
            patch(
                "src.domains.briefing.fetchers.is_capability_enabled", AsyncMock(return_value=True)
            ),
            patch("src.domains.briefing.fetchers.read_attention", AsyncMock(return_value=figures)),
            patch("src.domains.briefing.fetchers.get_db_context", new=_db_ctx()),
        ):
            data = await fetch_workboard(user_id=uuid4())
        assert [item.title for item in data.items] == ["Needs me"]
        assert data.model_dump()["previews"]["held_by_peers"][0]["title"] == "Peer held"
        assert data.model_dump()["previews"]["held_by_lia"] == []


@pytest.mark.unit
@pytest.mark.parametrize("verbose", [False, True])
def test_grouped_ticket_titles_never_enter_the_greeting_or_synthesis_prompt(verbose: bool) -> None:
    from src.domains.briefing.llm import _summarize_cards_for_llm
    from src.domains.briefing.schemas import CardsBundle

    ticket = WorkboardTicketItem(
        id="private", title="Private Workboard title", status="todo", overdue=False
    )
    groups = {
        key: [ticket]
        for key in ("needs_me", "held_by_lia", "held_by_peers", "overdue", "open_total")
    }
    payload = WorkboardData.model_validate(
        {
            "needs_me": 1,
            "held_by_lia": 1,
            "held_by_peers": 1,
            "overdue": 1,
            "open_total": 1,
            "items": [ticket],
            "previews": groups,
        }
    )
    empty = CardSection(status=CardStatus.EMPTY, generated_at=NOW)
    cards = CardsBundle.model_validate(dict.fromkeys(SECTION_NAMES, empty))
    cards = cards.model_copy(
        update={"workboard": CardSection(status=CardStatus.OK, data=payload, generated_at=NOW)}
    )
    prompt = _summarize_cards_for_llm(cards, verbose=verbose)
    assert "Private Workboard title" not in prompt
    assert '"workboard"' not in prompt
