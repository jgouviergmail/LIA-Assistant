"""Unit tests for ``_format_execution_summary`` registry handling (ADR-070).

Registry items reach the Initiative node in two shapes:
- **dict** in the pipeline (after a checkpoint serialization round-trip);
- **Pydantic `RegistryItem` objects** in ReAct (built in-memory by
  ``react_execute_tools``, no round-trip).

Before the fix, the function only handled dicts (`if not isinstance(item, dict):
continue`), so in ReAct it silently dropped every item and produced
``"No execution results."`` — leaving the Initiative LLM blind to the data the
ReAct loop had just fetched (observed live: "Sans détails sur les rendez-vous …",
``should_act=false``). These tests pin dual-format handling.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.core.constants import INITIATIVE_SUMMARY_MAX_FIELDS
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.nodes.initiative_node import _format_execution_summary


@pytest.mark.unit
class TestFormatExecutionSummaryRegistryShapes:
    def test_pydantic_registry_item_is_surfaced(self):
        """ReAct shape: RegistryItem objects must be summarised, not skipped."""
        item = RegistryItem(
            id="event_1",
            type=RegistryItemType.EVENT,
            payload={"summary": "Ramonage", "start": "2026-05-22T09:00:00"},
            meta=RegistryItemMeta(source="google_calendar", domain="calendar"),
        )
        summary = _format_execution_summary({}, registry={"event_1": item}, current_turn_id=4)
        assert "Ramonage" in summary
        assert "calendar" in summary
        assert summary != "No execution results."

    def test_dict_registry_item_still_works(self):
        """Pipeline shape: serialized dict items keep working (no regression)."""
        registry = {
            "event_1": {
                "payload": {"summary": "Ramonage", "start": "2026-05-22T09:00:00"},
                "meta": {"domain": "calendar", "source": "google_calendar"},
            }
        }
        summary = _format_execution_summary({}, registry=registry, current_turn_id=4)
        assert "Ramonage" in summary
        assert "calendar" in summary

    def test_empty_registry_returns_sentinel(self):
        summary = _format_execution_summary({}, registry={}, current_turn_id=4)
        assert summary == "No execution results."


def _email_item(reply_state: dict[str, object], **fields: object) -> dict[str, object]:
    payload = {"subject": "Budget", "from": "Marc <marc@example.org>", **fields}
    return {"payload": {**payload, "reply_state": reply_state}, "meta": {"domain": "emails"}}


def _reply_state(status: str, *, valid_minutes: int, **over: object) -> dict[str, object]:
    observed = datetime.now(UTC)
    return {
        "version": "mail-reply-state-v1",
        "status": status,
        "observed_at": observed.isoformat(),
        "valid_until": (observed + timedelta(minutes=valid_minutes)).isoformat(),
        **over,
    }


@pytest.mark.unit
class TestAnEmailSaysWhetherItWasAnswered:
    """ADR-379: the initiative offered to draft replies the person had already sent —
    an annotation is a dict, and the summary skipped every dict."""

    def test_an_answered_email_says_so(self) -> None:
        answered = _reply_state(
            "answered",
            valid_minutes=2,
            message={
                "message_id": "m2",
                "at": "2026-11-10T09:30:00+01:00",
                "correspondents": "Marc",
                "excerpt": "Yes, Friday works.",
            },
        )

        summary = _format_execution_summary({}, registry={"email_1": _email_item(answered)})

        assert "Reply state: answered on 2026-11-10T09:30+01:00 to Marc — Yes, Friday works." in (
            summary
        )

    def test_the_state_is_never_cut_by_the_field_bound(self) -> None:
        many = {
            f"field_{index}": f"value {index}" for index in range(INITIATIVE_SUMMARY_MAX_FIELDS)
        }
        item = _email_item(_reply_state("unanswered", valid_minutes=2), **many)

        summary = _format_execution_summary({}, registry={"email_1": item})

        assert "Reply state: unanswered" in summary

    def test_a_reading_too_old_to_repeat_says_nothing(self) -> None:
        stale = _reply_state("unanswered", valid_minutes=-1)
        stale["observed_at"] = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()

        summary = _format_execution_summary({}, registry={"email_1": _email_item(stale)})

        assert "Reply state" not in summary and "Budget" in summary
