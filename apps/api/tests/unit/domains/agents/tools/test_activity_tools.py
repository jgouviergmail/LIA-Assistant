"""The activity tool — what LIA did and consulted, as the model reads it (ADR-318).

The read itself is proven on PostgreSQL (``tests/integration/.../test_activity_db``);
here the TOOL is: the period it asks for (a day is a whole day in the person's
timezone), the action worded in the person's language as their register shows
it, the exact totals beside a shortened list, the vocabularies pinned to the
registers' enums, and every refusal typed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import get_args
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.core.config import settings
from src.domains.agents.activity.catalogue_manifests import (
    ACTIVITY_START_DESCRIPTION,
    ActivityOrigin,
    ActivityStatus,
    get_my_activity_catalogue_manifest,
)
from src.domains.agents.effects.activity import ActivityReport
from src.domains.agents.effects.models import EffectSource, EffectStatus
from src.domains.agents.effects.origin import RegisterOrigin
from src.domains.agents.tools import activity_tools
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")


def _action() -> SimpleNamespace:
    return SimpleNamespace(
        claimed_at=datetime(2026, 9, 24, 8, 5, tzinfo=UTC),
        tool_name="create_reminder_tool",
        status=EffectStatus.SUCCEEDED,
        source=EffectSource.USER,
        error_code=None,
    )


def _report(*, total: int = 1, listed: int = 1) -> ActivityReport:
    return ActivityReport(
        actions=[_action() for _ in range(listed)],
        actions_total=total,
        actions_by_status={"succeeded": total},
        consultations_by_domain={"email": 5, "weather": 2},
    )


async def _call(
    report: ActivityReport, *, language: str = "fr", **kwargs: object
) -> tuple[UnifiedToolOutput, AsyncMock]:
    read = AsyncMock(return_value=report)

    @asynccontextmanager
    async def session() -> AsyncIterator[MagicMock]:
        yield MagicMock()

    with (
        patch.object(activity_tools, "read_activity", read),
        patch.object(activity_tools, "get_db_context", session),
        patch.object(
            activity_tools,
            "readable_label",
            return_value=("effects.labels.create_reminder_tool", {"target": "Call Marie"}),
        ),
    ):
        output = await activity_tools.get_my_activity_tool.coroutine(
            runtime=make_tool_runtime(store=object(), timezone="Europe/Paris", language=language),
            **kwargs,
        )
    return output, read


class TestWhatTheModelReads:
    async def test_the_action_is_worded_as_the_person_s_register_shows_it(self) -> None:
        output, _read = await _call(_report())

        data = output.structured_data or {}
        assert data["actions"] == [
            {
                "when": "2026-09-24T10:05+02:00",
                "action": "Rappel « Call Marie » créé",
                "capability": "create_reminder_tool",
                "status": "succeeded",
                "authorship": "user",
                "error_code": None,
            }
        ]

    async def test_every_total_is_given_and_the_cut_is_stated(self) -> None:
        output, _read = await _call(_report(total=30, listed=20))

        data = output.structured_data or {}
        assert data["actions_total"] == 30
        assert len(data["actions"]) == 20
        assert data["consultations_total"] == 7
        assert data["consultations"][0] == {"domain": "email", "label": "E-mails", "count": 5}
        assert "10 others are counted, not listed" in output.message

    async def test_the_default_period_is_the_published_window_ending_now(self) -> None:
        before = datetime.now(UTC)
        _output, read = await _call(_report())

        kwargs = read.await_args.kwargs
        assert kwargs["until"] >= before
        assert kwargs["until"] - kwargs["since"] == timedelta(
            days=settings.effect_activity_window_days
        )
        assert kwargs["origin"] is RegisterOrigin.ALL and kwargs["status"] is None

    async def test_a_day_is_the_person_s_whole_day(self) -> None:
        _output, read = await _call(_report(), start_date="2026-09-21", end_date="2026-09-21")

        kwargs = read.await_args.kwargs
        assert kwargs["since"] == datetime(2026, 9, 21, tzinfo=PARIS)
        assert kwargs["until"] == datetime(2026, 9, 22, tzinfo=PARIS)

    async def test_a_filtered_total_says_which_total_it_is(self) -> None:
        """The breakdown covers every outcome, the total follows the filter: the
        sentence must not read « 1 action (2 succeeded, 1 failed) »."""
        report = ActivityReport(
            actions=[_action()],
            actions_total=1,
            actions_by_status={"succeeded": 2, "failed": 1},
            consultations_by_domain={},
        )

        output, _read = await _call(report, status="failed")

        assert "1 failed action(s) out of 3 in the period (2 succeeded, 1 failed)" in output.message

    async def test_the_filters_reach_the_read(self) -> None:
        _output, read = await _call(_report(), origin="initiative", status="failed")

        kwargs = read.await_args.kwargs
        assert kwargs["origin"] is RegisterOrigin.INITIATIVE
        assert kwargs["status"] is EffectStatus.FAILED

    async def test_the_ceiling_is_the_published_maximum(self) -> None:
        published = {
            c.kind: c.value
            for p in get_my_activity_catalogue_manifest.parameters
            if p.name == "max_results"
            for c in p.constraints
        }
        assert published["maximum"] == settings.effect_activity_max_actions

        _output, read = await _call(_report(), max_results=10_000)

        assert read.await_args.kwargs["limit"] == settings.effect_activity_max_actions


class TestRefusals:
    async def test_an_unreadable_day(self) -> None:
        output, read = await _call(_report(), start_date="last monday")

        assert output.error_code == ToolErrorCode.INVALID_INPUT.value
        assert "YYYY-MM-DD" in output.message
        read.assert_not_awaited()

    async def test_a_period_ending_before_it_starts(self) -> None:
        output, read = await _call(_report(), start_date="2026-09-22", end_date="2026-09-20")

        assert output.error_code == ToolErrorCode.INVALID_PARAM_VALUE.value
        read.assert_not_awaited()

    async def test_an_unknown_status(self) -> None:
        output, _read = await _call(_report(), status="exploded")

        assert output.error_code == ToolErrorCode.INVALID_PARAM_VALUE.value


class TestTheVocabulariesAreTheRegisters:
    def test_origins(self) -> None:
        assert set(get_args(ActivityOrigin)) == {member.value for member in RegisterOrigin}

    def test_statuses(self) -> None:
        assert set(get_args(ActivityStatus)) == {member.value for member in EffectStatus}


def test_the_react_schema_publishes_the_manifest_s_wording() -> None:
    description = activity_tools.get_my_activity_tool.args_schema.model_fields[
        "start_date"
    ].description

    assert description is not None and description.startswith(ACTIVITY_START_DESCRIPTION)
