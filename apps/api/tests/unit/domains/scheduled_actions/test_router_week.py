"""``GET /scheduled-actions/week`` (ADR-265): shape, ownership, route order."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from src.domains.scheduled_actions.models import ScheduledRunOutcome
from src.domains.scheduled_actions.router import router, week_scheduled_actions
from src.domains.scheduled_actions.schemas import ScheduledActionWeekResponse
from src.domains.scheduled_actions.week import ActionWeek, WeekCell

pytestmark = pytest.mark.unit

OWNER = uuid.uuid4()
MON = datetime(2026, 8, 3, 6, 0, tzinfo=UTC)


def _week(action_id: uuid.UUID) -> ActionWeek:
    return ActionWeek(
        action_id=action_id,
        timezone="Europe/Paris",
        week_start=date(2026, 8, 3),
        today=3,
        cells=[
            WeekCell(
                day=1,
                date=date(2026, 8, 3),
                slot_at=MON,
                outcome=ScheduledRunOutcome.FAILURE,
                run_at=MON,
                error="boom",
                manual=False,
            ),
            WeekCell(
                day=3,
                date=date(2026, 8, 5),
                slot_at=datetime(2026, 8, 5, 6, 0, tzinfo=UTC),
                outcome=None,
                run_at=None,
                error=None,
                manual=None,
            ),
        ],
    )


class TestTheResponse:
    async def test_serialises_every_cell_for_the_caller_only(self) -> None:
        action_id = uuid.uuid4()
        with patch("src.domains.scheduled_actions.router.ScheduledActionService") as service_cls:
            service_cls.return_value.week_for_user = AsyncMock(return_value=[_week(action_id)])
            response = await week_scheduled_actions(user=SimpleNamespace(id=OWNER), db=object())

        service_cls.return_value.week_for_user.assert_awaited_once_with(OWNER)
        assert isinstance(response, ScheduledActionWeekResponse)
        [week] = response.actions
        assert (week.id, week.timezone, week.today) == (action_id, "Europe/Paris", 3)
        assert week.week_start == date(2026, 8, 3)
        assert [c.day for c in week.cells] == [1, 3]
        assert week.cells[0].outcome is ScheduledRunOutcome.FAILURE
        assert week.cells[0].error == "boom"
        assert week.cells[1].outcome is None
        assert response.generated_at.tzinfo is not None

    def test_the_outcome_travels_as_its_value(self) -> None:
        payload = ScheduledActionWeekResponse(
            actions=[
                {
                    "id": uuid.uuid4(),
                    "timezone": "Europe/Paris",
                    "week_start": date(2026, 8, 3),
                    "today": 1,
                    "cells": [
                        {
                            "day": 1,
                            "date": date(2026, 8, 3),
                            "slot_at": MON,
                            "outcome": "skipped_condition",
                        }
                    ],
                }
            ],
            generated_at=MON,
        ).model_dump(mode="json")
        assert payload["actions"][0]["cells"][0]["outcome"] == "skipped_condition"
        assert payload["actions"][0]["cells"][0]["run_at"] is None


class TestRouteOrder:
    def test_week_is_declared_before_any_action_id_route(self) -> None:
        """A literal segment after a path parameter is parsed as that parameter."""
        paths = [route.path for route in router.routes if isinstance(route, APIRoute)]
        week_index = paths.index("/scheduled-actions/week")
        first_parametrised = next(
            index for index, path in enumerate(paths) if "{action_id}" in path
        )
        assert week_index < first_parametrised, paths

    def test_week_resolves_as_a_literal_route(self) -> None:
        app = FastAPI()
        app.include_router(router)
        matched = [
            route
            for route in app.routes
            if isinstance(route, APIRoute)
            and route.path == "/scheduled-actions/week"
            and "GET" in route.methods
        ]
        assert len(matched) == 1
