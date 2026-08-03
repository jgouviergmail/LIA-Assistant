"""The interest history at its HTTP boundary.

The repository pages and counts; this checks what the route does around it —
that the interest a notification was ABOUT travels with it, that a deleted
interest degrades to an absent topic instead of a crash, and that the total is
the one the repository measured rather than the length of the page.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.interests.notifications_router import get_interest_notification_history

pytestmark = pytest.mark.unit


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4())


def _row(**over: object) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "created_at": datetime(2026, 8, 1, 9, 30, tzinfo=UTC),
        "content": "Trois articles sur la fusion nucléaire cette semaine.",
        "source": "perplexity",
        "user_feedback": None,
        "interest": SimpleNamespace(topic="fusion nucléaire"),
    }
    base.update(over)
    return SimpleNamespace(**base)


def _patched(rows: list[object], total: int):
    return patch(
        "src.domains.interests.repository.InterestNotificationRepository.get_history",
        new=AsyncMock(return_value=(rows, total)),
    )


class TestHistoryRoute:
    async def test_reports_the_notification_with_its_interest(self) -> None:
        with _patched([_row()], total=1):
            response = await get_interest_notification_history(
                limit=10, offset=0, user=_user(), db=AsyncMock()
            )

        assert len(response.notifications) == 1
        item = response.notifications[0]
        assert item.content == "Trois articles sur la fusion nucléaire cette semaine."
        assert item.source == "perplexity"
        assert item.topic == "fusion nucléaire"

    async def test_a_deleted_interest_leaves_the_topic_absent_not_a_crash(self) -> None:
        """`interest_id` is nullable and the relationship can be None."""
        with _patched([_row(interest=None)], total=1):
            response = await get_interest_notification_history(
                limit=10, offset=0, user=_user(), db=AsyncMock()
            )

        assert response.notifications[0].topic is None

    async def test_a_row_predating_the_content_column_renders_without_it(self) -> None:
        with _patched([_row(content=None)], total=1):
            response = await get_interest_notification_history(
                limit=10, offset=0, user=_user(), db=AsyncMock()
            )

        assert response.notifications[0].content is None

    async def test_the_total_is_the_whole_set_not_the_page(self) -> None:
        """ADR-185: a count shown to the reader is exact or it does not exist."""
        with _patched([_row(), _row()], total=57):
            response = await get_interest_notification_history(
                limit=2, offset=0, user=_user(), db=AsyncMock()
            )

        assert len(response.notifications) == 2
        assert response.total == 57

    async def test_the_page_is_scoped_to_the_caller(self) -> None:
        user = _user()
        with _patched([], total=0) as history:
            await get_interest_notification_history(limit=10, offset=0, user=user, db=AsyncMock())

        assert history.await_args.kwargs["user_id"] == user.id

    async def test_an_empty_history_is_an_empty_list(self) -> None:
        with _patched([], total=0):
            response = await get_interest_notification_history(
                limit=10, offset=0, user=_user(), db=AsyncMock()
            )

        assert response.notifications == []
        assert response.total == 0


class TestItIsActuallyMounted:
    """A route defined in a module nobody includes is a 404 with tests.

    The endpoint moved out of `interests/router.py` when that file reached its
    frozen size ceiling. Extraction is the right answer; forgetting to mount
    the extracted router is the way it silently stops existing.
    """

    def test_the_path_is_reachable_on_the_v1_api(self) -> None:
        from src.api.v1.routes import api_router

        paths = {route.path for route in api_router.routes}  # type: ignore[attr-defined]
        assert "/interests/notifications/history" in paths

    def test_the_move_did_not_change_the_path_the_client_calls(self) -> None:
        # Same prefix as the main interests router: extracting a module is an
        # internal decision and must not be a contract change.
        from src.domains.interests.notifications_router import router

        assert router.prefix == "/interests"
