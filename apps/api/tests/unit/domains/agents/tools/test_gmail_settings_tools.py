"""Gmail settings tools behavior (lot I, 2026-08).

Covers the read tool's normalization and exact counts, the vacation request
validation (unrepairable errors stay errors), and the date-bounds conversion
(inclusive user end day → exclusive Gmail endTime, user timezone).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from src.domains.agents.tools.gmail_settings_tools import (
    GetGmailSettingsTool,
    _date_bounds_ms,
    _normalize_filters,
    _normalize_send_as,
    _normalize_vacation,
    _validate_vacation_request,
)

pytestmark = pytest.mark.unit


class TestNormalization:
    def test_vacation_defaults_when_gmail_returns_empty(self) -> None:
        assert _normalize_vacation({}) == {
            "enabled": False,
            "subject": "",
            "body": "",
            "start_time_ms": None,
            "end_time_ms": None,
        }

    def test_vacation_full_payload(self) -> None:
        vacation = _normalize_vacation(
            {
                "enableAutoReply": True,
                "responseSubject": "Absent",
                "responseBodyPlainText": "Je suis en congés.",
                "startTime": 1_787_000_000_000,
                "endTime": 1_787_800_000_000,
            }
        )
        assert vacation["enabled"] is True
        assert vacation["subject"] == "Absent"
        assert vacation["start_time_ms"] == 1_787_000_000_000

    def test_filters_keep_criteria_and_action_only(self) -> None:
        filters = _normalize_filters(
            {
                "filter": [
                    {
                        "id": "f1",
                        "criteria": {"from": "news@x.com"},
                        "action": {"addLabelIds": ["TRASH"]},
                        "internal": "dropped",
                    }
                ]
            }
        )
        assert filters == [
            {"id": "f1", "criteria": {"from": "news@x.com"}, "action": {"addLabelIds": ["TRASH"]}}
        ]

    def test_send_as_flags(self) -> None:
        aliases = _normalize_send_as(
            {
                "sendAs": [
                    {"sendAsEmail": "me@x.com", "isPrimary": True, "isDefault": True},
                    {"sendAsEmail": "alias@x.com", "displayName": "Support"},
                ]
            }
        )
        assert aliases[0]["is_primary"] is True
        assert aliases[1] == {
            "email": "alias@x.com",
            "display_name": "Support",
            "is_default": False,
            "is_primary": False,
        }


class TestReadToolAggregation:
    async def test_counts_are_exact_totals_from_the_whole_set(self) -> None:
        class _FakeClient:
            async def get_vacation(self) -> dict[str, Any]:
                return {"enableAutoReply": True, "responseSubject": "Absent"}

            async def list_filters(self) -> dict[str, Any]:
                return {"filter": [{"id": "f1"}, {"id": "f2"}]}

            async def list_send_as(self) -> dict[str, Any]:
                return {"sendAs": [{"sendAsEmail": "me@x.com", "isPrimary": True}]}

        tool = GetGmailSettingsTool()
        result = await tool.execute_api_call(_FakeClient(), uuid4())

        assert result["success"] is True
        assert result["vacation_responder"]["enabled"] is True
        assert result["filter_count"] == 2
        assert result["send_as_count"] == 1

    async def test_registry_response_carries_the_full_snapshot(self) -> None:
        class _FakeClient:
            async def get_vacation(self) -> dict[str, Any]:
                return {}

            async def list_filters(self) -> dict[str, Any]:
                return {}

            async def list_send_as(self) -> dict[str, Any]:
                return {}

        tool = GetGmailSettingsTool()
        result = await tool.execute_api_call(_FakeClient(), uuid4())
        output = tool.format_registry_response(result)

        assert output.success is True
        assert output.structured_data is not None
        assert output.structured_data["vacation_responder"]["enabled"] is False
        assert output.structured_data["filter_count"] == 0


class TestVacationValidation:
    def test_disable_needs_nothing(self) -> None:
        assert _validate_vacation_request(False, "", "", "") is None

    def test_enable_requires_a_body(self) -> None:
        assert _validate_vacation_request(True, "   ", "", "") == "vacation_body_required"

    def test_malformed_date_is_a_real_error(self) -> None:
        assert _validate_vacation_request(True, "Away.", "24/08/2026", "") == "invalid_date_format"

    def test_inverted_range_is_a_real_error(self) -> None:
        assert (
            _validate_vacation_request(True, "Away.", "2026-08-30", "2026-08-24")
            == "end_before_start"
        )

    def test_valid_enable_passes(self) -> None:
        assert _validate_vacation_request(True, "Away.", "2026-08-24", "2026-08-30") is None


class TestDateBounds:
    def test_end_is_exclusive_midnight_after_the_inclusive_last_day(self) -> None:
        start_ms, end_ms = _date_bounds_ms("2026-08-24", "2026-08-30", "UTC")
        assert start_ms == int(datetime(2026, 8, 24, tzinfo=UTC).timestamp() * 1000)
        # Inclusive last day 30/08 → exclusive bound = midnight 31/08.
        assert end_ms == int(datetime(2026, 8, 31, tzinfo=UTC).timestamp() * 1000)

    def test_bounds_use_the_user_timezone(self) -> None:
        utc_start, _ = _date_bounds_ms("2026-08-24", "", "UTC")
        paris_start, _ = _date_bounds_ms("2026-08-24", "", "Europe/Paris")
        # Paris midnight (UTC+2 in August) is 2 hours BEFORE UTC midnight.
        assert utc_start is not None and paris_start is not None
        assert utc_start - paris_start == 2 * 3600 * 1000

    def test_missing_dates_yield_open_bounds(self) -> None:
        assert _date_bounds_ms("", "", "UTC") == (None, None)

    def test_unknown_timezone_falls_back_to_utc(self) -> None:
        fallback, _ = _date_bounds_ms("2026-08-24", "", "Not/AZone")
        utc, _ = _date_bounds_ms("2026-08-24", "", "UTC")
        assert fallback == utc
